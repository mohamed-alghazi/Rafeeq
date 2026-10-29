from __future__ import annotations
import asyncio
import json
import os
import sys
from pathlib import Path
from contextlib import AsyncExitStack
from datetime import timedelta
from typing import Protocol
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import AsyncOpenAI, OpenAIError
from rafeeq.store import Store
from rafeeq.privacy import redact, redact_text
from rafeeq.provider_errors import provider_settings, safe_failure

ROOT = Path(__file__).resolve().parents[1]
MAX_STEPS = 8
MAX_CALLS = 12
MAX_CONTEXT = 24_000
MAX_OUTPUT_TOKENS = 800

RESERVATION_PER_REQUEST = 0.006
MAX_COST_USD = 0.05

def tool(name, description, fields):
    return {'type':'function','function':{'name':name,'description':description,
            'parameters':{'type':'object','properties':{k:{'type':'string','description':v} for k,v in fields.items()},
                          'required':list(fields),'additionalProperties':False}}}


LOCAL_TOOLS = [
    tool('get_application','Read a verified applicant\'s synthetic application.',{'application_id':'Application ID'}),
    tool('list_inspections','List the verified applicant\'s existing inspections.',{'application_id':'Application ID'}),
    tool('propose_inspection','Prepare an inspection. Human approval is required before booking.',{'application_id':'Application ID','day':'Future Sunday–Thursday, YYYY-MM-DD'}),
    tool('propose_reschedule','Prepare a change to an existing inspection. Human approval is required.',{'inspection_id':'ID from list_inspections','day':'New future date, YYYY-MM-DD'}),
    tool('propose_refund','Calculate a policy-eligible refund and prepare a request. Never pays money. Requires human approval; above 1000 SAR also awaits finance.',{'application_id':'Application ID'}),
    tool('propose_escalation','Prepare escalation of an active overdue application. Human approval required.',{'application_id':'Application ID'}),
]


class Provider(Protocol):
    async def complete(self, messages: list, tools: list) -> dict: ...


class OpenRouterProvider:
    def __init__(self):
        self.provider_name, self.model, key_name = provider_settings()
        key = os.getenv(key_name,'').strip()
        if not key: raise ValueError('Provider key is missing; configure it securely in the environment.')
        base = 'https://api.openai.com/v1' if self.provider_name=='openai' else 'https://openrouter.ai/api/v1'
        self.client = AsyncOpenAI(api_key=key,base_url=base,timeout=45,max_retries=0)

    async def complete(self, messages, tools):
        try:
            result = await self.client.chat.completions.create(model=self.model,messages=messages,tools=tools,max_tokens=MAX_OUTPUT_TOKENS,temperature=0)
        except OpenAIError as exc:
            raise safe_failure(exc) from None
        if not result.choices:
            from rafeeq.provider_errors import ProviderFailure
            raise ProviderFailure('provider_empty_response','The AI provider returned no answer. Please try again later.',502)
        choice = result.choices[0]
        return {'message':choice.message.model_dump(exclude_none=True),
                'tokens':result.usage.total_tokens if result.usage else 0,
                'finish_reason':choice.finish_reason,'served_model':result.model}

    async def close(self):
        await self.client.close()


def trim_history(history: list) -> list:
    history = [{'role':m['role'],'content':redact_text(m['content'])} for m in history
               if m.get('role') in {'user','assistant'} and isinstance(m.get('content'),str) and not m.get('tool_calls')][-12:]
    while history and history[0]['role'] != 'user': history = history[1:]
    while len(json.dumps(history, ensure_ascii=False)) > 8_000: history = history[2:]
    return history


async def run_agent(prompt: str, store: Store, provider: Provider, config='B', history=None, owner=None, session_id=None) -> dict:
    if config not in {'A', 'B'}: raise ValueError('Unknown configuration')
    spec = (ROOT / 'rafeeq/spec.md').read_text()

    if config == 'B': spec += '\nFor fee and policy questions, start by retrieving the relevant policy before computing or answering.'
    if session_id:
        history = store.history(session_id)
    messages = [{'role': 'system', 'content': spec}, *trim_history(history or []), {'role': 'user', 'content': redact_text(prompt)}]
    trace, tokens, requests, reserved = [], 0, 0, 0.0
    served_models = set()
    def scope():
        if not session_id: raise ValueError('Verify the applicant in the verification form first')
        return store.session(session_id, True)['owner']

    def finish(answer: str, stopped: str) -> dict:
        answer = redact_text(answer)
        current = store.session(session_id)['owner'] if session_id else None
        if session_id and stopped == 'complete': store.remember(session_id, prompt, answer)
        return {'answer': answer, 'stopped': stopped, 'trace': trace, 'requests': requests,
                'tokens': tokens, 'served_models': sorted(served_models), 'reserved_usd': round(reserved, 4), 'pending': store.pending(current, session_id) if current else []}

    async with AsyncExitStack() as stack:
        read, write = await stack.enter_async_context(stdio_client(StdioServerParameters(command=sys.executable, args=['-m', 'rafeeq.mcp_server'], cwd=str(ROOT))))
        mcp = await stack.enter_async_context(ClientSession(read, write, read_timeout_seconds=timedelta(seconds=20)))
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
            if result.get('served_model'): served_models.add(result['served_model'])
            if result.get('finish_reason', 'stop') not in {'stop', 'tool_calls'}:
                return finish('The model reply was incomplete. No tools from this reply were executed.', 'incomplete_response')
            msg = result['message']
            calls = msg.get('tool_calls') or []
            if not calls:
                answer = msg.get('content') or ''
                return finish(answer, 'complete' if answer.strip() else 'empty_response')
            if len(trace) + len(calls) > MAX_CALLS:
                return finish('Tool-call budget reached.', 'tool_budget')
            messages.append(msg)
            for call in calls:
                name = call['function']['name']
                args = {}
                ok = False
                try:
                    args = json.loads(call['function']['arguments'])
                    if name in remote_names:
                        response = await mcp.call_tool(name, args)
                        ok = not response.isError
                        output = {'error': 'MCP tool rejected input'} if not ok else response.structuredContent
                        if ok and output is None:
                            content = [c.text for c in response.content if hasattr(c, 'text')]
                            try: output = json.loads(content[0]) if len(content) == 1 else {'content': content}
                            except ValueError: output = {'content': content}
                    elif name in {t['function']['name'] for t in LOCAL_TOOLS}:
                        current_owner = scope()
                        if name == 'get_application': output = store.application(owner=current_owner, **args)
                        elif name == 'list_inspections': output = store.inspections(owner=current_owner, **args)
                        elif name == 'propose_inspection': output = store.propose(owner=current_owner, token=session_id, **args)
                        elif name == 'propose_reschedule': output = store.reschedule(owner=current_owner, token=session_id, **args)
                        elif name == 'propose_refund': output = store.refund(owner=current_owner, token=session_id, **args)
                        else: output = store.escalate(owner=current_owner, token=session_id, **args)
                        ok = True
                    else: output = {'error': 'Tool not allowed'}
                except (ValueError, TypeError):
                    output = {'error': 'Verification required, invalid arguments, or application unavailable'}
                text = json.dumps(redact(output), ensure_ascii=False)[:5000]
                trace.append({'tool': name, 'arguments': redact(args), 'ok': ok, 'result': text})
                messages.append({'role': 'tool', 'tool_call_id': call['id'], 'content': text})
    return finish('Step budget reached.', 'step_budget')
