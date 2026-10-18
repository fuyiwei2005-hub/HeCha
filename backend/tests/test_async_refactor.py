"""Behavioral regressions for independent advice, bounded images and fenced jobs."""
import asyncio
import io
from datetime import timedelta
from threading import Event
from uuid import uuid4

import pytest
from arq import Retry
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import update

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.main import app
from app.models.detection import Detection
from app.services.admission import ImageAdmission
from app.services import image_detection
from app.services.files import save_video
from app.services.predictions import normalize_predictions
from app.services.analysis_jobs import finish_analysis, process_analysis, utcnow
from app.services.task_maintenance import dispatch_pending_videos, reconcile_tasks
from app.workers import video


@pytest.fixture(autouse=True)
def isolated_maintenance(monkeypatch):
    async def idle():
        await asyncio.Event().wait()
    monkeypatch.setattr("app.main.maintenance_loop", idle)


def login(client):
    name = f"refactor_{uuid4().hex[:12]}"
    password = "Test-password-123"
    assert client.post('/api/auth/register', json={'username': name, 'password': password}).status_code == 201
    token = client.post('/api/auth/login', data={'username': name, 'password': password}).json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def image_upload(client, headers):
    data = io.BytesIO()
    Image.new('RGB', (32, 32), 'green').save(data, 'PNG')
    return client.post('/api/detections/image', headers=headers,
                       files={'file': ('leaf.png', data.getvalue(), 'image/png')})


def enable_advice(monkeypatch):
    monkeypatch.setattr(get_settings(), 'deepseek_api_key', 'test-provider-key')
    def predict(content, output, rgb):
        Image.fromarray(rgb).save(output)
        return [{'class': 'aphid', 'class_cn': '蚜虫', 'confidence': .7,
                 'bbox': {'x1': 1, 'y1': 1, 'x2': 20, 'y2': 20}}]
    monkeypatch.setattr('app.services.image_detection.detector.predict_image', predict)


def test_upload_returns_before_advice_and_quota_is_independent(monkeypatch):
    enable_advice(monkeypatch)
    called = []
    async def unavailable(*args, **kwargs):
        called.append(True)
        raise RuntimeError('provider down')
    async def exhausted(user_id):
        raise HTTPException(429, 'quota exhausted')
    monkeypatch.setattr('app.services.analysis_jobs.llm.analyze', unavailable)
    monkeypatch.setattr('app.services.analysis_jobs.check_llm_quota', exhausted)
    with TestClient(app) as client:
        headers = login(client)
        response = image_upload(client, headers)
        assert response.status_code == 201
        body = response.json()
        assert body['status'] == 'completed' and body['analysis_status'] == 'queued'
        assert body['analysis'] is None and called == []
        async def process():
            async with SessionLocal() as db:
                item = await db.get(Detection, body['id'])
                attempt = item.analysis_attempt
            await process_analysis({}, body['id'], attempt)
        asyncio.run(process())
        finished = client.get(f"/api/detections/{body['id']}", headers=headers).json()
        assert finished['status'] == 'completed' and finished['analysis_status'] == 'failed'
        assert '上限' in finished['analysis_error'] and called == []
        assert client.get(f"/api/detections/{body['id']}/result", headers=headers).status_code == 200


def test_advice_failure_retry_is_idempotent_and_isolated(monkeypatch):
    enable_advice(monkeypatch)
    calls = []
    async def no_quota(user_id): pass
    async def analyze(*args, **kwargs):
        calls.append(1)
        return ('防治建议及参考资料', [{'ref': 1, 'title': '知识条目'}])
    monkeypatch.setattr('app.services.analysis_jobs.check_llm_quota', no_quota)
    monkeypatch.setattr('app.services.analysis_jobs.llm.analyze', analyze)
    with TestClient(app) as client:
        headers, other = login(client), login(client)
        body = image_upload(client, headers).json()
        async def fail():
            async with SessionLocal() as db:
                await db.execute(update(Detection).where(Detection.id == body['id']).values(analysis_status='failed'))
                await db.commit()
        asyncio.run(fail())
        assert client.post(f"/api/detections/{body['id']}/analysis", headers=other).status_code == 404
        first = client.post(f"/api/detections/{body['id']}/analysis", headers=headers)
        assert first.status_code == 202 and first.json()['analysis_status'] == 'queued'
        async def run():
            async with SessionLocal() as db:
                item = await db.get(Detection, body['id'])
                attempt = item.analysis_attempt
            # Duplicate delivery may never cause two provider calls.
            await asyncio.gather(process_analysis({}, body['id'], attempt), process_analysis({}, body['id'], attempt))
        asyncio.run(run())
        finished = client.get(f"/api/detections/{body['id']}", headers=headers).json()
        assert finished['analysis_status'] == 'completed' and finished['analysis']
        assert len(calls) == 1
        assert client.post(f"/api/detections/{body['id']}/analysis", headers=headers).json()['analysis_status'] == 'completed'


