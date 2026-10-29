import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from rafeeq.retrieval import PolicyIndex, policy_search


@pytest.mark.parametrize('mode',['A','B'])
def test_fee_search_returns_policy_evidence(mode):
    hits=policy_search('illuminated sign fees',mode)
    assert hits and hits[0]['id']=='POL-02' and '750' in hits[0]['text']
    assert hits[0]['snippet'] and 0<hits[0]['score']<=1


@pytest.mark.parametrize('mode',['A','B'])
def test_unknown_vocabulary_does_not_invent_a_policy(mode):
    index=PolicyIndex([{'id':'P1','text':'cat dog kitten puppy'},{'id':'P2','text':'rain snow clouds winter'}])
    assert index.search('zzzzzzzzzzzz',mode)==[]


def test_character_search_matches_a_prefix_missing_from_word_vocabulary():
    index=PolicyIndex([{'id':'P1','text':'refund reimbursement withdrawal payment'},
                       {'id':'P2','text':'inspection appointment booking schedule'}])
    assert index.search('refun',mode='A')==[]
    assert index.search('refun',mode='B')[0]['id']=='P1'


def test_local_search_is_public_but_does_not_grant_private_access(monkeypatch):
    from rafeeq import api
    from rafeeq.agent import OpenRouterProvider
    def inference_forbidden(*args,**kwargs):raise AssertionError('Local search must not create an inference client')
    monkeypatch.setattr(OpenRouterProvider,'__init__',inference_forbidden)
    c=TestClient(api.app)
    r=c.post('/api/policies/search',json={'query':'illuminated sign fees','mode':'B'})
    assert r.status_code==200 and r.json()['local'] is True
    assert r.json()['documents'][0]['id']=='POL-02'
    assert c.get('/api/proposals').status_code in (401,503)
    assert c.post('/api/policies/search',json={'query':'fees','mode':'C'}).status_code==422
    assert c.post('/api/policies/search',json={'query':'x'*1001}).status_code==422


def test_retrieval_task_set_is_frozen_and_uses_existing_policy_ids():
    tasks=[json.loads(x) for x in Path('evaluations/retrieval/tasks.jsonl').read_text().splitlines() if x.strip()]
    ids={p.stem for p in Path('data/policies').glob('*.md')}
    assert len(tasks)==26 and len({t['id'] for t in tasks})==26
    assert all(t['expected_policy'] in ids|{None} for t in tasks)
    assert any(t['expected_policy'] is None for t in tasks)


def test_invalid_queries_and_modes_fail():
    with pytest.raises(ValueError):policy_search('   ')
    with pytest.raises(ValueError):policy_search('fee',mode='invalid')
