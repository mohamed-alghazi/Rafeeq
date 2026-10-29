"""Live model evaluation only. Missing credentials fail before creating result files."""
import argparse
import asyncio
import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from dotenv import load_dotenv
from rafeeq.agent import OpenRouterProvider, run_agent
from rafeeq.store import Store


def grade(task, result):
    answer=result['answer'].lower()
    called=[t['tool'] for t in result['trace']]
    checks=[]
    if task.get('contains_any'): checks.append(any(str(v).lower() in answer for v in task['contains_any']))
    for tool in task.get('required_tools',[]): checks.append(tool in called)
    for tool in task.get('forbidden_tools',[]): checks.append(tool not in called)
    for term in task.get('not_contains',[]): checks.append(term.lower() not in answer)
    return result['stopped']=='complete' and bool(checks) and all(checks)


async def evaluate(args):
    provider=OpenRouterProvider()
    tasks=[json.loads(line) for line in args.tasks.read_text().splitlines() if line.strip()]
    rows=[]
    for config in args.config:
        for trial in range(args.trials):
            for task in tasks:
                with TemporaryDirectory() as tmp:
                    try:
                        result=await run_agent(task['prompt'],Store(Path(tmp)/'db'),provider,config)
                        rows.append({'config':config,'trial':trial+1,'task':task['id'],'category':task['category'],'passed':grade(task,result),'stopped':result['stopped'],'requests':result['requests'],'tokens':result['tokens'],'answer':result['answer']})
                    except Exception as exc:
                        rows.append({'config':config,'trial':trial+1,'task':task['id'],'category':task['category'],'passed':False,'stopped':type(exc).__name__,'requests':'','tokens':'','answer':'Provider or runtime failure; inspect service configuration.'})
    args.output.mkdir(parents=True,exist_ok=True)
    for config in args.config:
        subset=[r for r in rows if r['config']==config]
        with (args.output/f'eval-{config}.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(subset[0]));writer.writeheader();writer.writerows(subset)
    summary={c:{'passed':sum(r['passed'] for r in rows if r['config']==c),'total':sum(r['config']==c for r in rows),'all_trials_pass_fraction':sum(all(r['passed'] for r in rows if r['config']==c and r['task']==t['id']) for t in tasks)/len(tasks)} for c in args.config}
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))
    return 0 if all(r['passed'] for r in rows) else 1


def main():
    load_dotenv()
    p=argparse.ArgumentParser();p.add_argument('tasks',type=Path,nargs='?',default=Path('tasks.jsonl'))
    p.add_argument('--config',nargs='+',choices=['A','B'],default=['A','B']);p.add_argument('--trials',type=int,default=1);p.add_argument('--output',type=Path,default=Path('results'))
    args=p.parse_args()
    if args.trials<1:p.error('--trials must be positive')
    try:return asyncio.run(evaluate(args))
    except ValueError as exc:p.exit(2,str(exc)+'\n')

if __name__=='__main__':raise SystemExit(main())
