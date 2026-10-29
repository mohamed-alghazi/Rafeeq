import asyncio
import json
from datetime import date, timedelta
import pytest
from fastapi.testclient import TestClient
from rafeeq.domain import calculate_fee
from rafeeq.store import Store
from rafeeq.agent import run_agent, trim_history


def working_day():
    d = date.today() + timedelta(days=10)
    while d.weekday() in {4, 5}: d += timedelta(days=1)
    return d.isoformat()


@pytest.mark.parametrize('args,expected', [
    ({'permit_type':'BLD','area':180.4},500), ({'permit_type':'BLD','area':640},1280),
    ({'permit_type':'REN'},300), ({'permit_type':'REN','structural':True,'area':35},335),
    ({'permit_type':'REN','social_security':True,'primary_residence':True},0),
    ({'permit_type':'SGN','area':3,'illuminated':True},750),
    ({'permit_type':'SGN','area':1.5},400), ({'permit_type':'FTR'},1500),
    ({'permit_type':'EVT','days':3},3000)])
def test_fee(args, expected): assert calculate_fee(**args)['fee_sar'] == expected


@pytest.mark.parametrize('args', [{'permit_type':'OTHER'},{'permit_type':'BLD','area':-1},{'permit_type':'SGN','area':float('nan')},{'permit_type':'EVT','days':1.2}])
def test_fee_rejects(args):
    with pytest.raises(ValueError): calculate_fee(**args)


def test_approval_ownership_and_replay(tmp_path):
    store = Store(tmp_path/'db.sqlite')
    with pytest.raises(ValueError): store.application('MDR-2001','demo-user')
    p = store.propose('MDR-1001',working_day(),'demo-user')
    with store.connect() as db: assert db.execute('SELECT count(*) FROM inspections').fetchone()[0] == 0
    with pytest.raises(ValueError): store.decide(p['proposal_id'],True,'other-user')
    assert store.decide(p['proposal_id'],True,'demo-user')['booked']
    with pytest.raises(ValueError): store.decide(p['proposal_id'],True,'demo-user')


def test_rejection(tmp_path):
    s=Store(tmp_path/'db'); p=s.propose('MDR-1001',working_day(),'demo-user')
    assert not s.decide(p['proposal_id'],False,'demo-user')['booked']
    with s.connect() as db: assert db.execute('SELECT count(*) FROM inspections').fetchone()[0] == 0


class ScriptedProvider:
    """Protocol fixture, NOT a language model or substitute for model evaluation."""
    def __init__(self, calls): self.calls=calls; self.n=0
    async def complete(self,messages,tools):
        if self.n < len(self.calls):
            name,args=self.calls[self.n]; self.n+=1
            return {'message':{'role':'assistant','content':None,'tool_calls':[{'id':str(self.n),'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]},'tokens':0}
        return {'message':{'role':'assistant','content':'Protocol fixture complete'},'tokens':0}


def test_real_mcp_roundtrip_and_write_gate(tmp_path):
    s=Store(tmp_path/'db')
    p=ScriptedProvider([('search_policy',{'query':'fee'}),('calculate_fee',{'permit_type':'SGN','area':3,'illuminated':True}),('propose_inspection',{'application_id':'MDR-1001','day':working_day()})])
    r=asyncio.run(run_agent('fixture',s,p))
    assert r['stopped']=='complete'
    assert len(r['trace'])==3
    assert '750' in r['trace'][1]['result']
    assert r['pending'][0]['day']==working_day()
    with s.connect() as db: assert db.execute('SELECT count(*) FROM inspections').fetchone()[0]==0


def test_unavailable_tools_and_cross_owner(tmp_path):
    p=ScriptedProvider([('send_email',{'to':'attacker@example.com'}),('get_application',{'application_id':'MDR-2001'})])
    r=asyncio.run(run_agent('fixture',Store(tmp_path/'db'),p))
    assert all('error' in row['result'] for row in r['trace'])


def test_step_budget(tmp_path):
    p=ScriptedProvider([('get_application',{'application_id':'MDR-1001'})]*20)
    r=asyncio.run(run_agent('fixture',Store(tmp_path/'db'),p))
    assert r['stopped']=='step_budget'
    assert p.n==8


def test_history_budget():
    h=[{'role':r,'content':'x'*2000} for _ in range(20) for r in ['user','assistant']]
    trimmed=trim_history(h)
    assert trimmed[0]['role']=='user'
    assert len(json.dumps(trimmed))<=8000


def test_api_auth_and_approval(tmp_path,monkeypatch):
    from rafeeq import api
    monkeypatch.setenv('RAFEEQ_ACCESS_TOKEN','test-access')
    monkeypatch.setattr(api,'store',Store(tmp_path/'db'))
    c=TestClient(api.app)
    assert c.get('/health').status_code==200
    assert c.get('/').status_code==200
    assert c.get('/api/proposals').status_code==401
    h={'Authorization':'Bearer test-access'}
    p=api.store.propose('MDR-1001',working_day(),'demo-user')
    endpoint=f"/api/proposals/{p['proposal_id']}/decision"
    assert c.post(endpoint,headers=h,json={'approve':'false'}).status_code==422
    assert c.post(endpoint,headers=h,json={'approve':True,'day':'2030-01-01'}).status_code==422
    assert c.post(endpoint,headers=h,json={'approve':True}).json()['booked']
    assert c.post(endpoint,headers=h,json={'approve':True}).status_code==409