@pytest.mark.asyncio
async def test_advice_expiry_fences_late_completion():
    # Existing user id from a real account is obtained through the API.
    with TestClient(app) as client:
        headers = login(client)
        user_id = client.get('/api/auth/me', headers=headers).json()['id']
    did, attempt = str(uuid4()), str(uuid4())
    async with SessionLocal() as db:
        db.add(Detection(id=did, user_id=user_id, media_type='image', original_name='a.png',
                         stored_name=f'{did}.png', predictions=[], status='completed',
                         analysis_status='processing', analysis_attempt=attempt,
                         analysis_started_at=utcnow()-timedelta(minutes=10)))
        await db.commit()
    await reconcile_tasks()
    await finish_analysis(did, attempt, 'late result', [], None)
    async with SessionLocal() as db:
        item = await db.get(Detection, did)
        assert item.analysis_status == 'failed' and item.analysis is None


@pytest.mark.asyncio
async def test_image_queue_capacity_timeout_and_cancellation(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, 'image_concurrency', 1)
    monkeypatch.setattr(settings, 'image_queue_size', 1)
    monkeypatch.setattr(settings, 'image_queue_timeout_seconds', .05)
    gate = ImageAdmission()
    async with gate.slot():
        async def wait():
            async with gate.slot(): pass
        pending = asyncio.create_task(wait())
        await asyncio.sleep(0)
        with pytest.raises(HTTPException) as exc:
            async with gate.slot(): pass
        assert exc.value.status_code == 503
        with pytest.raises(HTTPException):
            await pending
        pending = asyncio.create_task(wait())
        await asyncio.sleep(0)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError): await pending
    # Cancellation and timeouts must return admission capacity.
    async with gate.slot(): pass


def test_video_outbox_preserves_two_uploads_during_redis_outage(monkeypatch):
    async def unavailable(): raise ConnectionError('Redis down')
    monkeypatch.setattr('app.services.task_maintenance.get_pool', unavailable)
    with TestClient(app) as client:
        headers = login(client)
        ids = []
        for _ in range(2):
            response = client.post('/api/videos', headers=headers,
                files={'file': ('clip.mp4', b'\0\0\0\x18ftypmp42\0\0\0\0mp42isom', 'video/mp4')})
            assert response.status_code == 202
            ids.append(response.json()['id'])
        with pytest.raises(ConnectionError): asyncio.run(dispatch_pending_videos())
        async def inspect():
            async with SessionLocal() as db:
                rows = [await db.get(Detection, did) for did in ids]
                assert len({row.stored_name for row in rows}) == 2
                assert all(row.status == 'queued' for row in rows)
                assert all((get_settings().upload_dir / row.stored_name).is_file() for row in rows)
        asyncio.run(inspect())


def test_get_does_not_expire_jobs():
    with TestClient(app) as client:
        headers = login(client)
        user_id = client.get('/api/auth/me', headers=headers).json()['id']
        did = str(uuid4())
        async def insert():
            async with SessionLocal() as db:
                db.add(Detection(id=did, user_id=user_id, media_type='video', original_name='a.mp4',
                    stored_name=f'{did}.mp4', status='queued', predictions=[], created_at=utcnow()-timedelta(hours=1)))
                await db.commit()
        asyncio.run(insert())
        assert client.get(f'/api/videos/{did}', headers=headers).json()['status'] == 'queued'
        asyncio.run(reconcile_tasks())
        assert client.get(f'/api/videos/{did}', headers=headers).json()['status'] == 'failed'


@pytest.mark.asyncio
async def test_video_expired_attempt_cannot_publish_or_delete_source(monkeypatch):
    with TestClient(app) as client:
        headers = login(client)
        body = client.post('/api/videos', headers=headers,
            files={'file': ('a.mp4', b'\0\0\0\x18ftypmp42\0\0\0\0mp42isom', 'video/mp4')}).json()
    async with SessionLocal() as db:
        item = await db.get(Detection, body['id'])
        source = get_settings().upload_dir / item.stored_name
    started, finish = Event(), Event()
    def render(source, target, stop):
        target.write_bytes(b'video-result')
        started.set()
        assert finish.wait(3)
        return [], {'sampled_frames': 1}
    monkeypatch.setattr(video, 'render_video', render)
    monkeypatch.setattr(video, 'transcode_to_h264', lambda p: True)
    task = asyncio.create_task(video.process_video({'job_try': 1}, body['id'], str(source)))
    assert await asyncio.to_thread(started.wait, 3)
    async with SessionLocal() as db:
        await db.execute(update(Detection).where(Detection.id == body['id']).values(
            heartbeat_at=utcnow()-timedelta(minutes=10)))
        await db.commit()
    await reconcile_tasks()
    finish.set()
    await task
    async with SessionLocal() as db:
        item = await db.get(Detection, body['id'])
        assert item.status == 'failed' and item.result_path is None
    assert source.is_file()
    assert not list(get_settings().result_dir.glob(f"{body['id']}-*.mp4"))


