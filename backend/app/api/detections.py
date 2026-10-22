import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import check_llm_quota
from app.core.security import current_user, decode_user_id, ensure_not_revoked
from app.models.user import User
from app.models.detection import Detection
from app.models.chat_message import ChatMessage
from app.schemas.detection import DetectionResponse, DetectionPage
from app.services import image_detection
from app.services.observation import Observation, parse_observation
from app.services.analysis_jobs import analysis_request
from app.services.detection_response import serialize
from app.services.host_prior import host_prior
from app.services.llm import llm


router = APIRouter(prefix="/detections", tags=["detections"])
settings = get_settings()
logger = logging.getLogger(__name__)

@router.get("/crops", summary="可选作物清单（寄主先验下拉框数据源）")
async def list_crops(user: User = Depends(current_user)):
    """前端「这是什么作物」下拉框的数据源。

    has_prior=False 的作物不会改变排序，但仍会作为上下文传给大模型，
    让防治建议的用药部位与安全间隔期口径贴合该作物 —— 所以照样要展示给用户选。
    """
    items = host_prior.crops()
    return {
        "available": host_prior.available,
        # 先验表缺失时前端隐藏下拉框，而不是给个点了没反应的空控件
        "error": host_prior.load_error,
        "crops": items,
    }


@router.post("/image", response_model=DetectionResponse, status_code=201)
async def detect_image(
    file: UploadFile = File(...),
    crop: str | None = Form(None),
    observation: str | None = Form(None),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    item = await image_detection.detect_image(file, crop, user.id, db, parse_observation(observation))
    return serialize(item)


@router.get("", response_model=list[DetectionResponse])
async def list_detections(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db),
    offset: int = 0,
    limit: int = 50,
    media_type: str | None = None,
):
    offset = max(0, offset)
    limit = max(1, min(limit, 100))
    query = select(Detection).where(Detection.user_id == user.id)
    if media_type:
        if media_type not in {"image", "video"}:
            raise HTTPException(422, "media_type must be image or video")
        query = query.where(Detection.media_type == media_type)
    rows = await db.scalars(query.order_by(desc(Detection.created_at)).offset(offset).limit(limit))
    return [serialize(row) for row in rows]


@router.get('/search', response_model=DetectionPage)
async def search_detections(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db),
    offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
    media_type: str | None = None, status: str | None = None,
    q: str | None = Query(None, max_length=100),
    start_at: datetime | None = None, end_at: datetime | None = None,
    field_name: str | None = Query(None, max_length=80),
    detection_id: str | None = Query(None, max_length=36),
):
    from app.services.record_search import search_records
    return await search_records(db, user.id, offset, limit, media_type, status, q, start_at, end_at, field_name, detection_id)


@router.get("/{detection_id}", response_model=DetectionResponse)
async def get_detection(
    detection_id: str,
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db),
):
    """按 id 查询图片或视频记录，不触发状态变更。"""
    item = await db.scalar(
        select(Detection).where(Detection.id == detection_id, Detection.user_id == user.id)
    )
    if not item:
        raise HTTPException(404, "Detection not found")
    return serialize(item)


