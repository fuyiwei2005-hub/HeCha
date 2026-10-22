import asyncio
import json
import logging
import re
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.chat_message import ChatMessage
from app.services.knowledge import get_knowledge_base

logger = logging.getLogger(__name__)

# 单条参考资料注入上限。知识库条目正文在 300 字左右，截断是为了在
# 多虫种场景下把 4-6 条的 token 成本压住，避免挤占正文预算触发 finish_reason=length。
MAX_REF_CHARS = 520

# 检索时的附加意图词：只发虫种名的话 BM25 会召回一堆同名条目，
# 加上意图词才能把「危害症状 / 防治」相关的段落顶上来
RETRIEVE_INTENT = "危害症状 发生规律 防治方法 农业防治 化学防治"

# 单条检测保留的对话条数上限。模型上下文只取最近 20 条，
# 留 200 条既够前端回溯完整会话，又不会让表无限膨胀。
MAX_CHAT_ROWS_PER_DETECTION = 200


async def _trim_chat_history(db: AsyncSession, detection_id: str) -> None:
    """把某条检测下的对话裁剪到最近 N 条。

    只 flush 不 commit：事务边界属于调用方（chat() 负责提交），
    在这里自己 commit 会把调用方还没写完的东西一起提交掉，
    也让"一次提问 = 一个事务"这个语义被打破。
    """
    keep = select(ChatMessage.id).where(
        ChatMessage.detection_id == detection_id
    ).order_by(ChatMessage.id.desc()).limit(MAX_CHAT_ROWS_PER_DETECTION)
    await db.execute(
        delete(ChatMessage).where(
            ChatMessage.detection_id == detection_id,
            ChatMessage.id.notin_(keep),
        )
    )
    await db.flush()


_RAG_RULES = (
    "\n【参考资料使用规则】\n"
    "你会收到以 [编号] 开头的参考资料段落，这些是权威植保资料。请严格遵守：\n"
    "1. 优先依据参考资料作答，不得编造资料里没有的虫种、药剂成分或剂量；\n"
    "2. 凡依据参考资料得出的结论，在句末或段末标注对应编号，格式如 [1] 或 [1][2]；\n"
    "3. 资料不足以支撑时可结合通用植保常识补充，但补充部分不要标编号；\n"
    "4. 严禁推荐国家禁限用农药（如甲胺磷、对硫磷、克百威、涕灭威等），"
    "发现资料中出现此类成分一律替换为合法替代品；\n"
    "5. 涉及用药时必须提示遵守标签剂量与安全间隔期；\n"
    "6. 知识库条目为教学演示用整理稿，数字类信息（发生代数、安全间隔期天数、持效期）"
    "随地域与年份变化，凡涉及具体天数与剂量须加「以当地植保部门指导与产品标签为准」的限定语，"
    "不得把天数说成绝对结论。\n"
)

_SYSTEM_PROMPT_BASE = (
    "你是一名农作物植保助手。基于模型候选结果、田间背景与参考资料，用简洁中文分四部分回答：\n"
    "1. 识别与不确定性：候选虫种、危害症状、需核对的相似特征；\n"
    "2. 现在怎么处理：结合生长阶段和用户自述程度，给出可执行的农业、物理防治方向；\n"
    "3. 后续怎么观察：观察部位、变化与补拍重点；\n"
    "4. 何时咨询农技人员：说明需要现场复核的情况。\n"
    "缺少背景时明确说明；用户自述不是已证实事实，置信度不代表虫害程度。"
    "模型检出是候选判断，不是确诊；未检出也不能排除虫害。不要编造虫种或协同危害。"
    "总长度约300-500字，用药仅给有资料支持的方向，不推荐品牌。"
)

