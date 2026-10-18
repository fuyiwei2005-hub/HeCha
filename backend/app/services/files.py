import io
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

import numpy as np
from app.services.admission import run_blocking


IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
VIDEO_TYPES = {"video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov"}

# 文件头特征。MP4/MOV 是 ISOBMFF：第 4 字节起是 ftyp box，
# WebM/Matroska 以 EBML 魔数 1A45DFA3 开头。认 box 不认扩展名。
VIDEO_MAGIC: dict[str, tuple[bytes, ...]] = {
    ".mp4": (b"ftyp",),
    ".mov": (b"ftyp", b"moov"),
    ".webm": (b"\x1a\x45\xdf\xa3",),
}


def _decode_and_validate(content: bytes, max_pixels: int) -> "np.ndarray":
    """解码并校验图片，返回 RGB 数组。

    纯 CPU 操作，25MP 的图要几百毫秒 —— 直接在 async 函数体里跑会把事件循环
    按住，期间所有请求（连健康检查）都得排队。调用方必须用 asyncio.to_thread
    包起来。

    **返回解码结果**（而不是 None）：推理侧需要同一份像素。
    之前这里是 `image.load()` 之后就丢掉，detector.predict_image 又用同一份
    bytes 解码了第二次 —— 项目自己的注释都写了"25MP 的图要几百毫秒"，
    等于每张图白付一次整图解码 + RGB 转换。
    """
    probe = Image.open(io.BytesIO(content))
    probe.verify()          # 校验文件结构（会消耗文件对象，所以要重新打开）
    image = Image.open(io.BytesIO(content))
    if image.width * image.height > max_pixels:
        raise HTTPException(413, "Image dimensions are too large")
    image = image.convert("RGB")
    image.load()            # 真正解码，把损坏数据挡在这一步，而不是留到推理时才炸
    return np.asarray(image)


async def read_image(
    file: UploadFile, limit: int, max_pixels: int, directory: Path
) -> tuple[bytes, str, "np.ndarray"]:
    """读取并校验上传图片。

    返回 (原始字节, 落盘文件名, RGB 数组)。数组直接透传给检测器，
    避免重复解码。
    """
    if file.content_type not in IMAGE_TYPES:
        raise HTTPException(415, "Only JPEG, PNG and WebP images are accepted")
    content = await file.read(limit + 1)
    if not content:
        raise HTTPException(422, "The uploaded image is empty")
    if len(content) > limit:
        raise HTTPException(413, "Image is too large")
    try:
        rgb = await run_blocking(_decode_and_validate, content, max_pixels)
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise HTTPException(422, "The uploaded file is not a valid image")
    stored_name = f"{uuid4().hex}{IMAGE_TYPES[file.content_type]}"
    # 原图落盘，便于复检与二次处理（与视频分支行为一致）
    target = directory / stored_name
    try:
        await run_blocking(target.write_bytes, content)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return content, stored_name, rgb


async def save_video(file: UploadFile, directory: Path, limit: int) -> tuple[Path, str]:
    if file.content_type not in VIDEO_TYPES:
        raise HTTPException(415, "Only MP4, WebM and MOV videos are accepted")
    stored_name = f"{uuid4().hex}{VIDEO_TYPES[file.content_type]}"
    target = (directory / stored_name).resolve()
    if directory.resolve() not in target.parents:
        raise HTTPException(400, "Invalid target path")
    try:
        size = 0
        with target.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, "Video is too large")
                await run_blocking(output.write, chunk)
        if size == 0:
            raise HTTPException(422, "The uploaded video is empty")
        with target.open("rb") as handle:
            header = handle.read(12)
        expected = VIDEO_MAGIC[VIDEO_TYPES[file.content_type]]
        if not any(mark in header for mark in expected):
            raise HTTPException(422, "The uploaded file is not a valid video")
    except BaseException:
        # The handle is closed before unlink, including Windows and cancellation.
        target.unlink(missing_ok=True)
        raise
    return target, stored_name
