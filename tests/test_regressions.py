"""Regression coverage for incorrect grades, incomplete replies and saved evaluation evidence."""
import argparse
import asyncio
import csv
import json
from pathlib import Path

import pytest
from rafeeq import evaluate as E
from rafeeq.agent import run_agent
from rafeeq.store import Store, DEMO_IDENTITIES


@pytest.mark.parametrize('answer,term,expected', [
    ('300 SAR','0',False), ('1750 SAR','750',False), ('750 SAR','750',True),
    ('1,500 SAR','1500',True), ('٧٥٠ ريال','750',True), ('another record','not',False),
])
def test_exact_answer_matching(answer,term,expected):
    assert E.contains(answer,term) is expected


def test_failed_tool_is_not_successful_evidence():
    result={'answer':'300 SAR','stopped':'complete','trace':[{'tool':'calculate_fee','ok':False,'result':'{"error":"rejected"}'}]}
    assert not E.grade({'contains_any':['300'],'required_tools':['calculate_fee']},result)


def test_fee_requires_computation_and_exact_answer():
    task={'contains_any':['0','exempt'],'expected_fee':0,'required_tools':['calculate_fee']}
    result={'answer':'300 SAR','stopped':'complete','trace':[{'tool':'calculate_fee','ok':True,'result':'{"fee_sar":0}'}]}
    assert not E.grade(task,result)
    result['answer']='Exempt, 0 SAR'
    assert E.grade(task,result)


def test_approval_grade_checks_database_state():
    task={'contains_any':['approval'],'state_checks':{'pending':1,'inspections':0}}
    result={'answer':'Waiting for approval','stopped':'complete','trace':[]}
    assert E.grade(task,result,{'pending':1,'inspections':0})
    assert not E.grade(task,result,{'pending':0,'inspections':1})


def test_incomplete_reply_cannot_create_proposal(tmp_path):
    class Truncated:
        async def complete(self,messages,tools):
            return {'finish_reason':'length','message':{'role':'assistant','tool_calls':[{'id':'x','type':'function','function':{'name':'propose_inspection','arguments':json.dumps({'application_id':'MDR-1001','day':'2030-01-06'})}}]}}
    store=Store(tmp_path/'db.sqlite')
    token=store.create_session();i=DEMO_IDENTITIES['demo-user'];store.verify(token,i['application_id'],i['last4'],i['mobile'])
    result=asyncio.run(run_agent('Book an inspection',store,Truncated(),session_id=token))
    assert result['stopped']=='incomplete_response'
    assert store.counts('demo-user')=={'pending':0,'inspections':0,'refunds':0,'escalations':0}
    assert result['trace']==[]


def arguments(tmp_path):
    return argparse.Namespace(tasks=Path('tasks.jsonl'),config=['A','B'],trials=1,output=tmp_path/'results')


def test_provider_error_preserves_pending_rows_without_false_scores(tmp_path,monkeypatch):
    calls=[]
    async def unavailable(*args,**kwargs):
        calls.append(1)
        raise RuntimeError('Do not copy this provider response into results')
    monkeypatch.setattr(E,'run_agent',unavailable)
    args=arguments(tmp_path)
    assert asyncio.run(E.evaluate(args,provider=object()))==2
    assert len(calls)==1
    summary=json.loads((args.output/'summary.json').read_text())
    assert summary['run']['mode']=='controlled-test-fixture'
    assert summary['configs']['A']['errors']==1
    assert summary['configs']['A']['pending']==len(E.load_tasks(args.tasks))-1
    assert summary['configs']['A']['completed']==0
    assert summary['configs']['A']['pass_rate'] is None
    assert summary['configs']['B']['pending']==len(E.load_tasks(args.tasks))
    assert 'Do not copy' not in (args.output/'traces.jsonl').read_text()
    with (args.output/'eval-B.csv').open() as stream:
        rows=list(csv.DictReader(stream))
    assert len(rows)==len(E.load_tasks(args.tasks)) and all(r['status']=='pending' for r in rows)


def test_evaluation_preserves_existing_results(tmp_path):
    args=arguments(tmp_path);args.output.mkdir();p=args.output/'eval-A.csv';p.write_text('original evidence')
    with pytest.raises(ValueError,match='already exist'):
        asyncio.run(E.evaluate(args,provider=object()))
    assert p.read_text()=='original evidence'


def test_missing_key_creates_no_live_results(tmp_path,monkeypatch):
    monkeypatch.delenv('OPENROUTER_API_KEY',raising=False)
    monkeypatch.setenv('RAFEEQ_PROVIDER','openrouter')
    args=arguments(tmp_path)
    with pytest.raises(ValueError,match='key is missing'):
        asyncio.run(E.evaluate(args))
    assert not args.output.exists()


def test_task_suite_validates_minimum_and_unique_ids(tmp_path):
    tasks=[json.loads(s) for s in Path('tasks.jsonl').read_text().splitlines()]
    path=tmp_path/'tasks.jsonl'
    path.write_text('\n'.join(json.dumps(t) for t in tasks[:14]))
    with pytest.raises(ValueError,match='15'):E.load_tasks(path)
    tasks[-1]['id']=tasks[0]['id']
    path.write_text('\n'.join(json.dumps(t) for t in tasks))
    with pytest.raises(ValueError,match='unique'):E.load_tasks(path)


def test_approval_requires_boolean(tmp_path):
    with pytest.raises(ValueError,match='boolean'):
        Store(tmp_path/'db.sqlite').decide('missing','false','demo-user')
