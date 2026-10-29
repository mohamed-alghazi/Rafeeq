import argparse
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from rafeeq.agent import OpenRouterProvider, run_agent
from rafeeq.store import Store

load_dotenv()
p=argparse.ArgumentParser(description='Rafeeq synthetic municipal assistant')
p.add_argument('command',choices=['ask']);p.add_argument('question');p.add_argument('--config',choices=['A','B'],default='B')
a=p.parse_args()
try:
    r=asyncio.run(run_agent(a.question,Store(Path('.runtime/rafeeq.sqlite')),OpenRouterProvider(),a.config))
    print(r['answer'])
    for pending in r.get('pending',[]): print('Human approval required:',pending)
except ValueError as exc:p.exit(2,str(exc)+'\n')
