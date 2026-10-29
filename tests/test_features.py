import argparse
import asyncio
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from rafeeq import evaluate as E
from rafeeq.agent import run_agent
from rafeeq.evaluation_state import output_lock
from rafeeq.privacy import redact, redact_text
from rafeeq.store import Store, DEMO_IDENTITIES


def session(store,owner='demo-user'):
    token=store.create_session();i=DEMO_IDENTITIES[owner]
    store.verify(token,i['application_id'],i['last4'],i['mobile'])
    return token


def test_verification_normalises_digits_and_locks(tmp_path):
    s=Store(tmp_path/'db');t=s.create_session()
    assert s.verify(t,'MDR-1001','٠٠٠١','+966 550001001')['verified']
    other=s.create_session()
    for _ in range(3):
        with pytest.raises(ValueError,match='Invalid verification'):s.verify(other,'MDR-1001','9999','0550001001')
    assert s.session(other)['locked']
    with pytest.raises(ValueError,match='locked'):s.verify(other,'MDR-1001','0001','0550001001')


def test_owner_switch_and_expiry(tmp_path):
    s=Store(tmp_path/'db');t=session(s)
    with pytest.raises(ValueError):s.verify(t,'MDR-2001','0002','0550002002')
    t=session(s);s.remember(t,'My application?','under_review')
    with s.connect() as db:db.execute('UPDATE sessions SET verified_until=0 WHERE id=?',(s._session_key(t),))
    assert not s.session(t)['verified'] and s.history(t)==[]
    with pytest.raises(ValueError):s.session(t,True)
    s.verify(t,'MDR-1001','0001','0550001001')
    assert s.history(t)[-1]['content']=='under_review'


@pytest.mark.parametrize('text,secret',[
    ('mobile 0550001001','0550001001'),('mobile +966 55 000 1001','55 000 1001'),
    ('جوال ٠٥٥٠٠٠١٠٠١','٠٥٥٠٠٠١٠٠١'),('national ID 1234567890','1234567890'),
    ('ID ends 0001','0001'),('email person@example.com','person@example.com'),
    ('key sk-or-v1-'+'a'*32,'sk-or-v1-'),('Authorization: Bearer abcdefghijklmnop','abcdefghijklmnop'),
])
def test_redaction(text,secret):
    assert secret not in redact_text(text)
    assert redact_text('MDR-1001 on 2030-01-06 costs 750 SAR')=='MDR-1001 on 2030-01-06 costs 750 SAR'
    assert redact({'mobile':secret})['mobile']=='[redacted]'


def test_memory_is_bounded_isolated_redacted_and_persistent(tmp_path):
    path=tmp_path/'db';s=Store(path);a=session(s);b=session(s)
    s.remember(a,'My mobile is 0550001001; ID ends 0001','No need to share person@example.com')
    history=s.history(a)
    assert '0550001001' not in str(history) and '0001' not in str(history) and 'person@example.com' not in str(history)
    assert s.history(b)==[] and Store(path).history(a)==history
    assert a.encode() not in path.read_bytes()
    for _ in range(20):s.remember(a,'x'*1000,'y'*1000)
    h=s.history(a);assert len(h)<=12 and sum(len(m['content']) for m in h)<=8000 and h[0]['role']=='user'
    s.clear_history(a);assert s.history(a)==[]


def test_actions_are_bound_to_verified_session(tmp_path):
    s=Store(tmp_path/'db');a=session(s);b=session(s)
    p=s.propose('MDR-1001','2030-01-06','demo-user',a)
    assert s.pending('demo-user',b)==[]
    with pytest.raises(ValueError):s.decide(p['proposal_id'],True,'demo-user',b)
    assert s.counts('demo-user')['inspections']==0
    assert s.decide(p['proposal_id'],True,'demo-user',a)['booked']
    with pytest.raises(ValueError):s.decide(p['proposal_id'],True,'demo-user',a)


