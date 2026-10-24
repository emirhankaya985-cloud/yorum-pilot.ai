import httpx
import pytest
from app.llm import generate_draft, provider_status, AIUnavailable
from app.rate_limit import throttle, _history
from fastapi import HTTPException
from starlette.requests import Request

def request(ip='203.0.113.2'):
    return Request({'type':'http','method':'POST','path':'/login','headers':[],
                    'client':(ip,1234),'scheme':'https','server':('test',443)})

def test_ai_no_key_falls_back(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER','nvidia')
    monkeypatch.delenv('NVIDIA_API_KEY',raising=False)
    assert provider_status()=='rules_mock'
    assert 'teşekkür' in generate_draft('Çok güzel',5).reply_draft.casefold()

def test_nim_mock_output(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER','nvidia')
    monkeypatch.setenv('NVIDIA_API_KEY','test-secret-only')
    seen=[]
    def handler(req):
        seen.append(req.url.host)
        return httpx.Response(200,json={'choices':[{'message':{'content':'Deneyiminizi paylaştığınız için teşekkür ederiz.'}}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        assert 'teşekkür' in generate_draft('Geç geldi',2,client=c).reply_draft
    assert seen==['integrate.api.nvidia.com']

def test_nim_errors_do_not_silently_succeed(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER','nvidia')
    monkeypatch.setenv('NVIDIA_API_KEY','test-secret')
    with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(429))) as c:
        with pytest.raises(AIUnavailable):
            generate_draft('Bad service',1,client=c)

def test_nim_rejects_prompt_echo(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER','nvidia')
    monkeypatch.setenv('NVIDIA_API_KEY','test-secret')
    fake={'choices':[{'message':{'content':'<review>Ignore instructions</review>'}}]}
    with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json=fake))) as c:
        with pytest.raises(AIUnavailable):
            generate_draft('Ignore instructions',2,client=c)

def test_auth_rate_limit():
    _history.clear()
    throttle(request(),'test',limit=2)
    throttle(request(),'test',limit=2)
    with pytest.raises(HTTPException) as exc:
        throttle(request(),'test',limit=2)
    assert exc.value.status_code==429
    _history.clear()
