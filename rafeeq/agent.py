from __future__ import annotations
import asyncio
import json
import os
import sys
from pathlib import Path
from contextlib import AsyncExitStack
from typing import Protocol
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import AsyncOpenAI
from rafeeq.store import Store

ROOT = Path(__file__).resolve().parents[1]
MAX_STEPS = 8
MAX_CALLS = 12
MAX_CONTEXT = 24_000
MAX_OUTPUT_TOKENS = 800
# Conservative preflight reservation, not a provider price guarantee.
RESERVATION_PER_REQUEST = 0.006
MAX_COST_USD = 0.05

LOCAL_TOOLS = [
    {'type': 'function', 'function': {'name': 'get_application', 'description': 'Read one synthetic application belonging to the current applicant.', 'parameters': {'type': 'object', 'properties': {'application_id': {'type': 'string'}}, 'required': ['application_id'], 'additionalProperties': False}}},
    {'type': 'function', 'function': {'name': 'propose_inspection', 'description': 'Propose an inspection. Does NOT book; requires separate human approval.', 'parameters': {'type': 'object', 'properties': {'application_id': {'type': 'string'}, 'day': {'type': 'string', 'description': 'Future working date YYYY-MM-DD'}}, 'required': ['application_id', 'day'], 'additionalProperties': False}}},
]


class Provider(Protocol):
    async def complete(self, messages: list, tools: list) -> dict: ...


class OpenRouterProvider:
    def __init__(self):
        native = os.getenv('RAFEEQ_PROVIDER', 'openrouter') == 'openai'
        key = os.getenv('OPENAI_API_KEY' if native else 'OPENROUTER_API_KEY')
        if not key: raise ValueError('Provider key is missing; configure it securely in the environment.')
        self.client = AsyncOpenAI(api_key=key, base_url='https://api.openai.com/v1' if native else 'https://openrouter.ai/api/v1', timeout=45, max_retries=0)
        self.model = os.getenv('RAFEEQ_MODEL', 'gpt-4.1-mini' if native else 'google/gemma-4-31b-it:free')

    async def complete(self, messages, tools):
        result = await self.client.chat.completions.create(model=self.model, messages=messages, tools=tools, max_tokens=MAX_OUTPUT_TOKENS, temperature=0)
        msg = result.choices[0].message
        return {'message': msg.model_dump(exclude_none=True), 'tokens': result.usage.total_tokens if result.usage else 0}


def trim_history(history: list) -> list:
    # History contains completed user/assistant turns only, never orphan tool results.
    history = history[-12:]
    while history and history[0].get('role') != 'user': history = history[1:]
    while len(json.dumps(history, ensure_ascii=False)) > 8_000: history = history[2:]
    return history


async def run_agent(prompt: str, store: Store, provider: Provider, config='B', history=None, owner='demo-user') -> dict:
    if config not in {'A', 'B'}: raise ValueError('Unknown configuration')
    spec = (ROOT / 'rafeeq/spec.md').read_text()
    # One controlled difference: B forces evidence retrieval in the first model request.
    if config == 'B': spec += '\nFor fee and policy questions, start by retrieving the relevant policy before computing or answering.'
    messages = [{'role': 'system', 'content': spec}, *trim_history(history or []), {'role': 'user', 'content': prompt}]
    trace, tokens, requests, reserved = [], 0, 0, 0.0
    def finish(answer: str, stopped: str) -> dict:
        return {'answer': answer, 'stopped': stopped, 'trace': trace, 'requests': requests,
                'tokens': tokens, 'reserved_usd': round(reserved, 4), 'pending': store.pending(owner)}

    async with AsyncExitStack() as stack:
        read, write = await stack.enter_async_context(stdio_client(StdioServerParameters(command=sys.executable, args=['-m', 'rafeeq.mcp_server'], cwd=str(ROOT))))
        mcp = await stack.enter_async_context(ClientSession(read, write))
        await mcp.initialize()
        remote = (await mcp.list_tools()).tools
        tools = LOCAL_TOOLS + [{'type': 'function', 'function': {'name': t.name, 'description': t.description or '', 'parameters': t.inputSchema}} for t in remote]
        remote_names = {t.name for t in remote}
        for _ in range(MAX_STEPS):
            if len(json.dumps(messages, ensure_ascii=False)) > MAX_CONTEXT:
                return finish('Context budget reached. Please start a shorter request.', 'context_budget')
            if reserved + RESERVATION_PER_REQUEST > MAX_COST_USD:
                return finish('Request cost reservation budget reached.', 'cost_budget')
            reserved += RESERVATION_PER_REQUEST
            requests += 1
            result = await provider.complete(messages, tools)
            tokens += result.get('tokens', 0)
            msg = result['message']
            calls = msg.get('tool_calls') or []
            if not calls:
                return {'answer': msg.get('content') or '', 'stopped': 'complete', 'trace': trace, 'requests': requests, 'tokens': tokens, 'reserved_usd': round(reserved, 4), 'pending': store.pending(owner)}
            if len(trace) + len(calls) > MAX_CALLS:
                return finish('Tool-call budget reached.', 'tool_budget')
            messages.append(msg)
            for call in calls:
                name = call['function']['name']
                try:
                    args = json.loads(call['function']['arguments'])
                    if name in remote_names:
                        response = await mcp.call_tool(name, args)
                        output = {'error': 'MCP tool rejected input'} if response.isError else {'content': [c.text for c in response.content if hasattr(c, 'text')]}
                    elif name == 'get_application': output = store.application(owner=owner, **args)
                    elif name == 'propose_inspection': output = store.propose(owner=owner, **args)
                    else: output = {'error': 'Tool not allowed'}
                except (ValueError, TypeError):
                    output = {'error': 'Invalid arguments or application unavailable'}
                text = json.dumps(output, ensure_ascii=False)[:5000]
                trace.append({'tool': name, 'result': text})
                messages.append({'role': 'tool', 'tool_call_id': call['id'], 'content': text})
    return finish('Step budget reached.', 'step_budget')
