"""Bound decoded images and queued requests within each API process."""
import asyncio
from contextlib import asynccontextmanager
from weakref import WeakKeyDictionary

from fastapi import HTTPException
from app.core.config import get_settings


class ImageAdmission:
    def __init__(self):
        self._loops = WeakKeyDictionary()

    @asynccontextmanager
    async def slot(self):
        settings = get_settings()
        loop = asyncio.get_running_loop()
        state = self._loops.setdefault(loop, [asyncio.Semaphore(settings.image_concurrency), 0])
        # No await between checking and incrementing: atomic on this event loop.
        if state[1] >= settings.image_concurrency + settings.image_queue_size:
            raise HTTPException(503, "检测队列已满，请稍后重试", headers={"Retry-After": "5"})
        state[1] += 1
        acquired = False
        try:
            try:
                await asyncio.wait_for(state[0].acquire(), settings.image_queue_timeout_seconds)
            except TimeoutError:
                raise HTTPException(503, "等待检测超时，请稍后重试", headers={"Retry-After": "5"})
            acquired = True
            yield
        finally:
            if acquired:
                state[0].release()
            state[1] -= 1


async def run_blocking(function, *args):
    """Keep ownership of files/memory until a cancelled thread has stopped."""
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        try:
            await task
        except Exception:
            pass
        raise


image_admission = ImageAdmission()
