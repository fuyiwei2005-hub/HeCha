"""Image use case: admission, validation, inference, persistence, deferred advice."""
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from app.core.config import get_settings
from app.models.detection import Detection
from app.services.admission import image_admission, run_blocking
from app.services.analysis_jobs import analysis_request, utcnow
from app.services.detector import detector
from app.services.files import read_image
from app.services.host_prior import host_prior


async def detect_image(file, crop, user_id, db, observation=None):
    settings = get_settings()
    crop = host_prior.resolve_crop(crop.strip()) if crop and crop.strip() else None
    stored_name = None
    result_path = None
    committed = False
    try:
        async with image_admission.slot():
            content, stored_name, rgb = await read_image(
                file, settings.max_image_bytes, settings.max_image_pixels, settings.upload_dir,
            )
            result_name = f"{Path(stored_name).stem}.jpg"
            result_path = settings.result_dir / result_name
            try:
                predictions = await run_blocking(detector.predict_image, content, result_path, rgb)
            except RuntimeError as exc:
                raise HTTPException(503, str(exc)) from exc
            # Release the full image before the next request enters the gate.
            from app.services.observation import assess_image
            quality = await run_blocking(assess_image, rgb, predictions)
            del content, rgb
        predictions = host_prior.rerank(predictions, crop).predictions
        item = Detection(
            id=str(uuid4()), user_id=user_id, media_type="image", status="completed",
            original_name=(file.filename or "image")[:255], stored_name=stored_name,
            predictions=predictions, result_path=result_name, crop=crop,
            created_at=utcnow(), observation=observation, quality=quality,
            **analysis_request(predictions),
        )
        db.add(item)
        await db.commit()
        committed = True
        await db.refresh(item)
        return item
    except BaseException:
        # Cancellation also owns temporary files. A refresh failure after commit
        # must not delete media belonging to an already-persisted detection.
        if not committed:
            await db.rollback()
            if stored_name:
                (settings.upload_dir / stored_name).unlink(missing_ok=True)
            if result_path:
                result_path.unlink(missing_ok=True)
        raise
