import json
import pytest
from fastapi.testclient import TestClient
from nanoagent import chatstore, chat_outbox, db
from nanoagent.gateway.app import create_app

@pytest.fixture
def client(cfg_fake):
    return TestClient(create_app())

@pytest.fixture
def owner(client):
    assert client.post('/api/login', json={'token': 'owner-token-for-tests-only-0123456789'}).status_code == 200
    return client

def create(owner):
    r = owner.post('/api/chats', json={'channel': 'line', 'external_id': 'u1', 'kind': 'user', 'display_name': 'Alice'})
    assert r.status_code == 200
    return r.json()

def test_auth(client):
    assert client.get('/api/chats').status_code == 401
    assert client.put('/api/owner-profile', json={}).status_code == 401

def test_list_detail_settings(owner):
    c = create(owner)
    assert owner.get('/api/chats?q=lic').json()['chats'][0]['id'] == c['id']
    assert owner.get(f"/api/chats/{c['id']}").json()['agent']['id'] == c['agent_id']
    assert owner.patch(f"/api/agents/{c['agent_id']}", json={'permissions': {'unknown': True}}).status_code == 422
    assert owner.patch(f"/api/agents/{c['agent_id']}", json={'status': 'active', 'permissions': {'reply_mode': 'off'}}).status_code == 200
    assert owner.put('/api/owner-profile', json={'name': 'Owner'}).status_code == 200
    assert owner.get('/api/owner-profile').json()['data']['name'] == 'Owner'
    assert owner.get(f"/api/audit?target={c['agent_id']}").json()['rows']

def test_archive_and_delete(owner):
    c = create(owner); aid = c['agent_id']; cid = c['id']
    with db.tx() as conn:
        chat_outbox.migrate(conn)
        contact = chatstore.create_contact(conn, aid, display_name='Person')
        chatstore.create_message(conn, aid, direction='in', source='webhook', content_type='text', text='secret message', contact_id=contact)
        chat_outbox.prepare(conn, aid, text='draft secret', reply_token='token')
        conn.execute('CREATE TABLE IF NOT EXISTS chat_consents(id INTEGER PRIMARY KEY, contact_id INTEGER REFERENCES chat_contacts(id), scope TEXT, basis TEXT, text_version TEXT, ts REAL, withdrawn_at REAL)')
        conn.execute("INSERT INTO chat_consents(contact_id,scope,basis,ts) VALUES(?,'store','notice',1)", (contact,))
    assert owner.post(f'/api/agents/{aid}/archive').status_code == 200
    with db.tx() as conn:
        chatstore.create_message(conn, aid, direction='in', source='webhook', content_type='text', text='new secret')
    assert owner.get('/api/chats').json()['chats'] == []
    assert owner.get(f'/api/chats/{cid}').json()['agent']['status'] == 'archived'
    assert owner.delete(f'/api/chats/{cid}', params={'confirm': 'wrong'}).status_code == 400
    assert owner.get(f'/api/chats/{cid}').status_code == 200
    assert owner.delete(f'/api/chats/{cid}', params={'confirm': 'Alice'}).status_code == 200
    with db.tx() as conn:
        for table in ('chat_chats', 'chat_agents', 'chat_contacts', 'chat_messages', 'chat_consents', 'chat_outbox'):
            assert conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 0
        rows = conn.execute('SELECT * FROM chat_audit_log').fetchall()
        assert len(rows) == 1 and 'secret' not in json.dumps(dict(rows[0]))
