"""Local policy-retrieval benchmark; no model calls, private records or action execution."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import sklearn
from rafeeq.retrieval import PolicyIndex, documents, MIN_SCORE, WORD_WEIGHT, ALIASES

ROOT = Path(__file__).resolve().parents[1]


def run(tasks_path, output):
    tasks = [json.loads(s) for s in tasks_path.read_text().splitlines() if s.strip()]
    if not tasks or len({t['id'] for t in tasks})!=len(tasks): raise ValueError('Task IDs must be unique')
    docs = documents()
    ids = {d['id'] for d in docs}
    if any(t['expected_policy'] not in ids | {None} for t in tasks): raise ValueError('Unknown expected policy')
    index = PolicyIndex(docs)
    rows = []
    for mode in ('A','B'):
        for task in tasks:
            start = time.perf_counter()
            hits = index.search(task['query'],mode,limit=2)
            top = hits[0]['id'] if hits else None
            rows.append({'config':mode,'task':task['id'],'query':task['query'],'expected_policy':task['expected_policy'] or '',
                         'top_policy':top or '', 'passed':top==task['expected_policy'],
                         'hit_at_2':task['expected_policy'] in [h['id'] for h in hits] if task['expected_policy'] else not hits,
                         'score':hits[0]['score'] if hits else 0,'seconds':round(time.perf_counter()-start,6),
                         'llm_requests':0,'llm_tokens':0,'provider_cost_usd':0})
    commit = subprocess.run(['git','-C',str(ROOT),'rev-parse','HEAD'],capture_output=True,text=True)
    metadata = {'scope':'local policy retrieval only; not a full-assistant evaluation',
                'ran_at':datetime.now(timezone.utc).isoformat(),'source_commit':commit.stdout.strip() if commit.returncode==0 else None,
                'tasks_sha256':hashlib.sha256(tasks_path.read_bytes()).hexdigest(),
                'corpus':{d['id']:hashlib.sha256(d['text'].encode()).hexdigest() for d in docs},
                'implementation_sha256':hashlib.sha256((ROOT/'rafeeq/retrieval.py').read_bytes()).hexdigest(),
                'python':platform.python_version(),'scikit_learn':sklearn.__version__,
                'minimum_score':MIN_SCORE,'hybrid_word_weight':WORD_WEIGHT,'query_aliases':ALIASES}
    summary = {m:{'passed':sum(r['passed'] for r in rows if r['config']==m),'total':len(tasks),
                  'hit_at_2':sum(r['hit_at_2'] for r in rows if r['config']==m),
                  'llm_requests':0,'llm_tokens':0,'provider_cost_usd':0} for m in ('A','B')}
    output.mkdir(parents=True,exist_ok=True)
    for mode in ('A','B'):
        with (output/f'{mode}.csv').open('w',newline='',encoding='utf-8') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(r for r in rows if r['config']==mode)
    (output/'summary.json').write_text(json.dumps({'run':metadata,'configs':summary},indent=2,ensure_ascii=False)+'\n')
    report=['# Local retrieval evaluation','',metadata['scope']+'.','',
            '| Configuration | Top-1 matches | LLM requests | LLM tokens | Provider cost |',
            '|---|---:|---:|---:|---:|']
    for mode,label in [('A','word TF-IDF'),('B','word + character TF-IDF')]:
        s=summary[mode];report.append(f"| {mode}: {label} | {s['passed']}/{s['total']} ({s['passed']/s['total']:.1%}) | 0 | 0 | $0.00 |")
    report+=['','## Method','',
             'The same frozen questions, five policies, query aliases and relevance threshold are used in both settings. A uses word unigrams/bigrams. B combines 70% word similarity and 30% character 3–5-gram similarity. The primary metric is whether the highest-ranked policy matches the expected source; the out-of-scope case must return no result.',
             '', 'These are small synthetic document-retrieval checks. They do not grade generated answers, fees, identity verification, approval or resistance to live model attacks. Zero requests/tokens/cost means no inference provider was used; local CPU work is still required.',
             '', '## Mismatches','']
    mismatches=[r for r in rows if not r['passed']]
    for r in mismatches:report.append(f"- {r['config']} / {r['task']}: expected {r['expected_policy'] or 'no result'}, retrieved {r['top_policy'] or 'no result'}.")
    if not mismatches:report.append('No top-1 mismatches in this frozen set. This is not a claim of general retrieval accuracy.')
    (output/'REPORT.md').write_text('\n'.join(report)+'\n')
    print(json.dumps(summary,indent=2))
    return 1 if mismatches else 0


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tasks',type=Path,default=ROOT/'evaluations/retrieval/tasks.jsonl')
    parser.add_argument('--output',type=Path,default=ROOT/'evaluations/retrieval/results')
    args=parser.parse_args()
    return run(args.tasks,args.output)


if __name__=='__main__':raise SystemExit(main())
