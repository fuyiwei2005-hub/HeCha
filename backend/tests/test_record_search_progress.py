import asyncio
from datetime import datetime, timedelta, timezone
from threading import Event
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from app.main import app
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.detection import Detection
from app.services.analysis_jobs import utcnow
from app.services.video_progress import VideoControl
from app.workers import video

@pytest.fixture(autouse=True)
def no_background_tasks(monkeypatch):
    async def idle(): await asyncio.Event().wait()
    monkeypatch.setattr('app.main.maintenance_loop', idle)

def account(client):
    name = 'paging_'+uuid4().hex[:12]
    assert client.post('/api/auth/register',json={'username':name,'password':'Test-password-123'}).status_code == 201
    token = client.post('/api/auth/login',data={'username':name,'password':'Test-password-123'}).json()['access_token']
    headers = {'Authorization':'Bearer '+token}
    return headers,client.get('/api/auth/me',headers=headers).json()['id']

async def populate(user_id):
    base = datetime(2026,1,1,tzinfo=timezone.utc)
    async with SessionLocal() as db:
        for i in range(125):
            did = str(uuid4())
            db.add(Detection(id=did,user_id=user_id,media_type='video' if i%2 else 'image',
                original_name=f'leaf_{i:03}.png',stored_name=did+'.png',
                status=['queued','processing','completed','failed'][i%4],crop='玉米' if i%2==0 else None,
                predictions=[{'class':'aphid' if i%5 else 'whitefly','class_cn':'蚜虫' if i%5 else '粉虱','confidence':.7}],
                created_at=base+timedelta(days=i%3),analysis_status='skipped'))
        did=str(uuid4())
        db.add(Detection(id=did,user_id=user_id,media_type='image',original_name='literal%_sample.png',
            stored_name=did+'.png',status='completed',predictions=[],created_at=base+timedelta(days=10)))
        await db.commit()

def test_history_pagination_beyond_100_is_stable_and_user_scoped():
    with TestClient(app) as client:
        headers,user = account(client); other,other_user=account(client)
        asyncio.run(populate(user));asyncio.run(populate(other_user))
        ids=[]
        for offset in range(0,140,20):
            response=client.get('/api/detections/search',headers=headers,params={'offset':offset,'limit':20})
            assert response.status_code==200
            page=response.json();assert page['total']==126
            ids.extend(row['id'] for row in page['items'])
        assert len(ids)==len(set(ids))==126
        repeat=client.get('/api/detections/search',headers=headers,params={'offset':20,'limit':20}).json()
        assert [row['id'] for row in repeat['items']]==ids[20:40]
        foreign=client.get('/api/detections/search',headers=other).json()
        assert not set(ids)&{row['id'] for row in foreign['items']}
        assert client.get('/api/detections/search').status_code==401
        assert isinstance(client.get('/api/detections',headers=headers).json(),list)

def test_record_filters_chinese_literal_wildcards_and_date_boundaries():
    with TestClient(app) as client:
        headers,user=account(client);asyncio.run(populate(user))
        def search(**params):
            response=client.get('/api/detections/search',headers=headers,params=params)
            assert response.status_code==200,response.text
            return response.json()
        assert search(q='蚜虫')['total']==100
        assert search(q='aphid')['total']==100
        assert search(q='玉米')['total']==63
        assert search(q='%_')['total']==1
        assert search(q="' OR 1=1 --")['total']==0
        assert search(q='  leaf_124  ')['total']==1
        page=search(media_type='image',status='completed')
        assert page['total']>0 and all(row['media_type']=='image' and row['status']=='completed' for row in page['items'])
        assert search(start_at='2026-01-02T00:00:00Z',end_at='2026-01-03T00:00:00Z')['total']==42
        assert search(start_at='2026-01-02T08:00:00+08:00',end_at='2026-01-03T08:00:00+08:00')['total']==42
        for params in [{'offset':-1},{'limit':101},{'media_type':'bad'},{'status':'bad'}, {'q':'a'*101},
                       {'start_at':'2026-01-03T00:00:00Z','end_at':'2026-01-02T00:00:00Z'}]:
            assert client.get('/api/detections/search',headers=headers,params=params).status_code==422

def upload_video(client,headers):
    response=client.post('/api/videos',headers=headers,files={'file':('a.mp4',b'\0\0\0\x18ftypmp42\0\0\0\0mp42isom','video/mp4')})
    assert response.status_code==202,response.text
    return response.json()

