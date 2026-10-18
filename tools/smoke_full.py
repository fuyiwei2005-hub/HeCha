"""Deterministic integration server; synthetic detector/provider, isolated database.

Never import this module in production. It exercises the real API, persistence,
workers and frontend without calling a paid provider or loading the model.
"""
import asyncio
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
(ROOT / 'output').mkdir(parents=True, exist_ok=True)
if os.environ.get('HECHA_SMOKE_DIR'):
    DATA = Path(os.environ['HECHA_SMOKE_DIR']).resolve()
    if not DATA.is_relative_to((ROOT / 'output').resolve()):
        raise RuntimeError('Smoke data must stay inside output')
    DATA.mkdir(parents=True, exist_ok=True)
else:
    DATA = Path(tempfile.mkdtemp(prefix='full-ui-smoke-', dir=ROOT / 'output'))
os.environ['DATABASE_URL'] = f'sqlite+aiosqlite:///{(DATA / "smoke.db").as_posix()}'
os.environ['UPLOAD_DIR'] = str(DATA / 'uploads')
os.environ['RESULT_DIR'] = str(DATA / 'results')
os.environ['TASK_BACKEND'] = 'local'
os.environ['MODEL_PATH'] = ''
os.environ['ALLOW_MOCK_DETECTOR'] = 'true'
os.environ['DEEPSEEK_API_KEY'] = 'synthetic-smoke-provider'
os.environ['SECRET_KEY'] = 'smoke-test-isolated-session-signing-key-2026'
sys.path.insert(0, str(ROOT / 'backend'))

from PIL import Image
from sqlalchemy import select
import app.main as main
from app.core.database import SessionLocal
from app.models.detection import Detection
from app.models.chat_message import ChatMessage
from app.services.analysis_jobs import process_analysis
import app.services.analysis_jobs as analysis_jobs
from app.workers.video import process_video
from app.services.detector import detector
from app.services.llm import llm
from app.services.task_maintenance import reconcile_tasks


def prediction():
    return [{'class': 'aphid', 'class_cn': '蚜虫', 'confidence': .72,
             'bbox': {'x1': 2, 'y1': 2, 'x2': 20, 'y2': 20}}]


def predict_image(content, target, rgb):
    Image.fromarray(rgb).save(target)
    return prediction()


detector.predict_image = predict_image
def predict_frame(frame):
    delay = float(os.environ.get('HECHA_SMOKE_FRAME_DELAY', '0'))
    if delay: time.sleep(min(delay, .2))
    return prediction()
detector.predict_frame = predict_frame
calls = 0


async def analyze(*args, **kwargs):
    global calls
    await asyncio.sleep(.4)
    calls += 1
    if calls == 1:
        return None, []
    return '这是浏览器集成测试的模拟防治建议。请结合田间观察核对虫体特征，参考资料见[1]。', [
        {'ref': 1, 'title': '集成测试参考条目', 'source': '测试知识库', 'body': '模拟资料，仅用于验证界面。'}]


async def chat(detection_id, predictions, media_type, message, db):
    reply = '这是集成测试的模拟追问回答。'
    db.add_all([ChatMessage(detection_id=detection_id, role='user', content=message),
                ChatMessage(detection_id=detection_id, role='assistant', content=reply)])
    await db.commit()
    return reply


async def no_quota(user_id): pass


llm.analyze = analyze
llm.chat = chat
analysis_jobs.check_llm_quota = no_quota


async def maintenance():
    while True:
        await reconcile_tasks()
        async with SessionLocal() as db:
            advice = (await db.execute(select(Detection.id, Detection.analysis_attempt).where(
                Detection.analysis_status == 'queued'))).all()
            videos = (await db.execute(select(Detection.id, Detection.stored_name).where(
                Detection.status == 'queued', Detection.media_type == 'video'))).all()
        for did, attempt in advice: await process_analysis({}, did, attempt)
        for did, name in videos: await process_video({'job_try': 1}, did, str(DATA / 'uploads' / name))
        await asyncio.sleep(.3)



app = main.app


if __name__ == '__main__':
    from alembic import command
    from alembic.config import Config
    os.chdir(ROOT / 'backend')
    command.upgrade(Config('alembic.ini'), 'head')
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=int(sys.argv[1]) if len(sys.argv) > 1 else 8137)
