from copy import deepcopy
from uuid import UUID
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from app.main import app, videos
from app.ai import ModelUnavailable

FIELDS = {'title':'Python', 'topic':'цикли', 'duration_minutes':15}
TEXT = 'Відео Python, тема цикли, тривалість 15 хвилин'

@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.setenv('AI_MODE', 'fixture')
    videos.clear()
    yield
    videos.clear()

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

def unchanged_failure(client, payload, code=422, status=None):
    client.post('/videos', json=FIELDS)
    before = deepcopy(client.get('/videos').json())
    response = client.post('/videos/ai', json={'text':payload})
    assert response.status_code == code
    if status:
        assert response.json()['detail']['status'] == status
    assert client.get('/videos').json() == before
    return response

def test_list_and_manual(client):
    assert client.get('/videos').json() == []
    with patch('app.main.extract_video', side_effect=AssertionError('manual must not use AI')):
        r = client.post('/videos', json=FIELDS)
    assert r.status_code == 201
    record = r.json()
    UUID(record['id'])
    assert {k:record[k] for k in FIELDS} == FIELDS
    assert client.get('/videos').json() == [record]

@pytest.mark.parametrize('change', [
    {'title':''}, {'topic':' '}, {'duration_minutes':0}, {'duration_minutes':-1},
    {'duration_minutes':True}, {'duration_minutes':'15'}, {'duration_minutes':1441},
    {'duration_minutes':1.5}, {'extra':1}, {'title':'x'*201},
])
def test_manual_invalid(client, change):
    client.post('/videos', json=FIELDS)
    before = client.get('/videos').json()
    r = client.post('/videos', json={**FIELDS, **change})
    assert r.status_code == 422
    assert client.get('/videos').json() == before

def test_ai_valid(client):
    r = client.post('/videos/ai', json={'text':TEXT})
    assert r.status_code == 201
    UUID(r.json()['id'])
    assert {k:r.json()[k] for k in FIELDS} == FIELDS
    assert client.get('/videos').json() == [r.json()]

@pytest.mark.parametrize('text', ['Відео Python, тема цикли', 'Відео Python, тема цикли, тривалість 15 або 20 хвилин', 'Відео Python, тема цикли, тривалість 0 хвилин'])
def test_incomplete(client, text):
    with patch('app.main.extract_video', side_effect=AssertionError('no guessing')):
        unchanged_failure(client,text,status='needs_clarification')

def test_null(client):
    with patch('app.main.extract_video', return_value=None):
        unchanged_failure(client,TEXT,status='needs_clarification')

@pytest.mark.parametrize('proposal', ['not JSON', [], {'title':'Python'}, {**FIELDS,'duration_minutes':True}, {**FIELDS,'extra':'x'}, {**FIELDS,'duration_minutes':'15'}, {**FIELDS,'title':None}])
def test_invalid_proposal(client, proposal):
    with patch('app.main.extract_video', return_value=proposal):
        unchanged_failure(client,TEXT,status='invalid_proposal')

@pytest.mark.parametrize('change', [{'duration_minutes':21}, {'title':'Java'}, {'topic':'функції'}])
def test_semantic_mismatch(client, change):
    with patch('app.main.extract_video', return_value={**FIELDS,**change}):
        unchanged_failure(client,TEXT,status='semantic_mismatch')

@pytest.mark.parametrize('error', [ModelUnavailable('secret must not leak'), TimeoutError()])
def test_failure_and_manual(client, error):
    with patch('app.main.extract_video', side_effect=error):
        r = unchanged_failure(client,TEXT,503,'model_unavailable')
        assert 'secret' not in r.text
        before = client.get('/videos').json()
        manual = client.post('/videos',json=FIELDS)
        assert manual.status_code == 201
        assert client.get('/videos').json() == before + [manual.json()]

def test_missing_key(client, monkeypatch):
    monkeypatch.setenv('AI_MODE','live')
    monkeypatch.delenv('GROQ_API_KEY',raising=False)
    unchanged_failure(client,TEXT,503,'model_unavailable')
    assert client.post('/videos',json=FIELDS).status_code == 201

def test_json_provider_response(client):
    import json
    with patch('app.main.extract_video',return_value=json.dumps(FIELDS)):
        assert client.post('/videos/ai',json={'text':TEXT}).status_code == 201

def test_unique_ids_and_repeated_records(client):
    a=client.post('/videos',json=FIELDS).json()
    b=client.post('/videos',json=FIELDS).json()
    assert a['id'] != b['id']
    assert client.get('/videos').json() == [a,b]

def test_timeout_config(monkeypatch):
    from app.ai import extract_video
    monkeypatch.setenv('AI_MODE','live')
    monkeypatch.setenv('GROQ_API_KEY','test-only')
    with patch('app.ai.Groq') as factory:
        factory.return_value.__enter__.return_value.chat.completions.create.side_effect=TimeoutError()
        with pytest.raises(ModelUnavailable):
            extract_video(TEXT)
        assert factory.call_args.kwargs['timeout'] == 15.0
        assert factory.call_args.kwargs['max_retries'] == 0
