from __future__ import annotations

import asyncio
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

load_dotenv()
app = FastAPI(title='رفيق | Rafeeq', version='0.2.0')
store = Store(Path(os.getenv('RAFEEQ_DB', '.runtime/rafeeq.sqlite')))
lock = asyncio.Lock()


@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):

    return JSONResponse(status_code=422, content={'detail': 'Invalid request fields'})


def auth(authorization: str = Header(default='')):
    token = os.getenv('RAFEEQ_ACCESS_TOKEN', '')
    if not token: raise HTTPException(503, 'Set RAFEEQ_ACCESS_TOKEN before using the service')
    if not secrets.compare_digest(authorization, f'Bearer {token}'):
        raise HTTPException(401, 'Invalid access token')


def session_token(x_rafeeq_session: str = Header(default=''), _=Depends(auth)):
    if not x_rafeeq_session or len(x_rafeeq_session) > 100: raise HTTPException(401, 'Create a session first')
    try: store.session(x_rafeeq_session)
    except ValueError: raise HTTPException(401, 'Session expired or unavailable')
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
    provider = os.getenv('RAFEEQ_PROVIDER', 'openrouter')
    key = os.getenv('OPENAI_API_KEY' if provider == 'openai' else 'OPENROUTER_API_KEY')
    return {'status': 'ok', 'synthetic': True, 'provider_configured': bool(key), 'access_configured': bool(os.getenv('RAFEEQ_ACCESS_TOKEN'))}


@app.post('/api/policies/search')
def search_public_policies(body: PolicySearch):
    from rafeeq.retrieval import policy_search
    try: return {'mode':body.mode,'local':True,'documents':policy_search(body.query,body.mode)}
    except ValueError as exc: raise HTTPException(422,str(exc))


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
    except ValueError as exc: raise HTTPException(503, str(exc))
    except TimeoutError: raise HTTPException(504, 'Request timed out; inspect pending actions before retrying')
    except Exception: raise HTTPException(502, 'Provider unavailable. Check key, quota and model; no credentials are logged.')


@app.get('/api/proposals')
def proposals(actor=Depends(verified)):
    token, owner = actor
    return store.pending(owner, token)


@app.post('/api/proposals/{proposal_id}/decision')
def decision(proposal_id: str, body: Decision, actor=Depends(verified)):
    token, owner = actor
    try: return store.decide(proposal_id, body.approve, owner, token)
    except ValueError as exc: raise HTTPException(409, str(exc))