# 口径必须按媒体类型分开交代。
#
# 原来的写法把「视频按时间抽帧、同一只虫会在连续多帧被检出、某虫在 N 个采样帧中
# 被检出」这段话无条件放进了系统提示，结果**图片**分析也照抄这套说法：
# 一张白菜照片检出 4 个目标，模型写成「本视频按时间抽帧…多次检出」；
# 一张柑橘照片检出 27 个目标，写成「蚜虫在 18 个采样帧中被检出」。
# 用户看到的是一张静态照片，却被描述了帧数和持续时间 —— 这属于事实性错误，
# 而评委很容易当场指出来。所以图片和视频给两套不同的口径。
_IMAGE_ADDENDUM = (
    "\n【本次是单张静态照片，不是视频】"
    "数据里的「出现 N 次」含义是：**这一张图里检出了 N 个该虫种的目标**，"
    "对应画面里聚集的 N 头（或虫体片段），与时间、帧、持续时间无关。\n"
    "绝对不要使用「采样帧」「抽帧」「逐帧」「连续多帧」「持续时间」「帧数」这类说法，"
    "也不要把检出数量换算成时间。用「本图检出 N 个目标（约 N 头）」这样的表述。"
)

_VIDEO_ADDENDUM = (
    "\n【本次是视频，结果是按时间抽帧得到的】"
    "同一只虫会在连续多帧里被重复检出，因此「出现的采样帧数」描述的是**持续时间**，"
    "不是害虫只数；回答时不要写成「共出现 N 次」，也不要把它当成虫口密度。"
)

SYSTEM_PROMPT = _SYSTEM_PROMPT_BASE + _IMAGE_ADDENDUM + _RAG_RULES
SYSTEM_PROMPT_VIDEO = _SYSTEM_PROMPT_BASE + _VIDEO_ADDENDUM + _RAG_RULES

CHAT_SYSTEM_PROMPT = (
    "你是一名经验丰富的农作物植保助手。用户刚刚用一个 AI 害虫识别系统拍完照片，系统已经告诉你检测到了什么害虫。"
    "现在用户会基于这次检测结果连续追问，问题可能包括：这种虫会不会传染？用什么药？什么时候打？对人有没有害？"
    "下次还会复发吗？请用口语化、简短、直接的中文回答，像农技员在田埂上跟农户说话。"
    "不要重复列三段结构，不要编造检测结果里没有的虫种。用药给通用类别（如吡虫啉、阿维菌素），不推荐具体品牌。"
    "如果用户问的问题和农业无关，礼貌地把话题拉回作物保护。"
    "\n【参考资料使用规则】\n"
    "你会收到以 [编号] 开头的参考资料段落。请优先依据资料作答，不得编造资料里没有的虫种、"
    "药剂成分或剂量；严禁推荐国家禁限用农药。\n"
    "注意：追问是口语化对话，不要在回答里出现 [1] 这类编号角标，直接把内容说清楚即可。"
)


