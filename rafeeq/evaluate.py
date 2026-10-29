"""Live A/B evaluation. Fixture tests never create live results in this repository."""
from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from dotenv import load_dotenv
from rafeeq.agent import OpenRouterProvider, run_agent
from rafeeq.store import Store, DEMO_IDENTITIES
from rafeeq.privacy import redact
from rafeeq.evaluation_state import fingerprint, source_commit, write_progress, read_progress, output_lock

DIGITS = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹', '01234567890123456789')
TOOLS = {'search_policy','calculate_fee','get_application','list_inspections','propose_inspection','propose_reschedule','propose_refund','propose_escalation'}


def contains(answer: str, term: str) -> bool:
    answer = answer.lower().translate(DIGITS)
    term = str(term).lower().translate(DIGITS)
    if re.fullmatch(r'\d[\d,]*(?:\.\d+)?', term):
        # A zero inside 300, or 750 inside 1750, must not pass.
        answer = re.sub(r'(?<=\d)[,٬](?=\d)', '', answer)
        number = re.escape(term.replace(',', ''))
        return bool(re.search(r'(?<![\w.])' + number + r'(?:\.0+)?(?![\w.])', answer))
    if re.fullmatch(r'[a-z]+', term):
        return bool(re.search(r'\b' + re.escape(term) + r'\b', answer))
    return term in answer


def grade_checks(task: dict, result: dict, state: dict | None = None) -> dict:
    answer = result['answer']
    trace = result['trace']
    successful = [t['tool'] for t in trace if t.get('ok') is True]
    attempted = [t['tool'] for t in trace]
    checks = {'completed': result['stopped'] == 'complete'}
    if task.get('contains_any'):
        checks['answer'] = any(contains(answer, v) for v in task['contains_any'])
    for tool in task.get('required_tools', []):
        checks['successful:' + tool] = tool in successful
    for tool in task.get('required_attempts', []):
        checks['attempted:' + tool] = tool in attempted
    for tool in task.get('denied_tools', []):
        calls = [t for t in trace if t['tool'] == tool]
        checks['denied:' + tool] = bool(calls) and all(t.get('ok') is False for t in calls)
    for tool in task.get('forbidden_tools', []):
        checks['not_called:' + tool] = tool not in attempted
    for term in task.get('not_contains', []):
        checks['not_disclosed:' + term] = not contains(answer, term)
    if 'expected_fee' in task:
        expected = task['expected_fee']
        fees = []
        for event in trace:
            if event['tool'] == 'calculate_fee' and event.get('ok') is True:
                try:
                    payload = json.loads(event['result'])
                    if isinstance(payload, dict):
                        fees.append(payload.get('fee_sar'))
                except (ValueError, TypeError):
                    pass
        checks['computed_fee'] = expected in fees
        checks['quoted_fee'] = contains(answer, str(expected)) or (
            expected == 0 and any(contains(answer, t) for t in ('exempt', 'معف')))
    if task.get('expected_action'):
        expected = task['expected_action']
        actions = []
        for event in trace:
            if event['tool'].startswith('propose_') and event.get('ok') is True:
                try: actions.append(json.loads(event['result']))
                except (ValueError,TypeError): pass
        checks['action_details'] = any(all(action.get(k) == v for k,v in expected.items()) for action in actions)
    if task.get('required_source'):
        checks['source'] = contains(answer, task['required_source'])
    for name, expected in task.get('state_checks', {}).items():
        checks['state:' + name] = state is not None and state.get(name) == expected
    return checks


def grade(task, result, state=None):
    checks = grade_checks(task, result, state)
    return len(checks) > 1 and all(checks.values())


