"""Approval-first chat delivery. The caller supplies the transport callable.

Callers must expose approve and configuration changes only to the authenticated owner.
Times are Unix seconds; limits are configurable because the design specifies no values.
"""
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from . import chatstore


@dataclass(frozen=True)
class Limits:
    per_chat_seconds: int = 60
    daily_cap: int = 20
    monthly_cap: int = 200
    reply_token_seconds: int = 60


def migrate(conn):
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS chat_outbox (
      id INTEGER PRIMARY KEY, agent_id TEXT NOT NULL REFERENCES chat_agents(id),
      chat_id INTEGER NOT NULL REFERENCES chat_chats(id), kind TEXT NOT NULL,
      text TEXT NOT NULL, status TEXT NOT NULL, created_at REAL NOT NULL,
      approved_by TEXT, approved_at REAL, sent_at REAL, risk_flags_json TEXT NOT NULL,
      reply_token TEXT, token_created_at REAL, push_approved INTEGER NOT NULL DEFAULT 0,
      line_request_id TEXT
    );
    CREATE INDEX IF NOT EXISTS chat_outbox_rate ON chat_outbox(status, sent_at, chat_id);
    CREATE TABLE IF NOT EXISTS chat_outbox_kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    ''')


def rollback_migration(conn):
    conn.executescript('DROP TABLE IF EXISTS chat_outbox; DROP TABLE IF EXISTS chat_outbox_kv;')


def get(conn, agent_id, outbox_id):
    return conn.execute('SELECT * FROM chat_outbox WHERE id=? AND agent_id=?', (outbox_id, agent_id)).fetchone()


def prepare(conn, agent_id, *, text, kind='reply', reply_token=None, token_created_at=None, risk_flags=(), now=None):
    now = time.time() if now is None else now
    if kind not in ('reply', 'push') or not isinstance(text, str) or not text.strip():
        raise ValueError('valid kind and text required')
    if kind == 'reply' and not reply_token:
        raise ValueError('reply token required')
    with chatstore._write(conn):
        chat_id = chatstore._chat_id(conn, agent_id)
        did = conn.execute('INSERT INTO chat_outbox(agent_id,chat_id,kind,text,status,created_at,risk_flags_json,reply_token,token_created_at) VALUES(?,?,?,?,?,?,?,?,?)',
                           (agent_id, chat_id, kind, text, 'draft', now, json.dumps(list(risk_flags)), reply_token, now if token_created_at is None else token_created_at)).lastrowid
        chatstore._audit(conn, agent_id, 'create', 'outbox', did, 'agent')
    return did


def approve(conn, agent_id, outbox_id, *, as_push=False, now=None):
    now = time.time() if now is None else now
    with chatstore._write(conn):
        row = get(conn, agent_id, outbox_id)
        if row is None or row['status'] not in ('draft', 'approved'):
            return {'ok': False, 'error': 'not an approvable draft'}
        conn.execute("UPDATE chat_outbox SET status='approved', approved_by='owner', approved_at=?, push_approved=? WHERE id=? AND agent_id=?", (now, int(as_push or row['kind'] == 'push'), outbox_id, agent_id))
        chatstore._audit(conn, agent_id, 'approve', 'outbox', outbox_id, 'owner')
    return {'ok': True}


def reject(conn, agent_id, outbox_id):
    with chatstore._write(conn):
        n = conn.execute("UPDATE chat_outbox SET status='rejected' WHERE id=? AND agent_id=? AND status IN ('draft','approved')", (outbox_id, agent_id)).rowcount
        if n:
            chatstore._audit(conn, agent_id, 'reject', 'outbox', outbox_id, 'owner')
    return {'ok': bool(n)}


def set_kill_switch(conn, paused):
    # Global setting has no agent scope; audit against each existing agent.
    with chatstore._write(conn):
        conn.execute("INSERT INTO chat_outbox_kv VALUES('pause_all',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", ('1' if paused else '0',))
        for (agent_id,) in conn.execute('SELECT id FROM chat_agents'):
            chatstore._audit(conn, agent_id, 'pause_sending' if paused else 'resume_sending', 'outbox_setting', 'pause_all', 'owner')


def send(conn, agent_id, outbox_id, sender, *, now=None, limits=Limits()):
    now = time.time() if now is None else now
    with chatstore._write(conn):
        row = get(conn, agent_id, outbox_id)
        if row is None or row['status'] != 'approved' or row['approved_by'] != 'owner':
            return {'ok': False, 'error': 'owner approval required'}
        paused = conn.execute("SELECT value FROM chat_outbox_kv WHERE key='pause_all'").fetchone()
        if paused and paused[0] == '1':
            return {'ok': False, 'error': 'sending paused globally'}
        agent = conn.execute('SELECT a.status,a.permissions_json,c.external_id,c.channel,c.kind FROM chat_agents a JOIN chat_chats c ON c.id=a.chat_id WHERE a.id=?', (agent_id,)).fetchone()
        if not agent or agent['status'] != 'active':
            return {'ok': False, 'error': 'agent is paused or inactive'}
        kind = row['kind']
        if kind == 'reply' and now - row['token_created_at'] >= limits.reply_token_seconds:
            if not row['push_approved']:
                return {'ok': False, 'error': 'reply token expired; explicit push approval required'}
            kind = 'push'
        if kind == 'push' and not json.loads(agent['permissions_json']).get('push_allowed', False):
            return {'ok': False, 'error': 'push not allowed for agent'}
        start_day = datetime.fromtimestamp(now, timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        start_month = datetime.fromtimestamp(now, timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp()
        last = conn.execute("SELECT MAX(sent_at) FROM chat_outbox WHERE chat_id=? AND status IN ('sending','sent','failed')", (row['chat_id'],)).fetchone()[0]
        if last is not None and now - last < limits.per_chat_seconds:
            return {'ok': False, 'error': 'per-chat interval limit reached'}
        count = conn.execute("SELECT COUNT(*) FROM chat_outbox WHERE agent_id=? AND status IN ('sending','sent','failed') AND sent_at>=?", (agent_id, start_day)).fetchone()[0]
        if count >= limits.daily_cap:
            return {'ok': False, 'error': 'agent daily limit reached'}
        count = conn.execute("SELECT COUNT(*) FROM chat_outbox WHERE status IN ('sending','sent','failed') AND sent_at>=?", (start_month,)).fetchone()[0]
        if count >= limits.monthly_cap:
            return {'ok': False, 'error': 'global monthly limit reached'}
        n = conn.execute("UPDATE chat_outbox SET status='sending',sent_at=? WHERE id=? AND agent_id=? AND status='approved' AND approved_by='owner'", (now, outbox_id, agent_id)).rowcount
        if not n:
            return {'ok': False, 'error': 'already claimed'}
        chatstore._audit(conn, agent_id, 'sending', 'outbox', outbox_id, 'system')
    payload = {'kind': kind, 'target': agent['external_id'], 'channel': agent['channel'], 'text': row['text'], 'reply_token': row['reply_token'] if kind == 'reply' else None}
    try:
        request_id = sender(payload)
    except Exception:
        with chatstore._write(conn):
            conn.execute("UPDATE chat_outbox SET status='failed' WHERE id=? AND agent_id=? AND status='sending'", (outbox_id, agent_id))
            chatstore._audit(conn, agent_id, 'failed', 'outbox', outbox_id, 'system')
        return {'ok': False, 'error': 'sending failed'}
    with chatstore._write(conn):
        conn.execute("UPDATE chat_outbox SET status='sent',line_request_id=? WHERE id=? AND agent_id=? AND status='sending'", (request_id if isinstance(request_id, str) else None, outbox_id, agent_id))
        chatstore._audit(conn, agent_id, 'sent', 'outbox', outbox_id, 'system')
    return {'ok': True, 'status': 'sent'}
