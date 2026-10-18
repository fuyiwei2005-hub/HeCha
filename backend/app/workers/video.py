import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from contextlib import suppress
from threading import Event
from uuid import uuid4
from sqlalchemy import update
from app.services.admission import run_blocking
from app.services.analysis_jobs import analysis_request, utcnow

import cv2
from arq import Retry
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.detection import Detection
from app.services.annotate import draw_labels
from app.services.detector import detector
from app.services.ffmpeg import transcode_to_h264
from app.services.video_progress import VideoControl


logger = logging.getLogger(__name__)
settings = get_settings()

# 抽帧目标：每秒抽样帧数。原先按 fps/5 取（5fps），2 秒视频只有 10 个采样点，
# 且采样点会随 fps 取整而漂移（实测出现 1042ms → 2500ms 的空档，中间 1.5 秒完全没看），
# 表现为「结果给的不全」。这里改为按固定时间间隔抽样，与 fps 解耦：
#   - 采样间隔 = 1000 / sample_fps 毫秒，采样点严格等距，全片均匀覆盖；
#   - 上限保护：避免长视频把推理帧数放大到不可接受。
SAMPLE_FPS = 8
MIN_SAMPLE_INTERVAL_MS = 1000 / SAMPLE_FPS
MAX_SAMPLED_FRAMES = 3000
# 短视频直接逐帧全检：参赛演示的视频大多在十几秒内，抽帧反而会让人觉得「漏掉了」。
# 超过这个帧数才退回抽样，保证长视频不会把 worker 拖死。
FULL_SCAN_MAX_FRAMES = 300