def load_tasks(path: Path) -> list:
    tasks = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if len(tasks) < 15:
        raise ValueError('The capstone suite requires at least 15 tasks.')
    ids = [t.get('id', '') for t in tasks]
    if len(set(ids)) != len(ids) or any(not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', t) for t in ids):
        raise ValueError('Task IDs must be unique, nonempty identifiers.')
    for task in tasks:
        if not task.get('prompt') or not task.get('category') or not task.get('contains_any'):
            raise ValueError('Each task needs a prompt, category and answer checks.')
        for name in ('required_tools', 'required_attempts', 'denied_tools'):
            if not set(task.get(name, [])) <= TOOLS:
                raise ValueError('Unknown tool in task ' + task['id'])
    return tasks


def atomic_text(path: Path, text: str):
    temporary = path.with_name('.' + path.name + '.tmp')
    temporary.write_text(text, encoding='utf-8')
    temporary.replace(path)


def save_progress(output: Path, rows: list, configs: list, metadata: dict):
    output.mkdir(parents=True, exist_ok=True)
    rows = redact(rows)
    write_progress(output/'progress.json', metadata, rows)
    columns = ['config', 'trial', 'task', 'category', 'status', 'stopped', 'requests', 'tokens', 'seconds', 'answer', 'checks']
    summaries = {}
    analysis = ['# Live evaluation error analysis', '',
                'Pending tasks and runtime/provider errors are not scored model outcomes.', '',
                '| Config | Category | Scored failures | Runtime errors | Pending |',
                '|---|---|---:|---:|---:|']
    for config in configs:
        subset = [r for r in rows if r['config'] == config]
        temporary = output / ('.eval-' + config + '.csv.tmp')
        with temporary.open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            for row in subset:
                values = {k: row[k] for k in columns}
                values['checks'] = json.dumps(values['checks'], ensure_ascii=False)
                writer.writerow(values)
        temporary.replace(output / f'eval-{config}.csv')
        counts = Counter(r['status'] for r in subset)
        completed = counts['passed'] + counts['failed']
        grouped = {r['task']: [v for v in subset if v['task'] == r['task']] for r in subset}
        complete_suite = completed == len(subset)
        summaries[config] = {
            'planned': len(subset), 'completed': completed, 'passed': counts['passed'],
            'failed': counts['failed'], 'errors': counts['error'], 'pending': counts['pending'],
            'pass_rate': counts['passed'] / completed if completed else None,
            'all_trials_pass_fraction': sum(all(r['status'] == 'passed' for r in group) for group in grouped.values()) / len(grouped) if complete_suite else None,
        }
        for category in sorted({r['category'] for r in subset}):
            c = Counter(r['status'] for r in subset if r['category'] == category)
            analysis.append(f"| {config} | {category} | {c['failed']} | {c['error']} | {c['pending']} |")
    analysis += ['', '## Failed checks and runtime stops', '']
    for row in rows:
        if row['status'] in {'failed', 'error'}:
            failed = ', '.join(k for k, passed in row['checks'].items() if not passed)
            analysis.append(f"- {row['config']} / {row['task']} / trial {row['trial']}: {failed or row['stopped']}")
    analysis += ['', '## A/B changes', '']
    for task_id in dict.fromkeys(r['task'] for r in rows):
        a = [r for r in rows if r['task'] == task_id and r['config'] == 'A']
        b = [r for r in rows if r['task'] == task_id and r['config'] == 'B']
        if a and b and all(r['status'] in {'passed', 'failed'} for r in a + b):
            a_rate = sum(r['status'] == 'passed' for r in a) / len(a)
            b_rate = sum(r['status'] == 'passed' for r in b) / len(b)
            if a_rate != b_rate:
                analysis.append(f'- {task_id}: A={a_rate:.0%}, B={b_rate:.0%}. Inspect the saved traces before attributing a cause.')
    atomic_text(output / 'summary.json', json.dumps({'run': metadata, 'configs': summaries}, indent=2))
    atomic_text(output / 'traces.jsonl', ''.join(json.dumps({k: v for k, v in r.items()}, ensure_ascii=False) + '\n' for r in rows if r['status'] != 'pending'))
    atomic_text(output / 'error-analysis.md', '\n'.join(analysis) + '\n')
    return summaries


def prepare_task(task, store):
    token = store.create_session()
    owner = task.get('verified_as')
    if owner:
        if owner not in DEMO_IDENTITIES: raise ValueError('Unknown synthetic evaluation identity')
        identity = DEMO_IDENTITIES[owner]
        store.verify(token, identity['application_id'], identity['last4'], identity['mobile'])
    prompt = task['prompt']
    if task.get('fixture_inspection'):
        if not owner: raise ValueError('Inspection fixture requires a verified identity')
        p = store.propose(task['fixture_inspection']['application_id'], task['fixture_inspection']['day'], owner, token)
        outcome = store.decide(p['proposal_id'], True, owner, token)
        prompt = prompt.replace('{{inspection_id}}', outcome['inspection_id'])
    return token, prompt


async def evaluate(args, provider=None):
    tasks = load_tasks(args.tasks)
    if len(set(args.config)) != len(args.config): raise ValueError('Configurations must not be repeated.')
    if args.trials < 1: raise ValueError('Trials must be positive.')
    resume = getattr(args,'resume',False)
    max_tasks = getattr(args,'max_tasks',None)
    if max_tasks is not None and max_tasks < 1: raise ValueError('--max-tasks must be positive')
    targets = [args.output/f'eval-{c}.csv' for c in args.config] + [args.output/'summary.json',args.output/'progress.json',args.output/'traces.jsonl']
    if not resume and any(p.exists() for p in targets):
        raise ValueError('Results already exist. Use --resume or a new --output directory.')
    if resume and not (args.output/'progress.json').exists(): raise ValueError('No resumable evaluation state exists')
    owned_provider = provider is None
    provider = provider or OpenRouterProvider()  # Missing key never creates result files.
    mode = 'live' if owned_provider else 'controlled-test-fixture'
    try:
        run_hash, identity = fingerprint(args.tasks,args.config,args.trials,provider,mode)
        rows = [dict(config=c,trial=trial,task=t['id'],category=t['category'],status='pending',stopped='',requests=None,
                     tokens=None,seconds=None,answer='',checks={})
                for c in args.config for trial in range(1,args.trials+1) for t in tasks]
        keys = [(r['config'],r['trial'],r['task']) for r in rows]
        metadata = {'started_at':datetime.now(timezone.utc).isoformat(),'model':getattr(provider,'model','controlled-test-fixture'),
                    'tasks_sha256':identity['tasks'],'spec_sha256':identity['files']['rafeeq/spec.md'],
                    'trials':args.trials,'mode':mode,'fingerprint':run_hash,'source_commit':source_commit(),'identity':identity}
        with output_lock(args.output):
            if resume:
                metadata,rows = read_progress(args.output/'progress.json',run_hash,keys)
            elif any(p.exists() for p in targets):
                raise ValueError('Results already exist. Use --resume or a new --output directory.')
            lookup = {t['id']:t for t in tasks}
            executed = 0
            for row in rows:
                if row['status'] in {'passed','failed'}: continue
                if max_tasks is not None and executed >= max_tasks:
                    save_progress(args.output,rows,args.config,metadata)
                    print('Batch limit reached. Continue with the same command and --resume.')
                    return 2
                if row['status'] == 'error':
                    row.setdefault('previous_errors',[]).append({k:row[k] for k in ('stopped','seconds')})
                row.update(status='pending',stopped='',requests=None,tokens=None,seconds=None,answer='',checks={})
                started = time.monotonic()
                task = lookup[row['task']]
                with TemporaryDirectory() as tmp:
                    store = Store(Path(tmp)/'db.sqlite')
                    try:
                        token,prompt = prepare_task(task,store)
                        result = await asyncio.wait_for(run_agent(prompt,store,provider,row['config'],session_id=token),timeout=180)
                        state = store.counts(task.get('verified_as','demo-user'))
                        checks = grade_checks(task,result,state)
                        row.update(status='passed' if len(checks)>1 and all(checks.values()) else 'failed',stopped=result['stopped'],
                                   requests=result['requests'],tokens=result['tokens'],answer=result['answer'],checks=checks,
                                   trace=result['trace'],state=state)
                    except Exception as exc:
                        row.update(status='error',stopped=type(exc).__name__,answer='Runtime or provider error; no scored model outcome.')
                    row['seconds'] = round(time.monotonic()-started,3)
                    save_progress(args.output,rows,args.config,metadata)
                    executed += 1
                    if row['status'] == 'error':
                        print('Stopped after a runtime/provider error. Completed work is saved; resume after fixing access or quota.')
                        return 2
            summary = save_progress(args.output,rows,args.config,metadata)
            print(json.dumps(summary,indent=2))
            return 0 if all(r['status']=='passed' for r in rows) else 1
    finally:
        if owned_provider: await provider.close()


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tasks', type=Path, nargs='?', default=Path('tasks.jsonl'))
    parser.add_argument('--config', nargs='+', choices=['A', 'B'], default=['A', 'B'])
    parser.add_argument('--trials', type=int, default=1)
    parser.add_argument('--output', type=Path, default=Path('results'))
    parser.add_argument('--resume',action='store_true',help='Continue matching pending/error tasks; preserve scored outcomes')
    parser.add_argument('--max-tasks',type=int,help='Maximum tasks attempted in this invocation; resume the remainder later')
    args = parser.parse_args()
    try:
        return asyncio.run(evaluate(args))
    except (ValueError, OSError) as exc:
        parser.exit(2, str(exc) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())
