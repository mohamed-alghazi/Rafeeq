from __future__ import annotations
import asyncio
import os
import secrets
from pathlib import Path
from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ConfigDict, StrictBool
from dotenv import load_dotenv
from rafeeq.agent import OpenRouterProvider, run_agent
from rafeeq.store import Store

load_dotenv()
app = FastAPI(title='رفيق | Rafeeq', version='0.1.0')
store = Store(Path(os.getenv('RAFEEQ_DB', '.runtime/rafeeq.sqlite')))
lock = asyncio.Lock()


def auth(authorization: str = Header(default='')):
    token = os.getenv('RAFEEQ_ACCESS_TOKEN', '')
    if not token: raise HTTPException(503, 'Set RAFEEQ_ACCESS_TOKEN before using the service')
    if not secrets.compare_digest(authorization, f'Bearer {token}'):
        raise HTTPException(401, 'Invalid access token')
    return 'demo-user'


class Ask(BaseModel):
    model_config = ConfigDict(extra='forbid')
    message: str = Field(min_length=1, max_length=4000)
    config: str = Field(default='B', pattern='^[AB]$')


class Decision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    approve: StrictBool


@app.get('/', include_in_schema=False)
def home(): return FileResponse(Path(__file__).with_name('index.html'))


@app.get('/health')
def health():
    return {'status': 'ok', 'synthetic': True, 'provider_configured': bool(os.getenv('OPENROUTER_API_KEY') or os.getenv('OPENAI_API_KEY')), 'access_configured': bool(os.getenv('RAFEEQ_ACCESS_TOKEN'))}


@app.post('/api/chat')
async def chat(body: Ask, owner=Depends(auth)):
    try:
        async with lock:
            provider = OpenRouterProvider()
            try:
                return await asyncio.wait_for(run_agent(body.message, store, provider, body.config, owner=owner), timeout=180)
            finally:
                await provider.close()
    except ValueError as exc: raise HTTPException(503, str(exc))
    except TimeoutError: raise HTTPException(504, 'Request timed out; inspect pending proposals before retrying')
    except Exception: raise HTTPException(502, 'Provider unavailable. Check key, quota and model; no credentials are logged.')


@app.get('/api/proposals')
def proposals(owner=Depends(auth)): return store.pending(owner)


@app.post('/api/proposals/{proposal_id}/decision')
def decision(proposal_id: str, body: Decision, owner=Depends(auth)):
    try: return store.decide(proposal_id, body.approve, owner)
    except ValueError as exc: raise HTTPException(409, str(exc))
