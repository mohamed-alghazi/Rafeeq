from fastapi.testclient import TestClient
from rafeeq.store import Store, DEMO_IDENTITIES


def test_guest_can_start_without_password_but_cannot_reuse_a_private_session(tmp_path,monkeypatch):
    from rafeeq import api
    monkeypatch.setenv('RAFEEQ_ACCESS_TOKEN','owner-only-fixture')
    monkeypatch.setattr(api,'store',Store(tmp_path/'db'))
    c=TestClient(api.app)
    guest=c.post('/api/visitors')
    assert guest.status_code==200
    token=guest.json()['session_token'];h={'X-Rafeeq-Session':token}
    assert c.get('/api/history',headers=h).json()==[]
    assert c.get('/api/proposals',headers=h).status_code==403
    private=c.post('/api/sessions',headers={'Authorization':'Bearer owner-only-fixture'}).json()['session_token']
    assert c.get('/api/history',headers={'X-Rafeeq-Session':private}).status_code==401
    assert c.get('/health').json()['guest_access'] is True


def test_guest_history_and_approvals_are_isolated(tmp_path,monkeypatch):
    from rafeeq import api
    monkeypatch.setattr(api,'store',Store(tmp_path/'db'))
    c=TestClient(api.app)
    a=c.post('/api/visitors').json()['session_token'];b=c.post('/api/visitors').json()['session_token']
    ha={'X-Rafeeq-Session':a};hb={'X-Rafeeq-Session':b}
    i=DEMO_IDENTITIES['demo-user']
    for h in (ha,hb):
        assert c.post('/api/session/verify',headers=h,json={k:i[k] for k in ('application_id','last4','mobile')}).status_code==200
    api.store.remember(a,'My question','My answer')
    assert c.get('/api/history',headers=hb).json()==[]
    p=api.store.refund('MDR-1002','demo-user',a)
    assert c.get('/api/proposals',headers=hb).json()==[]
    endpoint=f"/api/proposals/{p['proposal_id']}/decision"
    assert c.post(endpoint,headers=hb,json={'approve':True}).status_code==409
    assert c.post(endpoint,headers=ha,json={'approve':True}).json()['amount_sar']==650


def test_guest_flow_does_not_require_private_access_configuration(monkeypatch):
    from rafeeq import api
    monkeypatch.delenv('RAFEEQ_ACCESS_TOKEN',raising=False)
    c=TestClient(api.app)
    assert c.post('/api/visitors').status_code==200
    assert c.post('/api/sessions').status_code==503
    h=c.get('/health').json()
    assert h['guest_access'] is True and h['access_configured'] is False


def test_visitor_page_has_no_site_password_field():
    from rafeeq import api
    text=TestClient(api.app).get('/').text
    assert 'id="start-demo"' in text
    assert 'id="token"' not in text
    assert 'id="connect-form"' not in text
    assert 'RAFEEQ-DEMO' not in text
    assert 'id="verify-form"' in text
