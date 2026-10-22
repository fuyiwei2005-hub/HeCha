import asyncio
import io
import json
from uuid import uuid4
import numpy as np
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from app.main import app
from app.services.observation import assess_image, parse_observation
from app.core.database import SessionLocal
from app.models.detection import Detection

@pytest.fixture(autouse=True)
def idle_worker(monkeypatch):
    async def idle(): await asyncio.Event().wait()
    monkeypatch.setattr('app.main.maintenance_loop',idle)

def account(client):
    name='field_'+uuid4().hex[:12]
    assert client.post('/api/auth/register',json={'username':name,'password':'Test-password-123'}).status_code==201
    token=client.post('/api/auth/login',data={'username':name,'password':'Test-password-123'}).json()['access_token']
    return {'Authorization':'Bearer '+token}

def test_quality_dark_tiny_low_confidence_and_clear_image():
    warnings=assess_image(np.zeros((400,400,3),dtype=np.uint8),[{'confidence':.3,'bbox':{'x1':1,'y1':1,'x2':4,'y2':4}}])['warnings']
    assert any('偏暗' in w for w in warnings)
    assert any('较小' in w for w in warnings)
    assert any('偏低' in w for w in warnings)
    noise=np.random.default_rng(7).integers(50,200,(400,400,3),dtype=np.uint8)
    assert not assess_image(noise,[{'confidence':.9,'bbox':{'x1':30,'y1':30,'x2':200,'y2':200}}])['warnings']
    assert assess_image(np.zeros((1,1,3),dtype=np.uint8),[])['warnings']

def test_observation_original_filter_correction_and_ownership(monkeypatch):
    def predict(content,target,rgb):
        Image.fromarray(rgb).save(target)
        return [{'class':'rice leaf roller','class_cn':'稻纵卷叶螟','confidence':.8,'bbox':{'x1':1,'y1':1,'x2':200,'y2':200}}]
    monkeypatch.setattr('app.services.detector.detector.predict_image',predict)
    with TestClient(app) as client:
        headers=account(client); other=account(client)
        photo=io.BytesIO();Image.new('RGB',(400,400),'green').save(photo,format='PNG')
        metadata={'field_name':'一号田','growth_stage':'苗期','severity':'少量','notes':'叶背观察','correction':''}
        r=client.post('/api/detections/image',headers=headers,data={'observation':json.dumps(metadata),'crop':'水稻'},files={'file':('leaf.png',photo.getvalue(),'image/png')})
        assert r.status_code==201,r.text
        item=r.json();did=item['id']; assert item['observation']==metadata and item['quality']['width']==400
        assert client.get(f'/api/detections/{did}/original',headers=headers).content==photo.getvalue()
        assert client.get(f'/api/detections/{did}/original',headers=other).status_code==404
        assert client.get(f'/api/detections/{did}/original').status_code==401
        metadata['correction']='疑似漏检，待复核';metadata['notes']='<script>test</script>'
        assert client.patch(f'/api/detections/{did}/observation',headers=other,json=metadata).status_code==404
        assert client.patch(f'/api/detections/{did}/observation',headers=headers,json=metadata).status_code==200
        assert client.get(f'/api/detections/{did}',headers=headers).json()['observation']==metadata
        assert client.get('/api/detections/search',headers=headers,params={'field_name':'一号田'}).json()['total']==1
        assert client.get('/api/detections/search',headers=other,params={'field_name':'一号田'}).json()['total']==0
        assert client.get('/api/detections/search',headers=headers,params={'detection_id':did}).json()['total']==1
        assert client.get('/api/detections/search',headers=other,params={'detection_id':did}).json()['total']==0
        assert client.patch(f'/api/detections/{did}/observation',headers=headers,json={**metadata,'notes':'x'*1001}).status_code==422
        comparison=client.get(f'/api/detections/{did}/comparison',headers=headers)
        assert comparison.status_code==200 and comparison.json()
        assert comparison.json()[0]['source'] and comparison.json()[0]['symptoms']
        assert client.get(f'/api/detections/{did}/comparison',headers=other).status_code==404
        async def completed():
            async with SessionLocal() as db:
                record=await db.get(Detection,did);record.analysis_status='completed';record.analysis='old';await db.commit()
        asyncio.run(completed())
        monkeypatch.setattr('app.api.detections.analysis_request',lambda p:{'analysis_status':'queued','analysis_attempt':uuid4().hex})
        assert client.post(f'/api/detections/{did}/analysis',headers=headers).json()['analysis_status']=='completed'
        assert client.post(f'/api/detections/{did}/analysis?refresh=true',headers=other).status_code==404
        assert client.post(f'/api/detections/{did}/analysis?refresh=true',headers=headers).json()['analysis_status']=='queued'
        assert client.get(f'/api/detections/{did}',headers=headers).json()['observation']==metadata

def test_invalid_observation_rejected_before_upload():
    from fastapi import HTTPException
    for raw in ['[]','{"severity":"invalid"}','{"unknown":true}','x'*6001]:
        with pytest.raises(HTTPException):parse_observation(raw)
