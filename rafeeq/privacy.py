"""Minimise credentials and personal data in stored text, model context and traces."""
from __future__ import annotations

import re

DIGITS = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹', '01234567890123456789')
SENSITIVE = {'mobile', 'phone', 'national_id', 'national_id_last4', 'id_last4', 'last4',
             'api_key', 'openrouter_api_key', 'authorization', 'password', 'token',
             'access_token', 'session_token', 'session_id', 'identity_hash', 'mobile_hash'}
D = r'[0-9٠-٩۰-۹]'
PATTERNS = [
    (re.compile(r'\b(?:sk-or-v1-|sk-or-|sk-|hf_|ghp_)[A-Za-z0-9_-]{12,}'), '[secret]'),
    (re.compile(r'(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}'), 'Bearer [secret]'),
    (re.compile(r'(?i)\b(?:api[_-]?key|openrouter_api_key|password|access_token|session_token|session_id|secret)\s*[:=]\s*[\"\x27]?[^\s\"\x27,;]+'), '[secret]'),
    (re.compile(rf'(?<!{D})(?:(?:\+?[9٩۹][6٦۶][6٦۶]|[0٠۰][0٠۰][9٩۹][6٦۶][6٦۶]|[0٠۰])[\s-]?)?[5٥۵](?:[\s-]?{D}){{8}}(?!{D})'), '[mobile]'),
    (re.compile(rf'(?<!{D})[12١٢۱۲]{D}{{9}}(?!{D})'), '[national-id]'),
    (re.compile(r'\bSA\d{2}(?:[ -]?[A-Z0-9]){20}\b', re.I), '[iban]'),
    (re.compile(r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b', re.I), '[email]'),
    (re.compile(rf'(?i)((?:last\s*(?:4|four)|id\s*(?:ends?|ending)|هوية|الهوية|آخر\s*[4٤۴])[^\d٠-٩۰-۹\n]{{0,20}}){D}{{4}}(?!{D})'), r'\1[id-last4]'),
]


def redact_text(text: str) -> str:
    for pattern, replacement in PATTERNS:
        text = pattern.sub(replacement, str(text))
    return text


def redact(value):
    if isinstance(value, dict):
        return {key: '[redacted]' if str(key).lower() in SENSITIVE else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return redact_text(value) if isinstance(value, str) else value


def normalise_mobile(value: str) -> str:
    digits = re.sub(r'[\s()+-]', '', str(value).translate(DIGITS))
    if digits.startswith('00966'): digits = '0' + digits[5:]
    elif digits.startswith('966'): digits = '0' + digits[3:]
    if not re.fullmatch(r'05\d{8}', digits): raise ValueError('Invalid verification details')
    return digits