@router.get("/{detection_id}/comparison")
async def compare_pests(detection_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    item = await db.scalar(select(Detection).where(Detection.id == detection_id, Detection.user_id == user.id))
    if not item:
        raise HTTPException(404, "Detection not found")
    from app.services.observation import comparison_notes
    from app.services.admission import run_blocking
    return await run_blocking(comparison_notes, item.predictions or [], item.media_type)


@router.patch("/{detection_id}/observation", response_model=DetectionResponse)
async def save_observation(detection_id: str, body: Observation,
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    item = await db.scalar(select(Detection).where(Detection.id == detection_id, Detection.user_id == user.id))
    if not item:
        raise HTTPException(404, "Detection not found")
    item.observation = body.model_dump()
    await db.commit()
    await db.refresh(item)
    return serialize(item)


@router.get("/{detection_id}/original")
async def original_file(detection_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    item = await db.scalar(select(Detection).where(Detection.id == detection_id, Detection.user_id == user.id))
    if not item or item.media_type != "image":
        raise HTTPException(404, "Original image not found")
    path = (settings.upload_dir / item.stored_name).resolve()
    if settings.upload_dir.resolve() not in path.parents or not path.is_file():
        raise HTTPException(410, "原图已被清理")
    return FileResponse(path, headers={"Cache-Control": "private, no-store"})


# ── 结果文件的短时签名票据 ────────────────────────────────────────────
#
# 为什么需要它：<img> / <video> 带不了 Authorization 头，所以以前是把
# **完整 JWT** 拼进 URL 查询串（?token=…）。那个 JWT 12 小时有效、全权代表
# 用户，而 URL 会进入浏览器历史、Referer、nginx access log、答辩录屏 ——
# 等于把会话凭据散落到一堆不受控的地方。
#
# 换成票据后：URL 里只有一个绑定到**单个 detection_id**、5 分钟过期的
# HMAC 签名。即使从日志里泄漏，也只能读那一条结果，且很快失效。
_RESULT_TICKET_TTL_SECONDS = 300


def _result_ticket_signature(detection_id: str, expires: int) -> str:
    import hashlib
    import hmac

    msg = f"result:{detection_id}:{expires}".encode()
    return hmac.new(
        settings.secret_key.encode(), msg, hashlib.sha256
    ).hexdigest()


def make_result_ticket(detection_id: str) -> str:
    """为某个 detection 生成 ?ticket=<expires>-<sig> 形式的一次性票据。"""
    expires = int(time.time()) + _RESULT_TICKET_TTL_SECONDS
    return f"{expires}-{_result_ticket_signature(detection_id, expires)}"


def verify_result_ticket(detection_id: str, ticket: str | None) -> bool:
    """校验票据：签名必须匹配，且未过期。"""
    import hmac

    if not ticket or "-" not in ticket:
        return False
    raw_expires, _, signature = ticket.partition("-")
    try:
        expires = int(raw_expires)
    except ValueError:
        return False
    if expires < int(time.time()):
        return False
    expected = _result_ticket_signature(detection_id, expires)
    return hmac.compare_digest(expected, signature)


@router.get("/{detection_id}/result-ticket")
async def result_ticket(
    detection_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """为结果文件换取一个短时票据 URL。

    需要正常鉴权（Authorization 头），票据本身只授权读取这一条结果。
    """
    item = await db.scalar(
        select(Detection).where(Detection.id == detection_id, Detection.user_id == user.id)
    )
    if not item or not item.result_path:
        raise HTTPException(404, "Result not found")
    return {
        "url": f"/api/detections/{detection_id}/result?ticket={make_result_ticket(detection_id)}",
        "expires_in": _RESULT_TICKET_TTL_SECONDS,
    }


@router.get("/{detection_id}/result")
async def result_file(
    detection_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    ticket: str | None = Query(default=None),
):
    """返回结果文件。鉴权二选一：

    1. `Authorization: Bearer <JWT>`（API/脚本调用）；
    2. `?ticket=`（短时签名票据，给 <img>/<video> 用）。

    不再接受 `?token=<JWT>`：那会把长期凭据写进 URL 与访问日志。
    """
    user_id: int | None = None

    if ticket:
        # 票据已绑定 detection_id，签名不对或过期就直接拒绝
        if not verify_result_ticket(detection_id, ticket):
            raise HTTPException(401, "Invalid or expired ticket")
    else:
        auth = request.headers.get("authorization", "")
        raw = auth[7:] if auth.lower().startswith("bearer ") else ""
        if not raw:
            raise HTTPException(401, "Unauthorized")
        await ensure_not_revoked(raw)
        user_id = decode_user_id(raw)

    stmt = select(Detection).where(Detection.id == detection_id)
    if user_id is not None:
        # header 鉴权：必须属于该用户
        stmt = stmt.where(Detection.user_id == user_id)
    item = await db.scalar(stmt)
    if not item or not item.result_path:
        raise HTTPException(404, "Result not found")
    path = (settings.result_dir / item.result_path).resolve()
    if settings.result_dir.resolve() not in path.parents:
        raise HTTPException(404, "Result not found")
    if not path.is_file():
        # 记录还在但文件已被清理（例如跑过 clear_data.ps1）——与「记录不存在」区分开，
        # 前端可据此显示占位图而不是一张裂图
        raise HTTPException(410, "Result file has been cleaned up")
    return FileResponse(
        path,
        media_type=None,                      # 交给 Starlette 按扩展名推断
        headers={"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=300"},
    )


def _discard_files(pairs: list[tuple[Path, str | None]]) -> None:
    """尽力删除落盘文件，失败只记日志。

    必须在事务提交之后调用：顺序反过来的话，unlink 抛异常（Windows 下文件被
    占用、Linux 下权限不足）会让数据库记录留下来而文件已经没了 —— 前端列表
    就会出现「有记录、无图」的幽灵条目。反过来则只是残留几个文件，
    由定期孤儿回收处理，代价小得多。
    """
    for directory, name in pairs:
        if not name:
            continue
        try:
            (directory / name).unlink(missing_ok=True)
        except OSError:
            logger.warning("删除文件失败，留给孤儿回收：%s/%s", directory, name, exc_info=True)


@router.delete("/all", status_code=204)
async def delete_all_detections(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    """清空当前用户的所有检测记录（演示模式用）。"""
    items = await db.scalars(select(Detection).where(Detection.user_id == user.id))
    pending: list[tuple[Path, str | None]] = []
    for item in items.all():
        pending.append((settings.result_dir, item.result_path))
        pending.append((settings.upload_dir, item.stored_name))
        await db.delete(item)
    await db.commit()
    _discard_files(pending)


@router.delete("/{detection_id}", status_code=204)
async def delete_detection(
    detection_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    item = await db.scalar(
        select(Detection).where(Detection.id == detection_id, Detection.user_id == user.id)
    )
    if not item:
        raise HTTPException(404, "Detection not found")
    pending = [
        (settings.result_dir, item.result_path),
        (settings.upload_dir, item.stored_name),
    ]
    await db.delete(item)
    await db.commit()
    _discard_files(pending)


class ChatRequest(BaseModel):
    # 上限 500 字：既是提问的自然长度，也防止超长输入把历史塞爆导致 token 溢出
    message: str = Field(min_length=1, max_length=500)


@router.post("/{detection_id}/chat")
async def chat_about_detection(
    detection_id: str,
    body: ChatRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """针对一次检测结果的多轮追问（Agent 对话），历史持久化。"""
    item = await db.scalar(
        select(Detection).where(Detection.id == detection_id, Detection.user_id == user.id)
    )
    if not item:
        raise HTTPException(404, "Detection not found")
    msg = (body.message or "").strip()
    if not msg:
        raise HTTPException(422, "message is empty")
    # 追问是纯 LLM 调用，同样要计配额
    await check_llm_quota(user.id)
    reply = await llm.chat(item.id, item.predictions or [], item.media_type, msg, db)
    if reply is None:
        raise HTTPException(503, "AI 助手暂时思考不过来，请稍后再试")
    return {"reply": reply}


@router.get("/{detection_id}/chat")
async def chat_history(
    detection_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """拉取某次检测下的历史对话（用于前端刷新后恢复聊天记录）。"""
    item = await db.scalar(
        select(Detection).where(Detection.id == detection_id, Detection.user_id == user.id)
    )
    if not item:
        raise HTTPException(404, "Detection not found")
    # 次级排序键必须是 id：created_at 用 SQLite 的秒级 CURRENT_TIMESTAMP，
    # 同一轮对话里 user 和 assistant 两条消息时间戳完全相同，
    # 只按时间排时顺序不确定，会显示成「回答在提问之前」。
    rows = await db.scalars(
        select(ChatMessage)
        .where(ChatMessage.detection_id == detection_id)
        .order_by(ChatMessage.created_at, ChatMessage.id)
    )
    return [
        {"role": m.role, "content": m.content,
         "created_at": (m.created_at.replace(tzinfo=timezone.utc) if m.created_at.tzinfo is None else m.created_at).isoformat()}
        for m in rows.all()
    ]


class FeedbackRequest(BaseModel):
    rating: str  # "good" / "bad"
    note: str | None = None


@router.post("/{detection_id}/feedback")
async def submit_feedback(
    detection_id: str,
    body: FeedbackRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """用户对识别结果点赞/点踩，形成数据闭环。"""
    if body.rating not in ("good", "bad"):
        raise HTTPException(422, "rating must be 'good' or 'bad'")
    item = await db.scalar(
        select(Detection).where(Detection.id == detection_id, Detection.user_id == user.id)
    )
    if not item:
        raise HTTPException(404, "Detection not found")
    item.feedback = body.rating
    item.feedback_note = (body.note or "")[:500] or None
    await db.commit()
    return {"ok": True}


@router.post("/{detection_id}/analysis", response_model=DetectionResponse, status_code=202)
async def retry_analysis(
    detection_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db),
    refresh: bool = Query(False),
):
    item = await db.scalar(select(Detection).where(Detection.id == detection_id, Detection.user_id == user.id))
    if not item:
        raise HTTPException(404, "Detection not found")
    if item.status != "completed":
        raise HTTPException(409, "请等待识别完成")
    if item.analysis_status in {"queued", "processing"} or (item.analysis_status == "completed" and not refresh):
        return serialize(item)
    values = analysis_request(item.predictions)
    if values["analysis_status"] != "queued":
        raise HTTPException(409, "没有可解读的结果，或 AI 服务尚未配置")
    await db.execute(update(Detection).where(
        Detection.id == item.id, Detection.user_id == user.id,
        Detection.analysis_status.in_(["failed", "disabled", "skipped"] + (["completed"] if refresh else [])),
    ).values(**values))
    await db.commit()
    await db.refresh(item)
    return serialize(item)
