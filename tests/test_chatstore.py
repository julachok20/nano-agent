import sqlite3

import pytest

from nanoagent import chatstore


@pytest.fixture
def conn():
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    chatstore.migrate(db)
    return db


def test_migration_idempotent_and_down(conn):
    chatstore.migrate(conn)
    chatstore.rollback_migration(conn)
    chatstore.rollback_migration(conn)
    chatstore.migrate(conn)
    assert conn.execute("SELECT name FROM sqlite_master WHERE name='chat_messages'").fetchone()


def test_agent_isolation(conn):
    chatstore.create_agent(conn, 'a', channel='line', external_id='one', kind='user')
    chatstore.create_agent(conn, 'b', channel='line', external_id='two', kind='user')
    contact = chatstore.create_contact(conn, 'a', external_user_id='person')
    message = chatstore.create_message(conn, 'a', contact_id=contact, direction='in', source='webhook', content_type='text', text='private')
    assert chatstore.get_message(conn, 'b', message) is None
    assert chatstore.list_messages(conn, 'b') == []
    assert chatstore.get_contact(conn, 'b', contact) is None
    with pytest.raises(ValueError):
        chatstore.create_message(conn, 'b', contact_id=contact, direction='in', source='webhook', content_type='text')


def test_every_write_is_audited(conn):
    chatstore.create_agent(conn, 'a', channel='line', external_id='one', kind='user')
    contact = chatstore.create_contact(conn, 'a', external_user_id='person')
    message = chatstore.create_message(conn, 'a', contact_id=contact, direction='in', source='webhook', content_type='text')
    chatstore.update_agent(conn, 'a', status='active')
    chatstore.delete_message(conn, 'a', message)
    rows = chatstore.list_audit(conn, 'a')
    assert [row['action'] for row in rows] == ['create', 'create', 'create', 'update', 'delete']
    assert chatstore.list_audit(conn, 'missing') == []
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute('DELETE FROM chat_audit_log')
