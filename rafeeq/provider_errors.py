from __future__ import annotations

import os
import re

import openai

DEFAULT_MODELS = {'openrouter':'openrouter/free','openai':'gpt-4.1-mini'}


def provider_settings():
    provider = os.getenv('RAFEEQ_PROVIDER','openrouter').strip().lower()
    if provider not in DEFAULT_MODELS:
        raise ValueError('RAFEEQ_PROVIDER must be openrouter or openai')
    model = os.getenv('RAFEEQ_MODEL','').strip() or DEFAULT_MODELS[provider]
    if not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,160}',model) or model.startswith(('sk-','hf_','ghp_')):
        raise ValueError('RAFEEQ_MODEL must contain a model ID, not an API key or URL')
    return provider, model, 'OPENAI_API_KEY' if provider=='openai' else 'OPENROUTER_API_KEY'


class ProviderFailure(Exception):
    def __init__(self, code, message, status=503):
        self.code, self.public_message, self.status = code, message, status
        super().__init__(message)


def leaves(error):
    children = getattr(error,'exceptions',None)
    if children:
        for child in children: yield from leaves(child)
    else: yield error


def safe_failure(error):
    errors = list(leaves(error))
    for item in errors:
        if isinstance(item,ProviderFailure): return item
    for item in errors:
        if isinstance(item,openai.APITimeoutError):
            return ProviderFailure('provider_timeout','The AI provider timed out. Please try again later.',504)
        if isinstance(item,openai.APIConnectionError):
            return ProviderFailure('provider_connection_failed','The AI service could not be reached. Please try again later or use policy search.')
        if isinstance(item,openai.APIStatusError):
            status = item.status_code
            if status==401:
                return ProviderFailure('provider_key_rejected','AI chat is temporarily unavailable. Policy search is still available.')
            if status==402:
                return ProviderFailure('provider_credits_required','AI chat is temporarily unavailable. Please use policy search or try again later.')
            if status==403:
                return ProviderFailure('provider_access_denied','The AI service is currently unavailable. Policy search is still available.')
            if status==404:
                return ProviderFailure('provider_model_unavailable','The AI model is currently unavailable. Please try again later or use policy search.')
            if status==429:
                return ProviderFailure('provider_rate_limited','The AI service has reached its usage limit. Please try again later or use policy search.',429)
            if status in (400,422):
                return ProviderFailure('provider_request_rejected','The AI service could not process this request. Policy search is still available.',502)
            return ProviderFailure('provider_unavailable','The AI provider returned a service error. Please try again later.',502)
    return ProviderFailure('assistant_runtime_error','The assistant could not complete the request. Please try again or use policy search.',502)
