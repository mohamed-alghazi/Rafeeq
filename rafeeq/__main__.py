"""Local terminal client with isolated sessions and separate credential input."""
import argparse
import asyncio
import getpass
from pathlib import Path
from dotenv import load_dotenv
from rafeeq.agent import OpenRouterProvider, run_agent
from rafeeq.store import Store


def main():
    load_dotenv()
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    ask=sub.add_parser('ask');ask.add_argument('question');ask.add_argument('--config',choices=['A','B'],default='B')
    chat=sub.add_parser('chat');chat.add_argument('--config',choices=['A','B'],default='B')
    args=parser.parse_args()
    store=Store(Path('.runtime/rafeeq.sqlite'));token=store.create_session()
    async def request(question):
        provider=OpenRouterProvider()
        try:return await asyncio.wait_for(run_agent(question,store,provider,args.config,session_id=token),timeout=180)
        finally:await provider.close()
    try:
        if args.command=='ask':
            result=asyncio.run(request(args.question));print(result['answer'])
            return 0 if result['stopped']=='complete' else 2
        print('Commands: /verify, /approve, /clear, /quit. Never enter identity credentials into chat.')
        while True:
            message=input('You: ').strip()
            if not message or message=='/quit':return 0
            if message=='/verify':
                try:
                    store.verify(token,input('Application ID: ').strip(),getpass.getpass('Last 4 ID digits: '),getpass.getpass('Registered mobile: '))
                    print('Applicant verified.')
                except ValueError as exc:print(str(exc))
            elif message=='/clear':store.clear_history(token);print('Conversation cleared.')
            elif message=='/approve':
                owner=store.session(token,True)['owner']
                for action in store.pending(owner,token):
                    print(action)
                    answer=input('Approve these exact details? [y/N]: ').strip().lower()
                    print(store.decide(action['proposal_id'],answer=='y',owner,token))
            else:
                result=asyncio.run(request(message));print('Rafeeq:',result['answer'])
    except (ValueError,TimeoutError) as exc:parser.exit(2,str(exc)+'\n')
    except KeyboardInterrupt:return 0


if __name__=='__main__':raise SystemExit(main())