def test_rescheduling_requires_approval_and_detects_stale_proposal(tmp_path):
    s=Store(tmp_path/'db');t=session(s)
    p=s.propose('MDR-1001','2030-01-06','demo-user',t);s.decide(p['proposal_id'],True,'demo-user',t)
    a=s.reschedule(p['proposal_id'],'2030-01-08','demo-user',t)
    b=s.reschedule(p['proposal_id'],'2030-01-09','demo-user',t)
    assert s.inspections('MDR-1001','demo-user')['inspections'][0]['day']=='2030-01-06'
    assert s.decide(a['proposal_id'],True,'demo-user',t)['rescheduled']
    with pytest.raises(ValueError,match='changed'):s.decide(b['proposal_id'],True,'demo-user',t)
    assert s.inspections('MDR-1001','demo-user')['inspections'][0]['day']=='2030-01-08'


@pytest.mark.parametrize('app,amount,status',[
    ('MDR-1002',650,'approved_request'),('MDR-1003',1280,'pending_finance'),
    ('MDR-1004',167.5,'approved_request'),('MDR-1005',750,'approved_request')])
def test_policy_refund_amount_finance_gate_and_duplicate_prevention(tmp_path,app,amount,status):
    s=Store(tmp_path/'db');t=session(s);p=s.refund(app,'demo-user',t)
    assert p['amount_sar']==amount and s.counts('demo-user')['refunds']==0
    result=s.decide(p['proposal_id'],True,'demo-user',t)
    assert result['amount_sar']==amount and result['refund_status']==status and result['paid'] is False
    with pytest.raises(ValueError,match='already'):s.refund(app,'demo-user',t)


def test_refund_rejection_ineligibility_and_revalidation(tmp_path):
    s=Store(tmp_path/'db');t=session(s)
    with pytest.raises(ValueError,match='eligible'):s.refund('MDR-1001','demo-user',t)
    p=s.refund('MDR-1002','demo-user',t);s.decide(p['proposal_id'],False,'demo-user',t)
    assert s.counts('demo-user')['refunds']==0
    p=s.refund('MDR-1002','demo-user',t)
    with s.connect() as db:db.execute("UPDATE applications SET fee_paid=900 WHERE id='MDR-1002'")
    with pytest.raises(ValueError,match='changed'):s.decide(p['proposal_id'],True,'demo-user',t)


def test_escalation_policy_and_human_gate(tmp_path):
    s=Store(tmp_path/'db');t=session(s)
    with pytest.raises(ValueError):s.escalate('MDR-1002','demo-user',t)
    p=s.escalate('MDR-1001','demo-user',t);assert p['overdue_working_days']>0
    assert s.counts('demo-user')['escalations']==0
    assert s.decide(p['proposal_id'],True,'demo-user',t)['escalated']
    with pytest.raises(ValueError,match='already'):s.escalate('MDR-1001','demo-user',t)


def test_api_verification_session_boundaries_and_safe_validation(tmp_path,monkeypatch):
    from rafeeq import api
    monkeypatch.setenv('RAFEEQ_ACCESS_TOKEN','test-code');monkeypatch.setattr(api,'store',Store(tmp_path/'db'))
    c=TestClient(api.app);base={'Authorization':'Bearer test-code'}
    a=c.post('/api/sessions',headers=base).json()['session_token']
    h=base|{'X-Rafeeq-Session':a}
    assert c.get('/api/proposals',headers=h).status_code==403
    identity=DEMO_IDENTITIES['demo-user']
    assert c.post('/api/session/verify',headers=h,json={k:identity[k] for k in ('application_id','last4','mobile')}).status_code==200
    invalid=c.post('/api/session/verify',headers=h,json={'application_id':'MDR-1001','last4':'0001','mobile':'0550001001','secret':'private'})
    assert invalid.status_code==422 and '0550001001' not in invalid.text and 'private' not in invalid.text
    p=api.store.refund('MDR-1002','demo-user',a)
    b=c.post('/api/sessions',headers=base).json()['session_token'];hb=base|{'X-Rafeeq-Session':b}
    c.post('/api/session/verify',headers=hb,json={k:identity[k] for k in ('application_id','last4','mobile')})
    assert c.get('/api/proposals',headers=hb).json()==[]
    endpoint=f"/api/proposals/{p['proposal_id']}/decision"
    assert c.post(endpoint,headers=hb,json={'approve':True}).status_code==409
    assert c.post(endpoint,headers=h,json={'approve':True}).json()['amount_sar']==650


