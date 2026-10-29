"""Versioned, checksummed evaluation state. CSVs are derived from progress.json."""
from __future__ import annotations

import hashlib
import json
import subprocess
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()


def fingerprint(tasks, configs, trials, provider, mode):
    paths = [*sorted((ROOT/'rafeeq').glob('*.py')), ROOT/'rafeeq/spec.md',
             *sorted((ROOT/'data/policies').glob('*.md')), ROOT/'pyproject.toml', ROOT/'uv.lock']
    files = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    identity = {'schema':2,'files':files,'tasks':hashlib.sha256(tasks.read_bytes()).hexdigest(),
                'configs':configs,'trials':trials,'model':getattr(provider,'model','controlled-test-fixture'),
                'provider':getattr(provider,'provider_name','controlled-test-fixture'),'mode':mode}
    return hashlib.sha256(encoded(identity)).hexdigest(), identity


def source_commit():
    result = subprocess.run(['git','-C',str(ROOT),'rev-parse','HEAD'],capture_output=True,text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def write_progress(path, metadata, rows):
    payload = {'run':metadata,'rows':rows}
    document = {'sha256':hashlib.sha256(encoded(payload)).hexdigest(),'payload':payload}
    temporary = path.with_name('.progress.json.tmp')
    temporary.write_bytes(encoded(document))
    temporary.replace(path)


def read_progress(path, expected_fingerprint, expected_keys):
    try:
        document = json.loads(path.read_text())
        payload = document['payload']
        if hashlib.sha256(encoded(payload)).hexdigest() != document['sha256']:
            raise ValueError('Saved evaluation checksum mismatch')
        if payload['run']['fingerprint'] != expected_fingerprint:
            raise ValueError('Code, tasks, model or configuration changed. Use a new output directory.')
        rows = payload['rows']
        keys = [(r['config'],r['trial'],r['task']) for r in rows]
        if keys != expected_keys or len(set(keys)) != len(keys):
            raise ValueError('Saved evaluation task coverage mismatch')
        if any(r['status'] not in {'passed','failed','error','pending'} for r in rows):
            raise ValueError('Invalid saved evaluation status')
        return payload['run'], rows
    except (KeyError,TypeError,OSError,json.JSONDecodeError) as exc:
        raise ValueError('Saved evaluation state is missing or invalid') from exc


@contextmanager
def output_lock(output: Path):
    # Advisory locks are released by the OS even if the process is interrupted.
    try: import fcntl
    except ImportError: raise ValueError('Evaluation locking requires Linux, macOS or WSL') from None
    output.mkdir(parents=True,exist_ok=True)
    with (output/'.evaluation.lock').open('a') as stream:
        try: fcntl.flock(stream,fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('Another evaluation is writing this output directory') from None
        try: yield
        finally: fcntl.flock(stream,fcntl.LOCK_UN)
