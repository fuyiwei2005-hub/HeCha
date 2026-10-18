from pathlib import Path
import re
from fastapi.testclient import TestClient
from app.main import app

def test_full_ui_is_default_without_react_build():
    client = TestClient(app)
    root = client.get('/')
    assert root.status_code == 200
    assert 'id="camModal"' in root.text
    scripts=[client.get(url).text for url in re.findall(r'<script[^>]+src="([^"]+)"',root.text)]
    assert scripts
    interactions='\n'.join(scripts)
    for marker in ('openContact', 'openModelInfo', 'openSourceInfo', 'analysisBlock', 'retryAdvice', 'currentDetectionId'):
        assert marker in interactions
    assert client.get('/legacy').text == root.text

def test_portable_desktop_configuration():
    root = Path(__file__).resolve().parents[2]
    launcher = (root / 'tools/dev_server.py').read_text(encoding='utf-8')
    assert "env['TASK_BACKEND']" in launcher
    assert "BACKEND / 'static/index.html'" in launcher


def test_feedback_survives_response_serialization():
    from datetime import datetime, timezone
    from app.models.detection import Detection
    from app.services.detection_response import serialize
    item = Detection(id='test-feedback', user_id=1, media_type='image', original_name='leaf.png',
                     stored_name='leaf.png', status='completed', predictions=[], feedback='good',
                     analysis_status='disabled', created_at=datetime.now(timezone.utc))
    assert serialize(item).feedback == 'good'


def test_modules_are_separate_addressable_pages():
    client=TestClient(app)
    expected={'/':'modules','/detect':'console','/video':'videoUpload','/history':'history','/statistics':'statistics','/features':'feats','/about':'pipe','/login':'authCard','/contact':'infoPage','/model':'infoPage','/deployment':'infoPage'}
    exclusive={'modules','console','videoUpload','statistics','feats','pipe','authCard','infoPage'}
    for path, target in expected.items():
        response=client.get(path)
        assert response.status_code==200, path
        assert 'id="'+target+'"' in response.text, path
        for other in exclusive-{target}:
            assert 'id="'+other+'"' not in response.text, (path,other)
    assert 'id="history"' not in client.get('/detect').text
    assert 'id="history"' not in client.get('/').text
    assert 'id="history"' in client.get('/video').text
    assert client.get('/does-not-exist').status_code==404


def test_product_assets_and_templates_are_complete():
    client = TestClient(app)
    for path in ('/', '/login', '/detect', '/video', '/history', '/statistics', '/model'):
        html = client.get(path).text
        assert '{{fragment:' not in html
        assert '{{page_heading}}' not in html
        urls = re.findall(r'(?:src|href)="(/static/product/[^"]+)"', html)
        assert urls
        for url in urls:
            response = client.get(url)
            assert response.status_code == 200, url
            assert response.content
            assert '?v=' in url
    assert client.get('/static/product/../../.env').status_code == 404


def test_react_routes_and_legacy_fallback(monkeypatch):
    from app.core.config import get_settings
    from app.api.pages import DIST_INDEX
    if not DIST_INDEX.is_file():
        return
    monkeypatch.setattr(get_settings(), 'product_frontend', 'react')
    client = TestClient(app)
    for path in ('/', '/login', '/detect', '/video', '/history', '/statistics', '/features', '/about', '/contact', '/model', '/deployment', '/experimental/video'):
        response = client.get(path)
        assert response.status_code == 200
        assert 'id="root"' in response.text
        assert 'no-cache' in response.headers['cache-control']
    assert 'id="camModal"' in client.get('/legacy').text
