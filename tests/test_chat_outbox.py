import json
import random
import sqlite3

import pytest
from nanoagent import chatstore, chat_outbox


@pytest.fixture
def conn():
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    chatstore.migrate(c)
    chat_outbox.migrate(c)
    chatstore.create_agent(c, 'a', channel='line', external_id='user', kind='user')
    chatstore.update_agent(c, 'a', status='active')
    return c


def test_random_states_never_send_without_owner_approval(conn):
    rng = random.Random(821)
    calls = []
    for _ in range(100):
        did = chat_outbox.prepare(conn, 'a', text='hello', reply_token='token', now=100)
        status = rng.choice(['draft', 'rejected', 'failed', 'expired', 'sent'])
        conn.execute('UPDATE chat_outbox SET status=? WHERE id=?', (status, did))
        assert not chat_outbox.send(conn, 'a', did, calls.append, now=101)['ok']
    assert calls == []


def test_groups_always_draft_and_audited(conn):
    chatstore.create_agent(conn, 'g', channel='line', external_id='group', kind='group')
    chatstore.update_agent(conn, 'g', status='active', permissions_json=json.dumps({'reply_mode': 'auto'}))
    did = chat_outbox.prepare(conn, 'g', text='hello', reply_token='token', now=1)
    assert chat_outbox.get(conn, 'g', did)['status'] == 'draft'
    assert not chat_outbox.send(conn, 'g', did, lambda x: None, now=2)['ok']
    assert chat_outbox.approve(conn, 'g', did, now=2)['ok']
    calls = []
    assert chat_outbox.send(conn, 'g', did, calls.append, now=3)['ok']
    assert len(calls) == 1
    assert [r['action'] for r in chatstore.list_audit(conn, 'g')][-4:] == ['create', 'approve', 'sending', 'sent']


def test_limits_and_kill_switch(conn):
    calls = []
    limits = chat_outbox.Limits(per_chat_seconds=10, daily_cap=2, monthly_cap=2)
    def ready(now):
        d = chat_outbox.prepare(conn, 'a', text='x', reply_token='t', now=now)
        chat_outbox.approve(conn, 'a', d, now=now)
        return d
    assert chat_outbox.send(conn, 'a', ready(100), calls.append, now=100, limits=limits)['ok']
    d = ready(101)
    assert 'interval' in chat_outbox.send(conn, 'a', d, calls.append, now=101, limits=limits)['error']
    chat_outbox.set_kill_switch(conn, True)
    assert 'paused' in chat_outbox.send(conn, 'a', d, calls.append, now=111, limits=limits)['error']
    chat_outbox.set_kill_switch(conn, False)
    assert chat_outbox.send(conn, 'a', d, calls.append, now=111, limits=limits)['ok']
    assert 'daily' in chat_outbox.send(conn, 'a', ready(122), calls.append, now=122, limits=limits)['error']
    chatstore.create_agent(conn, 'b', channel='line', external_id='b', kind='user')
    chatstore.update_agent(conn, 'b', status='active')
    d = chat_outbox.prepare(conn, 'b', text='x', reply_token='t', now=122)
    chat_outbox.approve(conn, 'b', d, now=122)
    assert 'monthly' in chat_outbox.send(conn, 'b', d, calls.append, now=122, limits=limits)['error']


def test_expired_reply_requires_explicit_push_approval(conn):
    chatstore.update_agent(conn, 'a', permissions_json=json.dumps({'push_allowed': True}))
    d = chat_outbox.prepare(conn, 'a', text='x', reply_token='t', now=100)
    chat_outbox.approve(conn, 'a', d, now=101)
    calls = []
    assert 'push' in chat_outbox.send(conn, 'a', d, calls.append, now=160)['error']
    assert not calls
    assert chat_outbox.approve(conn, 'a', d, as_push=True, now=161)['ok']
    assert chat_outbox.send(conn, 'a', d, calls.append, now=161)['ok']
    assert calls[0]['kind'] == 'push'


def test_sender_failure_is_audited_and_not_retried(conn):
    d = chat_outbox.prepare(conn, 'a', text='x', reply_token='t', now=1)
    chat_outbox.approve(conn, 'a', d, now=2)
    def fail(_):
        raise RuntimeError('failed')
    assert not chat_outbox.send(conn, 'a', d, fail, now=3)['ok']
    assert chat_outbox.get(conn, 'a', d)['status'] == 'failed'
    assert chatstore.list_audit(conn, 'a')[-1]['action'] == 'failed'
