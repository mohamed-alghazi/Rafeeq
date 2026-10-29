from __future__ import annotations

import asyncio
import logging
import os
import secrets
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, ConfigDict, StrictBool

from rafeeq.agent import OpenRouterProvider, run_agent
from rafeeq.store import Store
from rafeeq.provider_errors import provider_settings, safe_failure, leaves

load_dotenv()
app = FastAPI(title='رفيق | Rafeeq', version='0.2.0')
store = Store(Path(os.getenv('RAFEEQ_DB', '.runtime/rafeeq.sqlite')))
lock = asyncio.Lock()


@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):

    return JSONResponse(status_code=422, content={'detail': 'Invalid request fields'})


def auth(authorization: str = Header(default='')):
    token = os.getenv('RAFEEQ_ACCESS_TOKEN','')
    if not token: raise HTTPException(503,'Private API access has not been configured')
    if not secrets.compare_digest(authorization.encode(),f'Bearer {token}'.encode()):
        raise HTTPException(401,'Invalid access code')


def session_token(x_rafeeq_session: str = Header(default=''), authorization: str = Header(default='')):
    if not x_rafeeq_session or len(x_rafeeq_session)>100: raise HTTPException(401,'Start a demo session first')
    try: state = store.session(x_rafeeq_session)
    except ValueError: raise HTTPException(401,'Session expired or unavailable')
    if not state['public']: auth(authorization)
    return x_rafeeq_session


def verified(token=Depends(session_token)):
    try: return token, store.session(token, True)['owner']
    except ValueError as exc: raise HTTPException(403, str(exc))


class StrictBody(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Ask(StrictBody):
    message: str = Field(min_length=1, max_length=4000)
    config: str = Field(default='B', pattern='^[AB]$')


class Verification(StrictBody):
    application_id: str = Field(min_length=1, max_length=40)
    last4: str = Field(min_length=4, max_length=4)
    mobile: str = Field(min_length=8, max_length=24)


class PolicySearch(StrictBody):
    query: str = Field(min_length=1, max_length=1000)
    mode: Literal['A','B'] = 'B'


class Decision(StrictBody):
    approve: StrictBool


@app.get('/', include_in_schema=False)
def home(): return FileResponse(Path(__file__).with_name('index.html'))


@app.get('/health')
def health():
    try:
        provider, model, key_name = provider_settings()
        configured = bool(os.getenv(key_name,'').strip())
        valid = True
    except ValueError:
        provider, model, configured, valid = None, None, False, False
    return {'status':'ok','synthetic':True,'provider':provider,'model':model,'configuration_valid':valid,
            'provider_configured':configured,'access_configured':bool(os.getenv('RAFEEQ_ACCESS_TOKEN')),'guest_access':True}


@app.post('/api/policies/search')
def search_public_policies(body: PolicySearch):
    from rafeeq.retrieval import policy_search
    try: return {'mode':body.mode,'local':True,'documents':policy_search(body.query,body.mode)}
    except ValueError as exc: raise HTTPException(422,str(exc))


@app.post('/api/visitors')
def create_visitor_session():
    return {'session_token':store.create_session(public=True)}


@app.post('/api/sessions')
def create_session(_=Depends(auth)):
    return {'session_token': store.create_session()}


@app.get('/api/session')
def session_status(token=Depends(session_token)):
    state = store.session(token)
    return {k: state[k] for k in ('verified','locked','failed_attempts')}


@app.post('/api/session/verify')
def verify_identity(body: Verification, token=Depends(session_token)):
    try: return store.verify(token, body.application_id, body.last4, body.mobile)
    except ValueError as exc: raise HTTPException(403, str(exc))


@app.get('/api/history')
def history(token=Depends(session_token)):
    return store.history(token)


@app.delete('/api/history')
def clear_history(token=Depends(session_token)):
    store.clear_history(token)
    return {'cleared': True}


@app.post('/api/chat')
async def chat(body: Ask, token=Depends(session_token)):
    try:
        async with lock:
            provider = OpenRouterProvider()
            try:
                return await asyncio.wait_for(run_agent(body.message, store, provider, body.config, session_id=token), timeout=180)
            finally:
                await provider.close()
    except ValueError:
        return JSONResponse(status_code=503,content={'error_code':'provider_configuration_error','detail':'AI chat is not configured correctly. The site owner should check the provider key and model settings. Local policy search needs no key.'})
    except TimeoutError:
        return JSONResponse(status_code=504,content={'error_code':'assistant_timeout','detail':'The request timed out. Check pending actions before trying again.'})
    except Exception as exc:
        failure = safe_failure(exc)
        logging.getLogger('rafeeq').warning('chat_failure code=%s cause_types=%s',failure.code,','.join(sorted({type(e).__name__ for e in leaves(exc)})))
        return JSONResponse(status_code=failure.status,content={'error_code':failure.code,'detail':failure.public_message})


@app.get('/api/proposals')
def proposals(actor=Depends(verified)):
    token, owner = actor
    return store.pending(owner, token)


@app.post('/api/proposals/{proposal_id}/decision')
def decision(proposal_id: str, body: Decision, actor=Depends(verified)):
    token, owner = actor
    try: return store.decide(proposal_id, body.approve, owner, token)
    except ValueError as exc: raise HTTPException(409, str(exc))
