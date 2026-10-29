import asyncio
import json
from types import SimpleNamespace

import httpx
import openai
import pytest
from fastapi.testclient import TestClient

from rafeeq.agent import OpenRouterProvider
from rafeeq.provider_errors import ProviderFailure, provider_settings, safe_failure
from rafeeq.store import Store


def error(status):
    response=httpx.Response(status,request=httpx.Request('POST','https://provider.example/chat'))
    return openai.APIStatusError('sensitive provider payload must not escape',response=response,body={'error':'private-value'})


@pytest.mark.parametrize('status,code',[(401,'provider_key_rejected'),(402,'provider_credits_required'),(403,'provider_access_denied'),(404,'provider_model_unavailable'),(429,'provider_rate_limited'),(400,'provider_request_rejected'),(503,'provider_unavailable')])
def test_safe_status_mapping_and_nested_task_groups(status,code):
    exc=ExceptionGroup('task group',[ExceptionGroup('nested',[error(status)])])
    result=safe_failure(exc)
    assert result.code==code
    assert 'sensitive' not in result.public_message and 'private-value' not in result.public_message


def test_internal_failure_is_not_mislabelled_as_provider_error():
    assert safe_failure(ExceptionGroup('group',[RuntimeError('internal-secret')])).code=='assistant_runtime_error'
    original=ProviderFailure('provider_key_rejected','Safe message')
    assert safe_failure(ExceptionGroup('group',[original])) is original


def test_free_router_default_and_model_configuration(monkeypatch):
    monkeypatch.setenv('RAFEEQ_PROVIDER','openrouter');monkeypatch.delenv('RAFEEQ_MODEL',raising=False)
    assert provider_settings()==('openrouter','openrouter/free','OPENROUTER_API_KEY')
    monkeypatch.setenv('RAFEEQ_MODEL',' vendor/model:free ')
    assert provider_settings()[1]=='vendor/model:free'
    monkeypatch.setenv('RAFEEQ_MODEL','sk-or-v1-not-a-model')
    with pytest.raises(ValueError):provider_settings()
    monkeypatch.setenv('RAFEEQ_PROVIDER','invalid')
    with pytest.raises(ValueError):provider_settings()


def test_provider_converts_errors_without_exposing_response(monkeypatch):
    captured={}
    class Client:
        def __init__(self,**kwargs):self.chat=SimpleNamespace(completions=self);captured.update(kwargs)
        async def create(self,**kwargs):raise error(404)
        async def close(self):pass
    monkeypatch.setenv('RAFEEQ_PROVIDER','openrouter');monkeypatch.delenv('RAFEEQ_MODEL',raising=False)
    monkeypatch.setenv('OPENROUTER_API_KEY',' test-only-fixture ')
    monkeypatch.setattr('rafeeq.agent.AsyncOpenAI',Client)
    provider=OpenRouterProvider()
    assert captured['api_key']=='test-only-fixture' and provider.model=='openrouter/free'
    with pytest.raises(ProviderFailure) as exc:asyncio.run(provider.complete([],[]))
    assert exc.value.code=='provider_model_unavailable'
    assert 'sensitive' not in str(exc.value)


def test_api_exposes_only_safe_diagnostic_code(tmp_path,monkeypatch,caplog):
    from rafeeq import api
    monkeypatch.setenv('RAFEEQ_ACCESS_TOKEN','test-access')
    monkeypatch.setattr(api,'store',Store(tmp_path/'db'))
    class Provider:
        async def close(self):pass
    async def failing(*args,**kwargs):raise ExceptionGroup('private-root',[error(401)])
    monkeypatch.setattr(api,'OpenRouterProvider',Provider);monkeypatch.setattr(api,'run_agent',failing)
    c=TestClient(api.app);h={'Authorization':'Bearer test-access'}
    h['X-Rafeeq-Session']=c.post('/api/sessions',headers=h).json()['session_token']
    response=c.post('/api/chat',headers=h,json={'message':'Hello'})
    assert response.status_code==503 and response.json()['error_code']=='provider_key_rejected'
    assert 'sensitive' not in response.text and 'private-value' not in response.text
    assert 'private-value' not in caplog.text and 'private-root' not in caplog.text
    assert 'chat_failure code=provider_key_rejected' in caplog.text


def test_health_uses_selected_provider_and_never_echoes_invalid_model(monkeypatch):
    from rafeeq import api
    monkeypatch.setenv('RAFEEQ_PROVIDER','openrouter');monkeypatch.delenv('OPENROUTER_API_KEY',raising=False)
    monkeypatch.setenv('OPENAI_API_KEY','other-provider-fixture');monkeypatch.setenv('RAFEEQ_MODEL','openrouter/free')
    c=TestClient(api.app);data=c.get('/health').json()
    assert not data['provider_configured'] and data['model']=='openrouter/free'
    monkeypatch.setenv('RAFEEQ_MODEL','sk-or-v1-fixture')
    response=c.get('/health')
    assert response.json()['configuration_valid'] is False
    assert 'sk-or-v1-fixture' not in response.text