def render_video(source: Path, target: Path, stop: Event | None = None) -> tuple[list[dict], dict]:
    """逐帧推理并渲染标注视频。

    返回 (events, meta)：
    - events：每个采样点的 {time_ms, detections}，按时间升序；
    - meta：抽帧统计，写进日志与前端提示，便于判断结果是否完整。
    """
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise ValueError("Invalid or unsupported video")

    fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration_ms = round(total_frames / fps * 1000) if total_frames else 0

    # 等距采样：每 sample_stride 帧取一帧，而不是靠 frame_index % (fps/5) 的取整
    full_scan = bool(total_frames) and total_frames <= FULL_SCAN_MAX_FRAMES
    sample_stride = 1 if full_scan else max(1, round(fps / SAMPLE_FPS))
    sampled_count = (total_frames // sample_stride) + 1 if total_frames else 0
    truncated = sampled_count > MAX_SAMPLED_FRAMES
    if truncated:
        # 视频过长时自动放宽间隔，保证采样总数可控
        sample_stride = max(1, -(-total_frames // MAX_SAMPLED_FRAMES))
        sampled_count = total_frames // sample_stride + 1
        logger.info("video too long (%s frames), widen stride to %s", total_frames, sample_stride)

    writer = cv2.VideoWriter(
        str(target), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height)
    )
    if not writer.isOpened():
        capture.release()
        raise ValueError("Failed to open video writer")

    report = getattr(stop, 'report', lambda *args: None)
    report('detecting', 0, total_frames)
    last_report = 0.0
    events: list[dict] = []
    frame_index = 0
    sampled = 0
    annotated = 0
    # 抽样模式下保留上一次的框并画到后续每一帧：否则输出视频里框只在 8fps 的
    # 采样点上出现，播放时一闪一闪，看着就像「识别不全」。
    last_predictions: list[dict] = []
    try:
        while True:
            if stop is not None and stop.is_set():
                raise RuntimeError("Video processing cancelled")
            ok, frame = capture.read()
            if not ok:
                break
            if frame_index % sample_stride == 0:
                sampled += 1
                # 直接用内存中的帧做推理：原先要 encode 成 JPEG 再解码、
                # 生成一张用完即弃的标注图写盘后删除，实测每帧多花约 36% 时间
                last_predictions = detector.predict_frame(frame)
                if last_predictions:
                    events.append(
                        {"time_ms": round(frame_index / fps * 1000), "detections": last_predictions}
                    )
            if last_predictions:
                frame = draw_labels(frame, last_predictions)
                annotated += 1
            writer.write(frame)
            frame_index += 1
            now = time.monotonic()
            if now - last_report >= .25:
                report('detecting', frame_index, total_frames)
                last_report = now
    finally:
        capture.release()
        writer.release()

    report('converting', frame_index, total_frames)
    meta = {
        "fps": round(fps, 2),
        "total_frames": total_frames,
        "duration_ms": duration_ms,
        "sample_stride": sample_stride,
        "full_scan": full_scan,
        "sampled_frames": sampled,
        "annotated_frames": annotated,
        "event_count": len(events),
        "truncated": truncated,
    }
    return events, meta


async def _save_progress(detection_id, attempt, stop):
    async with SessionLocal() as db:
        result = await db.execute(update(Detection).where(
            Detection.id == detection_id, Detection.status == 'processing',
            Detection.job_attempt == attempt,
        ).values(heartbeat_at=utcnow(), video_meta={'progress': stop.snapshot()}))
        await db.commit()
        return bool(result.rowcount)


async def _heartbeat(detection_id, attempt, stop):
    while True:
        await asyncio.sleep(2)
        if not await _save_progress(detection_id, attempt, stop):
            stop.set()
            return


async def process_video(ctx, detection_id: str, source_path: str):
    source = Path(source_path)
    attempt = str(uuid4())
    target = settings.result_dir / f"{detection_id}-{attempt}.mp4"
    async with SessionLocal() as db:
        claimed = await db.execute(update(Detection).where(
            Detection.id == detection_id, Detection.status == "queued",
        ).values(status="processing", job_attempt=attempt, heartbeat_at=utcnow(), error=None, video_meta={'progress': {'stage': 'starting'}}))
        await db.commit()
        if not claimed.rowcount:
            # Duplicate delivery, expired attempt or deleted record cannot run again.
            if await db.get(Detection, detection_id) is None:
                source.unlink(missing_ok=True)
            return

    stop = VideoControl()
    heartbeat = asyncio.create_task(_heartbeat(detection_id, attempt, stop))
    published = False
    try:
        render = asyncio.create_task(asyncio.to_thread(render_video, source, target, stop))
        try:
            events, meta = await asyncio.shield(render)
        except asyncio.CancelledError:
            stop.set()
            with suppress(Exception):
                await render
            raise
        if stop.is_set():
            return
        stop.report('converting', meta.get('total_frames', 0), meta.get('total_frames', 0))
        async with SessionLocal() as db:
            await db.execute(update(Detection).where(Detection.id == detection_id,
                Detection.status == 'processing', Detection.job_attempt == attempt
            ).values(video_meta={**meta, 'progress': stop.snapshot()}, heartbeat_at=utcnow()))
            await db.commit()
        meta["h264"] = await run_blocking(transcode_to_h264, target)
        async with SessionLocal() as db:
            result = await db.execute(update(Detection).where(
                Detection.id == detection_id, Detection.status == "processing",
                Detection.job_attempt == attempt,
            ).values(predictions=events, video_meta=meta, result_path=target.name,
                     status="completed", error=None, **analysis_request(events)))
            await db.commit()
            published = bool(result.rowcount)
        if published:
            source.unlink(missing_ok=True)
    except (Exception, asyncio.CancelledError) as exc:
        retry = int(ctx.get("job_try", 1) or 1) < WorkerSettings.max_tries
        async with SessionLocal() as db:
            changed = await db.execute(update(Detection).where(
                Detection.id == detection_id, Detection.status == "processing",
                Detection.job_attempt == attempt,
            ).values(status="queued" if retry else "failed", job_attempt=None,
                     heartbeat_at=utcnow(), error="视频处理暂时失败，正在重试" if retry else "视频处理失败，请重新提交"))
            await db.commit()
        if isinstance(exc, asyncio.CancelledError):
            raise
        if retry and changed.rowcount:
            raise Retry(defer=timedelta(seconds=5)) from exc
        if changed.rowcount:
            raise
    finally:
        stop.set()
        heartbeat.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat
        if not published:
            target.unlink(missing_ok=True)
            async with SessionLocal() as db:
                if await db.get(Detection, detection_id) is None:
                    source.unlink(missing_ok=True)


class WorkerSettings:
    functions = [process_video]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 1
    # 30 分钟过长：worker 卡死单任务时，这条任务会一直占着唯一的 worker 槽
    # （max_jobs=1），后面排队的视频全部干等。10 分钟对百 MB 内的视频足够。
    #
    # 不变式：这个值必须**大于** ffmpeg.TRANSCODE_TIMEOUT，
    # 因为 job 除了转码还要解码、抽帧、推理、写盘。
    # 两边相等时会在最后一刻双输（job 超时删源文件，ffmpeg 还在写目标）。
    job_timeout = 60 * 10
    max_tries = 2
    # API 从不读取 ARQ 的任务结果（状态全在数据库里），
    # 保留 1 小时只是白占 Redis 内存。
    keep_result = 0

    @staticmethod
    async def on_startup(ctx) -> None:
        """Worker 一启动就把模型跑热。

        Worker 跑在独立进程里，API 那边的预热对它无效。不预热的话，
        每个视频的**第一帧**都要承担加载权重的开销，会被算进 job_timeout，
        长视频更容易超时。
        """
        elapsed = await asyncio.to_thread(detector.warmup)
        if elapsed:
            logger.info("[worker] detector warmed up in %.2fs", elapsed)

    @staticmethod
    async def on_shutdown(ctx) -> None:
        # 进程退出前释放连接池，避免 SQLite 留下 -wal/-shm 残留文件
        from app.core.database import engine

        await engine.dispose()
