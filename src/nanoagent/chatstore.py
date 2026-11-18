"""Agent-scoped storage for chat data. All mutations and audits are atomic."""
import json
import time
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_owner_profile(id INTEGER PRIMARY KEY CHECK(id=1), data_json TEXT NOT NULL, updated_at REAL NOT NULL, version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS chat_chats(id INTEGER PRIMARY KEY, channel TEXT NOT NULL, external_id TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('user','group','room','import')), display_name TEXT, created_at REAL NOT NULL, last_message_at REAL, status TEXT NOT NULL DEFAULT 'active', UNIQUE(channel, external_id));
CREATE TABLE IF NOT EXISTS chat_personas(id INTEGER PRIMARY KEY, name TEXT NOT NULL, system_text TEXT NOT NULL, tone_defaults_json TEXT NOT NULL DEFAULT '{}', is_template INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS chat_agents(id TEXT PRIMARY KEY, chat_id INTEGER NOT NULL UNIQUE REFERENCES chat_chats(id), status TEXT NOT NULL DEFAULT 'pending', persona_id INTEGER REFERENCES chat_personas(id), permissions_json TEXT NOT NULL DEFAULT '{"read_owner_profile":true,"reply_mode":"draft","learn":false,"use_tools":[],"share_across_chats":false,"push_allowed":false}', model TEXT, context_budget_tokens INTEGER, created_at REAL NOT NULL, archived_at REAL, template_id INTEGER REFERENCES chat_personas(id));
CREATE TABLE IF NOT EXISTS chat_contacts(id INTEGER PRIMARY KEY, chat_id INTEGER NOT NULL REFERENCES chat_chats(id), external_user_id TEXT, display_name TEXT, is_owner INTEGER NOT NULL DEFAULT 0, consent_state TEXT NOT NULL DEFAULT 'none', first_seen REAL NOT NULL);
CREATE TABLE IF NOT EXISTS chat_messages(id INTEGER PRIMARY KEY, chat_id INTEGER NOT NULL REFERENCES chat_chats(id), contact_id INTEGER REFERENCES chat_contacts(id), direction TEXT NOT NULL CHECK(direction IN ('in','out')), source TEXT NOT NULL CHECK(source IN ('webhook','import','dashboard')), ts REAL NOT NULL, content_type TEXT NOT NULL, text TEXT, raw_ref TEXT, line_message_id TEXT UNIQUE, import_batch_id INTEGER, deleted_at REAL);
CREATE TABLE IF NOT EXISTS chat_audit_log(id INTEGER PRIMARY KEY, agent_id TEXT NOT NULL, ts REAL NOT NULL, actor TEXT NOT NULL CHECK(actor IN ('owner','system','agent')), action TEXT NOT NULL, target_type TEXT NOT NULL, target_id TEXT NOT NULL, detail_json TEXT NOT NULL DEFAULT '{}');
CREATE TRIGGER IF NOT EXISTS chat_audit_no_update BEFORE UPDATE ON chat_audit_log BEGIN SELECT RAISE(ABORT, 'audit is append-only'); END;
CREATE TRIGGER IF NOT EXISTS chat_audit_no_delete BEFORE DELETE ON chat_audit_log BEGIN SELECT RAISE(ABORT, 'audit is append-only'); END;
"""


def migrate(conn):
    """Apply the additive schema; safe to call repeatedly."""
    conn.executescript(SCHEMA)


def rollback_migration(conn):
    """Remove P1 tables. Intended only for explicit migration rollback."""
    conn.executescript("""
    DROP TRIGGER IF EXISTS chat_audit_no_update;
    DROP TRIGGER IF EXISTS chat_audit_no_delete;
    DROP TABLE IF EXISTS chat_audit_log;
    DROP TABLE IF EXISTS chat_messages;
    DROP TABLE IF EXISTS chat_contacts;
    DROP TABLE IF EXISTS chat_agents;
    DROP TABLE IF EXISTS chat_personas;
    DROP TABLE IF EXISTS chat_chats;
    DROP TABLE IF EXISTS chat_owner_profile;
    """)


@contextmanager
def _write(conn):
    conn.execute('SAVEPOINT chatstore_write')
    try:
        yield
        conn.execute('RELEASE SAVEPOINT chatstore_write')
    except Exception:
        conn.execute('ROLLBACK TO SAVEPOINT chatstore_write')
        conn.execute('RELEASE SAVEPOINT chatstore_write')
        raise


def _audit(conn, agent_id, action, target_type, target_id, actor):
    conn.execute('INSERT INTO chat_audit_log(agent_id,ts,actor,action,target_type,target_id,detail_json) VALUES(?,?,?,?,?,?,?)',
                 (agent_id, time.time(), actor, action, target_type, str(target_id), '{}'))


def _chat_id(conn, agent_id):
    if not agent_id:
        raise ValueError('agent_id is required')
    row = conn.execute('SELECT chat_id FROM chat_agents WHERE id=?', (agent_id,)).fetchone()
    if row is None:
        raise ValueError('unknown agent')
    return row[0]


def create_agent(conn, agent_id, *, channel, external_id, kind, display_name=None, actor='system'):
    if not agent_id:
        raise ValueError('agent_id is required')
    with _write(conn):
        now = time.time()
        chat_id = conn.execute('INSERT INTO chat_chats(channel,external_id,kind,display_name,created_at) VALUES(?,?,?,?,?)', (channel, external_id, kind, display_name, now)).lastrowid
        conn.execute('INSERT INTO chat_agents(id,chat_id,created_at) VALUES(?,?,?)', (agent_id, chat_id, now))
        _audit(conn, agent_id, 'create', 'agent', agent_id, actor)
    return agent_id


def get_agent(conn, agent_id):
    return conn.execute('SELECT * FROM chat_agents WHERE id=? AND id IS NOT NULL', (agent_id,)).fetchone()


def update_agent(conn, agent_id, *, actor='owner', **fields):
    allowed = {'status', 'persona_id', 'permissions_json', 'model', 'context_budget_tokens', 'archived_at', 'template_id'}
    if not fields or not fields.keys() <= allowed:
        raise ValueError('invalid fields')
    with _write(conn):
        _chat_id(conn, agent_id)
        conn.execute('UPDATE chat_agents SET ' + ','.join(k + '=?' for k in fields) + ' WHERE id=?', (*fields.values(), agent_id))
        _audit(conn, agent_id, 'update', 'agent', agent_id, actor)


def create_contact(conn, agent_id, *, external_user_id=None, display_name=None, is_owner=False, consent_state='none', actor='system'):
    with _write(conn):
        chat_id = _chat_id(conn, agent_id)
        row_id = conn.execute('INSERT INTO chat_contacts(chat_id,external_user_id,display_name,is_owner,consent_state,first_seen) VALUES(?,?,?,?,?,?)', (chat_id, external_user_id, display_name, is_owner, consent_state, time.time())).lastrowid
        _audit(conn, agent_id, 'create', 'contact', row_id, actor)
    return row_id


def get_contact(conn, agent_id, contact_id):
    return conn.execute('SELECT c.* FROM chat_contacts c JOIN chat_agents a ON a.chat_id=c.chat_id WHERE a.id=? AND c.id=?', (agent_id, contact_id)).fetchone()


def create_message(conn, agent_id, *, direction, source, content_type, contact_id=None, text=None, raw_ref=None, line_message_id=None, import_batch_id=None, ts=None, actor='system'):
    with _write(conn):
        chat_id = _chat_id(conn, agent_id)
        if contact_id is not None and get_contact(conn, agent_id, contact_id) is None:
            raise ValueError('contact does not belong to agent')
        row_id = conn.execute('INSERT INTO chat_messages(chat_id,contact_id,direction,source,ts,content_type,text,raw_ref,line_message_id,import_batch_id) VALUES(?,?,?,?,?,?,?,?,?,?)', (chat_id, contact_id, direction, source, time.time() if ts is None else ts, content_type, text, raw_ref, line_message_id, import_batch_id)).lastrowid
        _audit(conn, agent_id, 'create', 'message', row_id, actor)
    return row_id


def get_message(conn, agent_id, message_id):
    return conn.execute('SELECT m.* FROM chat_messages m JOIN chat_agents a ON a.chat_id=m.chat_id WHERE a.id=? AND m.id=?', (agent_id, message_id)).fetchone()


def list_messages(conn, agent_id):
    return conn.execute('SELECT m.* FROM chat_messages m JOIN chat_agents a ON a.chat_id=m.chat_id WHERE a.id=? ORDER BY m.id', (agent_id,)).fetchall()


def delete_message(conn, agent_id, message_id, *, actor='owner'):
    with _write(conn):
        cursor = conn.execute('DELETE FROM chat_messages WHERE id=? AND chat_id=(SELECT chat_id FROM chat_agents WHERE id=?)', (message_id, agent_id))
        if cursor.rowcount:
            _audit(conn, agent_id, 'delete', 'message', message_id, actor)
        return bool(cursor.rowcount)


def list_audit(conn, agent_id):
    return conn.execute('SELECT * FROM chat_audit_log WHERE agent_id=? ORDER BY id', (agent_id,)).fetchall()
