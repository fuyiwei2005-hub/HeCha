from app.models.detection import Detection
from datetime import timezone
from app.schemas.detection import DetectionResponse
from app.services.predictions import normalize_predictions
from app.services.video_progress import serialized_progress


def serialize(item: Detection) -> DetectionResponse:
    return DetectionResponse(
        id=item.id, media_type=item.media_type, original_name=item.original_name,
        status=item.status, crop=item.crop, predictions=normalize_predictions(item.predictions, item.media_type),
        video_meta=item.video_meta, progress=serialized_progress(item),
        result_url=f"/api/detections/{item.id}/result" if item.result_path else None,
        analysis=item.analysis, references=item.references, error=item.error, feedback=item.feedback,
        observation=item.observation, quality=item.quality, feedback_note=item.feedback_note,
        analysis_status=item.analysis_status, analysis_error=item.analysis_error,
        created_at=item.created_at.replace(tzinfo=timezone.utc) if item.created_at.tzinfo is None else item.created_at,
    )
