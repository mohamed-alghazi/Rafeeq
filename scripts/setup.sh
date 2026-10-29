#!/usr/bin/env bash
set -euo pipefail
cd /workspace/Rafeeq
export UV_CACHE_DIR=/workspace/.uv-cache
uv sync --frozen
python - <<'PY'
from pathlib import Path
import secrets
p=Path('.env')
if not p.exists():
    p.write_text('RAFEEQ_ACCESS_TOKEN='+secrets.token_urlsafe(32)+'\nRAFEEQ_PROVIDER=openrouter\nRAFEEQ_MODEL=google/gemma-4-31b-it:free\n')
    p.chmod(0o600)
PY
