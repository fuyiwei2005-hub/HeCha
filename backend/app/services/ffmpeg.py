"""H.264 转码封装。

背景：`cv2.VideoWriter` 配 `fourcc('mp4v')` 输出的是 MPEG-4 Part 2（fourcc 探测为 `FMP4`），
主流浏览器 `<video>` 标签**不支持**这个编码，视频会直接报「格式不受浏览器支持」。
OpenCV 在本环境也编不出 H.264（未编译 libx264 支持），所以必须用 ffmpeg 转一道。

ffmpeg 来源优先级：
1. 环境变量 `FFMPEG_BINARY` 指定的路径；
2. `imageio-ffmpeg` 包自带的二进制（项目依赖里已有，随 venv 分发，无需系统安装）；
3. 系统 PATH 里的 ffmpeg。

三者都拿不到时返回 None，调用方降级为保留 mp4v 输出并标注，前端据此给提示，
而不是抛异常让整个任务失败。
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

# 转码超时。这个值**必须显著小于** WorkerSettings.job_timeout（600s）：
# 一个视频任务除了转码，还要解码、抽帧、推理、写盘。
# 两边都设 600s 时，ffmpeg 慢的情况下 subprocess 与 ARQ 看门狗会同时到点 ——
# job 判超时删掉源文件，而 ffmpeg 还在往目标写，结果是半成品 mp4 + failed 记录。
TRANSCODE_TIMEOUT = 60 * 3


@lru_cache(maxsize=1)
def find_ffmpeg() -> str | None:
    """定位可用的 ffmpeg 可执行文件；找不到返回 None。"""
    explicit = os.environ.get("FFMPEG_BINARY", "").strip()
    if explicit and Path(explicit).is_file():
        return explicit

    try:
        import imageio_ffmpeg  # type: ignore[import-not-found]

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).is_file():
            return exe
    except Exception as exc:  # noqa: BLE001 - 缺失即降级，不该影响主流程
        logger.debug("imageio-ffmpeg unavailable: %s", exc)

    found = shutil.which("ffmpeg")
    if found:
        return found
    return None


def ffmpeg_available() -> bool:
    return find_ffmpeg() is not None


def transcode_to_h264(source: Path, *, crf: int = 23, preset: str = "veryfast") -> bool:
    """把 source 原地转成 H.264 + yuv420p + faststart。

    成功返回 True（source 被替换为新文件）；失败返回 False，且**保证原文件不被破坏**
    （先写临时文件，转码成功才替换，任何异常都清理临时文件）。

    - `preset="veryfast"`：演示视频只有几十秒，且 worker 是单并发
      （max_jobs=1），medium 档慢 3–5 倍却看不出画质差别，
      还更容易撞上 job_timeout。这里选快的那档。
    - `crf=23`：默认质量，肉眼无损。
    - `yuv420p`：浏览器兼容性最好的像素格式，缺了它部分浏览器仍会黑屏；
    - `+faststart`：把 moov box 前移，使视频可以边下边播而不是等整个文件加载完。
    """
    exe = find_ffmpeg()
    if exe is None:
        logger.warning("ffmpeg not found, keep original encoding for %s", source.name)
        return False
    if not source.is_file():
        return False

    # 同目录下建临时文件，保证最终 replace 是同盘原子操作
    fd, tmp_name = tempfile.mkstemp(suffix=".mp4", dir=str(source.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        result = subprocess.run(
            [
                exe,
                "-y",
                "-loglevel", "error",
                "-i", str(source),
                "-c:v", "libx264",
                "-preset", preset,
                "-crf", str(crf),
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                "-an",                       # 识别结果视频不需要音轨
                str(tmp),
            ],
            capture_output=True,
            text=True,
            timeout=TRANSCODE_TIMEOUT,
        )
        if result.returncode != 0 or not tmp.is_file() or tmp.stat().st_size == 0:
            logger.warning("ffmpeg transcode failed for %s: %s",
                           source.name, (result.stderr or "")[-400:])
            return False

        # 转码成功才替换原文件
        tmp.replace(source)
        return True
    except subprocess.TimeoutExpired:
        logger.warning("ffmpeg transcode timed out for %s", source.name)
        return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("ffmpeg transcode error for %s: %s", source.name, exc)
        return False
    finally:
        tmp.unlink(missing_ok=True)


@lru_cache(maxsize=1)
def supports_h264() -> bool:
    """探测本机 ffmpeg 是否带 libx264 编码器。"""
    exe = find_ffmpeg()
    if exe is None:
        return False
    try:
        r = subprocess.run([exe, "-hide_banner", "-encoders"],
                           capture_output=True, text=True, timeout=20)
        return "libx264" in r.stdout
    except Exception:  # noqa: BLE001
        return False