def test_agent_uses_session_memory_and_denies_unverified_private_access(tmp_path):
    s=Store(tmp_path/'db');t=s.create_session();seen=[]
    class Replies:
        async def complete(self,messages,tools):
            seen.append(json.loads(json.dumps(messages)))
            if len(seen)==1:
                return {'message':{'role':'assistant','tool_calls':[{'id':'1','type':'function','function':{'name':'get_application','arguments':'{"application_id":"MDR-1001"}'}}]}}
            return {'message':{'role':'assistant','content':'Please verify first. Mobile 0550001001 is private.'}}
    first=asyncio.run(run_agent('My mobile is 0550001001',s,Replies(),session_id=t))
    assert first['trace'][0]['ok'] is False and '0550001001' not in json.dumps(first)
    seen.clear()
    class Recall:
        async def complete(self,messages,tools):
            seen.extend(messages)
            return {'message':{'role':'assistant','content':'I can see the previous turn.'}}
    asyncio.run(run_agent('What did we discuss?',s,Recall(),session_id=t))
    assert len([m for m in seen if m['role']=='user'])==2
    assert '0550001001' not in json.dumps(seen)


def small_suite(tmp_path):
    tasks=tmp_path/'tasks.jsonl'
    tasks.write_text('\n'.join(json.dumps({'id':f't{i}','category':'test','prompt':'check','contains_any':['done']}) for i in range(15)))
    return argparse.Namespace(tasks=tasks,config=['A','B'],trials=1,output=tmp_path/'results',resume=False,max_tasks=2)


async def fixture_answer(*args,**kwargs):
    return {'answer':'done','stopped':'complete','trace':[],'requests':1,'tokens':1}


def test_evaluation_resume_preserves_scored_rows_and_finishes(tmp_path,monkeypatch):
    args=small_suite(tmp_path);monkeypatch.setattr(E,'run_agent',fixture_answer)
    assert asyncio.run(E.evaluate(args,provider=object()))==2
    first=json.loads((args.output/'progress.json').read_text())['payload']['rows'][0]
    args.resume=True;args.max_tasks=None
    assert asyncio.run(E.evaluate(args,provider=object()))==0
    saved=json.loads((args.output/'progress.json').read_text())['payload']['rows']
    assert saved[0]==first and len(saved)==30 and all(r['status']=='passed' for r in saved)
    assert asyncio.run(E.evaluate(args,provider=object()))==0


def test_resume_rejects_changed_tasks_and_corrupted_state(tmp_path,monkeypatch):
    args=small_suite(tmp_path);monkeypatch.setattr(E,'run_agent',fixture_answer)
    asyncio.run(E.evaluate(args,provider=object()));args.resume=True
    old=args.tasks.read_text();args.tasks.write_text(old.replace('check','changed'))
    with pytest.raises(ValueError,match='changed'):asyncio.run(E.evaluate(args,provider=object()))
    args.tasks.write_text(old)
    progress=args.output/'progress.json';state=json.loads(progress.read_text());state['payload']['rows'][0]['status']='failed';progress.write_text(json.dumps(state))
    with pytest.raises(ValueError,match='checksum'):asyncio.run(E.evaluate(args,provider=object()))


def test_evaluation_lock_prevents_concurrent_writer(tmp_path):
    with output_lock(tmp_path):
        with pytest.raises(ValueError,match='Another evaluation'):
            with output_lock(tmp_path):pass


def test_legacy_database_migrates_without_losing_records(tmp_path):
    path=tmp_path/'db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE applications(id TEXT PRIMARY KEY,owner TEXT,status TEXT)')
        db.execute("INSERT INTO applications VALUES ('LEGACY','demo-user','approved')")
    assert Store(path).application('LEGACY','demo-user')['status']=='approved'
    assert Store(path).application('LEGACY','demo-user')['status']=='approved'