@pytest.mark.asyncio
async def test_video_retry_retains_source_and_can_finish(monkeypatch):
    with TestClient(app) as client:
        headers = login(client)
        body = client.post('/api/videos', headers=headers,
            files={'file': ('a.mp4', b'\0\0\0\x18ftypmp42\0\0\0\0mp42isom', 'video/mp4')}).json()
    async with SessionLocal() as db:
        item = await db.get(Detection, body['id'])
        source = get_settings().upload_dir / item.stored_name
    def fail(*args): raise ValueError('transient decoder failure')
    monkeypatch.setattr(video, 'render_video', fail)
    with pytest.raises(Retry): await video.process_video({'job_try': 1}, body['id'], str(source))
    assert source.is_file()
    def success(source, target, stop):
        target.write_bytes(b'finished')
        return [], {'sampled_frames': 1}
    monkeypatch.setattr(video, 'render_video', success)
    monkeypatch.setattr(video, 'transcode_to_h264', lambda p: True)
    await video.process_video({'job_try': 2}, body['id'], str(source))
    async with SessionLocal() as db:
        item = await db.get(Detection, body['id'])
        assert item.status == 'completed' and item.error is None
        assert (get_settings().result_dir / item.result_path).is_file()
    assert not source.exists()


@pytest.mark.asyncio
async def test_waiting_images_are_not_decoded_and_cancelled_inference_cleans_files(monkeypatch):
    from fastapi import UploadFile
    from starlette.datastructures import Headers
    settings = get_settings()
    monkeypatch.setattr(settings, 'image_concurrency', 1)
    monkeypatch.setattr(settings, 'image_queue_size', 1)
    monkeypatch.setattr(image_detection, 'image_admission', ImageAdmission())
    started, finish = Event(), Event()
    decode_calls = []
    original_read = image_detection.read_image
    async def read(*args):
        decode_calls.append(1)
        return await original_read(*args)
    def infer(content, target, rgb):
        started.set()
        assert finish.wait(3)
        Image.fromarray(rgb).save(target)
        return []
    monkeypatch.setattr(image_detection, 'read_image', read)
    monkeypatch.setattr(image_detection.detector, 'predict_image', infer)
    with TestClient(app) as client:
        headers = login(client)
        user_id = client.get('/api/auth/me', headers=headers).json()['id']
    before_uploads = set(settings.upload_dir.iterdir())
    before_results = set(settings.result_dir.iterdir())
    data = io.BytesIO()
    Image.new('RGB', (128, 128), 'green').save(data, 'PNG')
    async def upload():
        file = UploadFile(io.BytesIO(data.getvalue()), filename='a.png', headers=Headers({'content-type': 'image/png'}))
        async with SessionLocal() as db:
            return await image_detection.detect_image(file, None, user_id, db)
    first = asyncio.create_task(upload())
    assert await asyncio.to_thread(started.wait, 3)
    second = asyncio.create_task(upload())
    await asyncio.sleep(.02)
    assert len(decode_calls) == 1, 'Queued request decoded before admission'
    second.cancel()
    with pytest.raises(asyncio.CancelledError): await second
    first.cancel()
    await asyncio.sleep(.02)
    assert not first.done(), 'Cancelled request released files while inference still uses them'
    finish.set()
    with pytest.raises(asyncio.CancelledError): await first
    assert set(settings.upload_dir.iterdir()) == before_uploads
    assert set(settings.result_dir.iterdir()) == before_results


@pytest.mark.asyncio
async def test_oversize_video_closes_file_before_cleanup(tmp_path):
    from fastapi import UploadFile
    from starlette.datastructures import Headers
    file = UploadFile(io.BytesIO(b'x' * 2048), filename='a.mp4', headers=Headers({'content-type': 'video/mp4'}))
    with pytest.raises(HTTPException) as exc:
        await save_video(file, tmp_path, 1024)
    assert exc.value.status_code == 413
    assert list(tmp_path.iterdir()) == []


def test_historical_weighted_scores_are_not_exposed_as_probability():
    old = [{'class': 'pest', 'confidence': 1.15, 'raw_confidence': .92}]
    response = normalize_predictions(old, 'image')[0]
    assert response['confidence'] == .92 and response['ranking_score'] == 1.15
    assert old[0]['confidence'] == 1.15, 'History must not be mutated'