def test_retry_video_is_owned_idempotent_and_requires_retained_source():
    with TestClient(app) as client:
        headers,user=account(client);other,_=account(client)
        item=upload_video(client,headers);did=item['id']
        assert item['progress']['stage']=='queued'
        async def fail():
            async with SessionLocal() as db:
                row=await db.get(Detection,did)
                source=get_settings().upload_dir/row.stored_name
                row.status='failed';await db.commit()
                return source
        source=asyncio.run(fail())
        assert client.post(f'/api/videos/{did}/retry',headers=other).status_code==404
        assert client.get(f'/api/videos/{did}',headers=headers).json()['progress']['can_retry']
        first=client.post(f'/api/videos/{did}/retry',headers=headers)
        second=client.post(f'/api/videos/{did}/retry',headers=headers)
        assert first.status_code==second.status_code==202
        assert first.json()['status']==second.json()['status']=='queued'
        assert first.json()['id']==second.json()['id']==did and source.exists()
        asyncio.run(fail());source.unlink()
        assert not client.get(f'/api/videos/{did}',headers=headers).json()['progress']['can_retry']
        assert client.post(f'/api/videos/{did}/retry',headers=headers).status_code==409

@pytest.mark.asyncio
async def test_progress_updates_are_persisted_and_fenced_after_completion():
    with TestClient(app) as client:
        headers,_=account(client);item=upload_video(client,headers)
    did,attempt=item['id'],str(uuid4())
    async with SessionLocal() as db:
        await db.execute(update(Detection).where(Detection.id==did).values(status='processing',job_attempt=attempt))
        await db.commit()
    control=VideoControl();control.report('detecting',40,100)
    assert await video._save_progress(did,attempt,control)
    async with SessionLocal() as db:
        item=await db.get(Detection,did)
        assert item.video_meta['progress']['percent']==40
        item.status='completed';item.video_meta={'total_frames':100};await db.commit()
    control.report('detecting',50,100)
    assert not await video._save_progress(did,attempt,control)
    async with SessionLocal() as db:
        assert (await db.get(Detection,did)).video_meta=={'total_frames':100}

@pytest.mark.asyncio
async def test_video_shutdown_keeps_source_and_next_worker_resumes(monkeypatch):
    with TestClient(app) as client:
        headers,_=account(client);item=upload_video(client,headers)
    did=item['id']
    async with SessionLocal() as db:
        source=get_settings().upload_dir/(await db.get(Detection,did)).stored_name
    started=Event()
    def interrupted(source,target,stop):
        target.write_bytes(b'partial');started.set()
        assert stop.wait(4)
        raise RuntimeError('cancelled')
    monkeypatch.setattr(video,'render_video',interrupted)
    task=asyncio.create_task(video.process_video({'job_try':1},did,str(source)))
    assert await asyncio.to_thread(started.wait,3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    async with SessionLocal() as db:
        assert (await db.get(Detection,did)).status=='queued'
    assert source.exists()
    def resumed(source,target,stop):
        target.write_bytes(b'finished');stop.report('detecting',10,10)
        return [],{'total_frames':10,'sampled_frames':10}
    monkeypatch.setattr(video,'render_video',resumed)
    monkeypatch.setattr(video,'transcode_to_h264',lambda path:True)
    await video.process_video({'job_try':1},did,str(source))
    async with SessionLocal() as db:
        row=await db.get(Detection,did)
        assert row.status=='completed' and (get_settings().result_dir/row.result_path).exists()
    assert not source.exists()

@pytest.mark.asyncio
async def test_local_runner_survives_temporary_database_scan_failure(monkeypatch):
    from app.services import local_tasks,task_maintenance
    resumed=asyncio.Event();calls=0
    async def reconcile():
        nonlocal calls
        calls+=1
        if calls==1: raise RuntimeError('temporary database problem')
        resumed.set()
    class Rows:
        def all(self): return []
    class Database:
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def execute(self,*args): return Rows()
    monkeypatch.setattr(task_maintenance,'reconcile_tasks',reconcile)
    monkeypatch.setattr(local_tasks,'SessionLocal',Database)
    task=asyncio.create_task(local_tasks.local_loop())
    await asyncio.wait_for(resumed.wait(),4)
    assert not task.done() and calls>=2
    task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