class LLMAnalyzer:
    """把 YOLO 的结构化检测结果交给 DeepSeek 做自然语言解读。

    设计原则：
    - 未配置 DEEPSEEK_API_KEY 时自动关闭，返回 None，不影响 YOLO 主流程；
    - 调用超时 / 报错一律降级为 None，不让 LLM 故障拖垮检测接口；
    - 使用 AsyncOpenAI，异步调用不阻塞事件循环。
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self._client: AsyncOpenAI | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.settings.deepseek_api_key)

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self.settings.deepseek_api_key,
                base_url=self.settings.deepseek_base_url,
                timeout=self.settings.deepseek_timeout,
                # 关键：SDK 默认 max_retries=2，会让"12 秒超时"变成
                # 3 × 12 秒 + 退避 ≈ 40 秒，而这是个**同步返回**的图片接口 ——
                # 用户就盯着转圈。config.py 里"超时就降级不要卡住主流程"的
                # 承诺，只有在关掉 SDK 重试之后才成立。
                # 重试交给外层（analyze 会降级，用户可重新上传）。
                max_retries=0,
            )
        return self._client

    def _thinking_kwargs(self) -> dict[str, Any]:
        """构造"关闭思考模式"的 extra_body。

        这段是**厂商私有**字段，不是 OpenAI 标准参数：DeepSeek 收
        {"thinking": {"type": "disabled"}}，阿里百炼收 {"enable_thinking": false}，
        而 qwen-max 这类纯非思考模型两者都不认。写死任一家的写法会让换厂商时
        请求被 400 拒绝 —— 又因为 LLM 是可选增强、异常一律降级，症状只是
        「建议生成失败」，不报错、难定位。所以改为配置驱动，默认维持 DeepSeek 不变。

        解析失败（配错 JSON）时宁可**不发**该参数也不能让整次调用崩：
        多数模型省略它只是多花点思考 token，而抛异常会直接丢掉整段建议。
        """
        raw = (self.settings.deepseek_thinking_param or "").strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            logger.warning(
                "DEEPSEEK_THINKING_PARAM 不是合法 JSON，已忽略：%r", raw[:120]
            )
            return {}
        if not isinstance(parsed, dict):
            logger.warning(
                "DEEPSEEK_THINKING_PARAM 必须是 JSON 对象，已忽略：%r", raw[:120]
            )
            return {}
        # 空对象 {} 视为"显式不发送"
        return {"extra_body": parsed} if parsed else {}

    @staticmethod
    def _normalize(
        predictions: list[dict[str, Any]], media_type: str
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """把 predictions 统一成 (事件列表, 展平检测列表)。

        视频在库里存的是 [{time_ms, detections}, ...]，但历史上也有调用方直接把
        展平后的检测列表传进来（worker 早期版本就是这么干的）。两者不区分的话，
        _summarize_video 会把每条检测当成「一个没有任何目标的帧」，算出
        「共采样 203 帧，其中 0 帧检出目标」，模型于是理直气壮地回答
        「未发现任何害虫」——与界面上的 203 个框完全矛盾。这里统一兼容。
        """
        if media_type != "video":
            return [], list(predictions)
        if predictions and isinstance(predictions[0], dict) and "detections" in predictions[0]:
            events = list(predictions)
        else:
            events = [{"time_ms": None, "detections": list(predictions)}] if predictions else []
        flat = [d for ev in events for d in (ev.get("detections") or [])]
        return events, flat

    @staticmethod
    def _summarize(predictions: list[dict[str, Any]]) -> str:
        """图片汇总：按「同一张图里检出多少个目标」表述。

        措辞很关键：不能写「出现 N 次」那种含糊的说法，
        否则模型会自己引申成"持续出现/多个采样帧"。
        """
        counts: dict[str, list[float]] = {}
        for p in predictions:
            # 优先用中文虫种名：让 LLM 看到的虫名与用户在界面上看到的一致，
            # 避免它照着英文类名回答，出现"aphids"这类中英夹杂
            name = str(p.get("class_cn") or p.get("class") or "unknown")
            counts.setdefault(name, []).append(float(p.get("confidence", 0.0)))
        lines = [
            f"- {name}：本图检出 {len(confs)} 个目标，平均置信度 {sum(confs) / len(confs):.0%}"
            for name, confs in sorted(counts.items(), key=lambda kv: -len(kv[1]))
        ]
        return "\n".join(lines)

    @staticmethod
    def _summarize_video(events: list[dict[str, Any]]) -> str:
        """视频专用汇总：按「出现帧数」而不是「目标总数」描述。

        视频按 8fps 采样，同一只虫会在连续多帧里被重复检出。若直接把 40 条检测
        丢给模型，它会写成「共出现 40 次」——与画面里只有几只虫的事实不符，
        用户观感就是「结果给的不全/不准」。这里改为按虫种统计「出现的采样帧数」
        与「单帧最多目标数」，更贴近真实语义。
        """
        per_class: dict[str, dict[str, float]] = {}
        total_frames = len(events)
        frames_with_hit = 0
        for ev in events:
            dets = ev.get("detections") or []
            if not dets:
                continue
            frames_with_hit += 1
            seen_in_frame: dict[str, float] = {}
            for d in dets:
                name = str(d.get("class_cn") or d.get("class") or "unknown")
                conf = float(d.get("confidence", 0.0))
                slot = per_class.setdefault(name, {"frames": 0, "conf_sum": 0.0, "n": 0, "peak": 0})
                seen_in_frame[name] = max(seen_in_frame.get(name, 0.0), conf)
                slot["conf_sum"] += conf
                slot["n"] += 1
            # 单帧内同种虫的个数计为峰值
            for name, _ in seen_in_frame.items():
                slot = per_class[name]
                cnt = sum(1 for d in dets
                          if str(d.get("class_cn") or d.get("class") or "unknown") == name)
                slot["peak"] = max(slot["peak"], cnt)
            for name in seen_in_frame:
                per_class[name]["frames"] += 1

        lines = [
            f"- {name}：在 {int(v['frames'])}/{total_frames} 个采样帧中被检出，"
            f"单帧最多 {int(v['peak'])} 个，平均置信度 {v['conf_sum'] / max(1, v['n']):.0%}"
            for name, v in sorted(per_class.items(), key=lambda kv: -kv[1]["frames"])
        ]
        times = [ev.get("time_ms") for ev in events if ev.get("time_ms") is not None]
        span = ""
        if times:
            span = f"（时间跨度 {min(times)}ms – {max(times)}ms）"
        header = f"视频共采样 {total_frames} 帧，其中 {frames_with_hit} 帧检出目标{span}。"
        return header + "\n" + "\n".join(lines) if lines else header + "\n（未检出害虫）"

    @staticmethod
    def _pest_names(predictions: list[dict[str, Any]], media_type: str) -> list[str]:
        """从检测结果里提取虫种中文名，用于构造检索查询。"""
        if media_type == "video":
            flat = [d for p in predictions if isinstance(p, dict) for d in (p.get("detections") or [])]
        else:
            flat = list(predictions)
        names: list[str] = []
        for p in flat:
            name = str(p.get("class_cn") or p.get("class") or "").strip()
            if name and name not in names:
                names.append(name)
        return names

    async def _retrieve(
        self, predictions: list[dict[str, Any]], media_type: str, extra_query: str = ""
    ) -> list[dict[str, Any]]:
        """RAG 的检索环节：拿虫种名去知识库取资料。

        任何一步失败都返回空列表——知识库是增强项，不能因为它挂了就让检测失败。

        检索是纯 CPU：jieba 分词 + BM25 全库打分，首次调用还要读 JSON 并建索引。
        放在事件循环里跑会把同进程的其它请求（含健康检查）一起按住，所以丢线程池。
        """
        try:
            kb = get_knowledge_base()
            if not kb.available:
                return []
            names = self._pest_names(predictions, media_type)
            if not names:
                return []
            # 虫种名重复 3 次做 query boosting：BM25 没有字段权重机制，
            # 虫种名只发一次的话，「防治方法」这类通用意图词会把无关条目顶上来
            # （实测检索蚜虫时召回了蝗虫）。重复靠词频把主对象权重提上去。
            boosted = (" ".join(names) + " ") * 3
            query = boosted + RETRIEVE_INTENT + " " + extra_query
            return await asyncio.to_thread(kb.search, query, min(6, 2 + len(names)))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Knowledge retrieval failed: %s", exc)
            return []

    @staticmethod
    def _format_refs(refs: list[dict[str, Any]]) -> str:
        """把检索结果渲染成给模型看的带编号资料段。"""
        if not refs:
            return ""
        blocks = [
            f"[{r['ref']}] {r['title']}（来源：{r['source']}）\n{r['body'][:MAX_REF_CHARS]}"
            for r in refs
        ]
        # 统一声明放在资料段最前面：一处改动覆盖全部条目，
        # 比逐条改 68 条正文安全得多（改正文容易引入新的事实错误）
        return (
            "【参考资料】\n"
            "说明：以下为教学演示用整理稿。其中发生代数、发生月份、安全间隔期等"
            "数字随地域与年份变化较大，引用时须加限定语，不得当作绝对结论。\n\n"
            + "\n\n".join(blocks)
            + "\n【参考资料结束】"
        )

    async def analyze(
        self, predictions: list[dict[str, Any]], media_type: str,
        crop_hint: str | None = None,
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """返回 (解读文本, 引用列表)。引用列表可直接入库与前端溯源展示。

        crop_hint 是「用户在什么作物上拍的」这段上下文（由 host_prior 生成），
        没有就不传 —— 空字符串会被直接忽略，不进 prompt，避免白白占 token。
        """
        if not self.enabled or not predictions:
            return None, []
        # LLM 是可选增强：汇总、拼 prompt、调模型任何一步出错都必须降级成 None，
        # 绝不能把异常抛回检测接口——YOLO 结果已经出来了，却因为解读失败整单 500，
        # 用户看到的就是「图片识别不了」，而且落盘的原图/结果图还会变成孤儿文件。
        try:
            return await self._analyze_inner(predictions, media_type, crop_hint)
        except Exception as exc:  # noqa: BLE001
            logger.warning("DeepSeek analysis failed unexpectedly: %s", exc, exc_info=True)
            return None, []

    async def _analyze_inner(
        self, predictions: list[dict[str, Any]], media_type: str,
        crop_hint: str | None = None,
    ) -> tuple[str | None, list[dict[str, Any]]]:
        events, flat = self._normalize(predictions, media_type)
        if media_type == "video":
            # 视频的 predictions 是 [{time_ms, detections}, ...]
            summary = self._summarize_video(events)
            head = f"这是一份视频逐帧检测结果：\n{summary}"
            system_prompt = SYSTEM_PROMPT_VIDEO
        else:
            # 图片：predictions 是同一张图里的多个目标，与时间无关。
            # 汇总与系统提示都要按"张"的口径来，否则模型会自己编出帧数。
            summary = self._summarize(flat)
            head = f"这是一张静态照片的检测结果（多个目标来自同一张图）：\n{summary}"
            system_prompt = SYSTEM_PROMPT
        system_prompt += "\n请最终按四个清晰标题组织：识别与不确定性、现在怎么处理、后续怎么观察、何时咨询农技人员。结合生长阶段和用户自述程度，但不要把自述当作已证实事实。缺少信息时说明；不要据置信度推断虫害程度；建议保留引用编号。"
        if crop_hint:
            # 田间上下文放在最前面：大模型先知道作物，再读检测结果，
            # 用药部位与安全间隔期的口径才对得上（这是作物信息最稳的一份收益）
            head = f"【田间上下文】\n{crop_hint}\n\n{head}"
        # RAG：先按虫种名检索资料，再把带编号的资料段拼进用户消息
        refs = await self._retrieve(predictions, media_type)
        ref_text = self._format_refs(refs)
        user_msg = f"{head}\n\n{ref_text}" if ref_text else head
        # 打印给模型看的原文：口径出问题时（比如算出 0 帧检出）这是唯一的排查线索
        logger.info("DeepSeek input summary (%s): %s", media_type, summary.replace("\n", " | "))
        logger.info("RAG injected %d references", len(refs))
        try:
            resp = await self._get_client().chat.completions.create(
                model=self.settings.deepseek_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.3,
                max_tokens=1200,
                # 关闭思考模式：植保问答不需要链式推理，且思维链会挤占 max_tokens 导致正文被截断
                # 厂商私有的"关闭思考模式"参数，由 DEEPSEEK_THINKING_PARAM 决定；
                # 置空字符串则整个 extra_body 不发（纯非思考模型用）
                **self._thinking_kwargs(),
            )
            choice = resp.choices[0]
            content = (choice.message.content or "").strip()
            if choice.finish_reason == "length":
                # 截断时明确记日志：旧的 600 token 预算会让正文只剩几十字，
                # 表现为「AI 建议只给了一句话」，且不报错、极难发现
                logger.warning(
                    "DeepSeek analysis truncated: content=%s chars, max_tokens=%s",
                    len(content), 1200,
                )
            # 正文过短视为不可用：与其给用户半句话，不如降级让前端显示"建议生成失败"
            if len(content) < 60:
                logger.warning("DeepSeek analysis too short (%s chars), treat as failure", len(content))
                return None, []
            return content, refs
        except Exception as exc:  # noqa: BLE001 - LLM 是可选增强，任何失败都降级
            logger.warning("DeepSeek analysis failed: %s", exc)
            return None, []

    async def chat(
        self,
        detection_id: str,
        predictions: list[dict[str, Any]],
        media_type: str,
        user_message: str,
        db: AsyncSession,
    ) -> str | None:
        """多轮追问：基于一次检测结果，和用户连续对话。

        历史持久化在 chat_messages 表里，重启后端不丢。
        第一次提问时把检测结果作为上下文注入；后续提问带上数据库里的历史。
        """
        if not self.enabled:
            return None

        # 从数据库读历史（最多 20 条）
        rows = await db.scalars(
            select(ChatMessage)
            .where(ChatMessage.detection_id == detection_id)
            # 次级排序键必须是 id：同一轮对话里 user/assistant 两条消息时间戳
            # 完全相同（SQLite 的 CURRENT_TIMESTAMP 只到秒），只按时间倒排时
            # 顺序不确定，倒序后可能变成「 assistant 排在 user 之前」，
            # 送进模型的对话历史就错了。
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(20)
        )
        history = [{"role": m.role, "content": m.content} for m in list(reversed(rows.all()))]

        # 追问同样走检索：用户问「用什么药」「安全间隔期多久」时，
        # 不注入资料就只能靠模型参数记忆，而那部分不可控、也无法溯源
        ref_text = self._format_refs(
            await self._retrieve(predictions, media_type, extra_query=user_message)
        )

        if not history:
            # 首问：把检测结果作为上下文塞进第一条 user 消息
            events, flat = self._normalize(predictions, media_type)
            if media_type == "video":
                media_label = "一段视频"
                # 视频必须用事件口径汇总，否则会把「一个框」误算成「一个空帧」，
                # 模型拿到的上下文变成「0 帧检出」，回答就和界面对不上
                summary = self._summarize_video(events)
            else:
                media_label = "一张图片"
                summary = self._summarize(flat)
            user_content = (
                f"用户刚用系统识别了{media_label}，结果如下：\n{summary}\n"
                f"现在用户要基于这个结果提问。第一个问题是：{user_message}"
            )
        else:
            user_content = user_message
        if ref_text:
            user_content = f"{user_content}\n\n{ref_text}"

        history_for_llm = [
            {"role": "system", "content": CHAT_SYSTEM_PROMPT},
            *history,
            {"role": "user", "content": user_content},
        ]
        try:
            resp = await self._get_client().chat.completions.create(
                model=self.settings.deepseek_model,
                messages=history_for_llm,
                temperature=0.4,
                max_tokens=1000,
                # 厂商私有的"关闭思考模式"参数，由 DEEPSEEK_THINKING_PARAM 决定；
                # 置空字符串则整个 extra_body 不发（纯非思考模型用）
                **self._thinking_kwargs(),
            )
            choice = resp.choices[0]
            if choice.finish_reason == "length":
                logger.warning("DeepSeek chat truncated (finish_reason=length), consider raising max_tokens")
            content = (choice.message.content or "").strip()
            if content:
                # 落库的是**用户原话**，不是拼给模型的那一版。
                # 首问的 user_content 里塞了检测摘要 + 整份参考资料正文，
                # 如果原样入库，之后每一轮都会把这 20 条历史重新回传，
                # token 成本随轮次线性放大，而模型真正需要的只是"用户问了什么"。
                db.add(ChatMessage(detection_id=detection_id, role="user", content=user_message))
                db.add(ChatMessage(detection_id=detection_id, role="assistant", content=content))
                await db.commit()
                # 滚动裁剪：模型只看最近 20 条，但表里会一直堆。
                # 单条检测被反复追问几个月后，这张表能长到几万行，
                # 而老消息模型根本读不到——留着只是拖慢查询和撑大数据库。
                await _trim_chat_history(db, detection_id)
            return content or None
        except Exception as exc:  # noqa: BLE001
            logger.warning("DeepSeek chat failed: %s", exc)
            return None


llm = LLMAnalyzer()
