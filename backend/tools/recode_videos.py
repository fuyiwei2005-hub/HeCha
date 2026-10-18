"""把历史遗留的 mp4v(FMP4) 结果视频批量转成 H.264。

OpenCV 写出来的 mp4v 容器，浏览器 <video> 直接拒播，用户界面上就是
「格式不受浏览器支持或文件已被清理」。新产出的视频已经走 ffmpeg 转码，
这里只扫存量，把还没转的补上。
"""
import sys
from pathlib import Path

import cv2

from app.core.config import get_settings
from app.services.ffmpeg import ffmpeg_available, transcode_to_h264

BROWSER_OK = {"h264", "avc1", "x264", "hev1", "hvc1"}


def fourcc_tag(path: Path) -> str:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return "?"
    code = int(cap.get(cv2.CAP_PROP_FOURCC))
    cap.release()
    return "".join(chr((code >> (8 * i)) & 0xFF) for i in range(4))


def main() -> int:
    settings = get_settings()
    result_dir: Path = settings.result_dir
    if not ffmpeg_available():
        print("ffmpeg 不可用，跳过")
        return 1

    files = sorted(result_dir.glob("*.mp4"))
    print(f"扫描 {result_dir}，共 {len(files)} 个结果视频")
    fixed = skipped = failed = 0
    for f in files:
        tag = fourcc_tag(f)
        if tag.lower().startswith(tuple(BROWSER_OK)) or tag.lower() in BROWSER_OK:
            skipped += 1
            continue
        before = f.stat().st_size
        print(f"  转码 {f.name}: {tag} ({before//1024}KB) ...", end=" ", flush=True)
        try:
            ok = transcode_to_h264(f)
        except Exception as exc:  # noqa: BLE001
            print(f"失败 {exc}")
            failed += 1
            continue
        if ok:
            print(f"完成 → {fourcc_tag(f)} ({f.stat().st_size//1024}KB)")
            fixed += 1
        else:
            print("ffmpeg 返回失败")
            failed += 1
    print(f"\n结果：已修复 {fixed}，原本正常 {skipped}，失败 {failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
