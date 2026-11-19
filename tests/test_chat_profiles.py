import json
import sqlite3

import pytest
from fastapi.testclient import TestClient
from nanoagent import chatstore, chat_runtime, db
from nanoagent.gateway.app import create_app


@pytest.fixture
def profiles():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    chatstore.migrate(conn)
    for aid in ('a', 'b'):
        chatstore.create_agent(conn, aid, channel='line', external_id=aid, kind='user')
    contact = chatstore.create_contact(conn, 'a', external_user_id='alice')
    return conn, contact


def test_edit_prompt_and_isolation(profiles):
    conn, contact = profiles
    chatstore.set_person_profile(conn, 'a', contact, {'notes': 'first secret'})
    assert 'first secret' in str(chat_runtime.build_prompt(conn, 'a'))
    chatstore.set_person_profile(conn, 'a', contact, {'notes': 'updated secret'})
    assert 'updated secret' in str(chat_runtime.build_prompt(conn, 'a'))
    assert 'updated secret' not in str(chat_runtime.build_prompt(conn, 'b'))
    assert chatstore.get_person_profile(conn, 'b', contact) is None
    assert chatstore.get_person_profile(conn, 'a', contact)['fields']['notes']['source'] == 'owner'


def test_post_filter_and_review(profiles):
    conn, contact = profiles
    chatstore.set_person_profile(conn, 'a', contact, {'never_mention': ['Secret', '\u0e04\u0e27\u0e32\u0e21\u0e25\u0e31\u0e1a']})
    prompt = str(chat_runtime.build_prompt(conn, 'a'))
    assert 'do not mention' in prompt.lower()
    draft = 'SECRET and \u0e04\u0e27\u0e32\u0e21\u0e25\u0e31\u0e1a'
    assert len(chat_runtime.check_draft(conn, 'a', draft)) == 2
    result = chat_runtime.run_turn(conn, 'a', lambda _: draft)
    assert result['draft'] == draft and result['needs_owner_review'] and len(result['violations']) == 2
    assert not chat_runtime.check_draft(conn, 'b', draft)


def test_delete_tombstone(profiles):
    conn, contact = profiles
    chatstore.set_person_profile(conn, 'a', contact, {'notes': 'sensitive content'})
    assert chatstore.delete_person_profile(conn, 'a', contact)
    assert chatstore.get_person_profile(conn, 'a', contact) is None
    rows = [dict(row) for row in chatstore.list_audit(conn, 'a')]
    assert rows[-1]['action'] == 'delete' and rows[-1]['target_type'] == 'person_profile'
    assert 'sensitive content' not in json.dumps(rows)


def test_api_auth_and_scope(cfg_fake):
    client = TestClient(create_app())
    for method in ('get', 'put', 'delete'):
        assert getattr(client, method)('/api/contacts/1/profile', params={'agent_id': 'a'}).status_code == 401
    client.post('/api/login', json={'token': 'owner-token-for-tests-only-0123456789'})
    with db.tx() as conn:
        chatstore.create_agent(conn, 'a', channel='line', external_id='a', kind='user')
        chatstore.create_agent(conn, 'b', channel='line', external_id='b', kind='user')
        contact = chatstore.create_contact(conn, 'a', external_user_id='alice')
    url = f'/api/contacts/{contact}/profile'
    assert client.put(url, params={'agent_id': 'a'}, json={'notes': 'hello'}).status_code == 200
    assert client.get(url, params={'agent_id': 'a'}).json()['fields']['notes']['value'] == 'hello'
    assert client.get(url, params={'agent_id': 'b'}).status_code == 404
    assert client.delete(url, params={'agent_id': 'a'}).status_code == 200
