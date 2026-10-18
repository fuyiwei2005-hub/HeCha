"""Small thread-safe progress snapshot; persistence remains attempt-fenced."""
from threading import Event, Lock
from app.core.config import get_settings

class VideoControl(Event):
    def __init__(self):
        super().__init__()
        self._lock = Lock()
        self._progress = {'stage': 'starting', 'processed_frames': 0, 'total_frames': 0, 'percent': None}

    def report(self, stage, processed_frames=0, total_frames=0):
        with self._lock:
            self._progress = {'stage': stage, 'processed_frames': processed_frames,
                              'total_frames': total_frames,
                              'percent': min(100, int(processed_frames * 100 / total_frames)) if total_frames else None}

    def snapshot(self):
        with self._lock:
            return dict(self._progress)


def serialized_progress(item):
    if item.media_type != 'video': return None
    meta = item.video_meta or {}
    progress = dict(meta.get('progress') or {})
    if item.status == 'completed':
        progress.update(stage='completed', percent=100,
                        processed_frames=meta.get('total_frames', 0), total_frames=meta.get('total_frames', 0))
    elif item.status == 'queued':
        progress.update(stage='queued', processed_frames=0, total_frames=0, percent=None)
    elif item.status == 'failed':
        progress['stage'] = 'failed'
    else:
        progress.setdefault('stage', 'starting')
    # Only failed videos whose source is retained can be retried without an upload.
    progress['can_retry'] = item.status == 'failed' and bool(item.stored_name) and (get_settings().upload_dir / item.stored_name).is_file()
    return progress
