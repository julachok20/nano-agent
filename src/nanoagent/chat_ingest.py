"""Store verified LINE webhook events without invoking an agent or network."""
import json
import time
import uuid

from . import chatstore
from .gateway.line import verify_signature


class InvalidSignature(ValueError):
    """The webhook signature is missing or invalid."""


def ingest(conn, body, signature, channel_secret):
    """Verify and store a LINE payload. Invalid signatures raise InvalidSignature.

    The caller supplies a migrated P1 SQLite connection. This function does not
    commit an existing transaction or perform any outbound actions.
    """
    if not verify_signature(body, signature, channel_secret):
        raise InvalidSignature('invalid LINE signature')
    payload = json.loads(body)
    events = payload['events']
    if not isinstance(events, list):
        raise ValueError('events must be a list')

    conn.execute('SAVEPOINT line_ingest')
    try:
        conn.execute('''CREATE TABLE IF NOT EXISTS chat_consents (
            id INTEGER PRIMARY KEY, contact_id INTEGER NOT NULL REFERENCES chat_contacts(id),
            scope TEXT NOT NULL, basis TEXT NOT NULL, text_version TEXT,
            ts REAL NOT NULL, withdrawn_at REAL)''')
        for event in events:
            source = event.get('source') or {}
            kind = source.get('type')
            key = {'user': 'userId', 'group': 'groupId', 'room': 'roomId'}.get(kind)
            external_id = source.get(key) if key else None
            if not external_id:
                continue
            msg = event.get('message') or {}
            if event.get('type') == 'message' and not msg.get('id'):
                raise ValueError('LINE message id is required')
            if event.get('type') == 'message' and conn.execute(
                    'SELECT 1 FROM chat_messages WHERE line_message_id=?', (msg['id'],)).fetchone():
                continue
            row = conn.execute('''SELECT a.id FROM chat_agents a JOIN chat_chats c ON c.id=a.chat_id
                                  WHERE c.channel=? AND c.external_id=?''', ('line', external_id)).fetchone()
            if row:
                agent_id = row[0]
            else:
                agent_id = uuid.uuid4().hex
                chatstore.create_agent(conn, agent_id, channel='line', external_id=external_id, kind=kind)
                if kind in ('group', 'room'):
                    permissions = json.loads(conn.execute('SELECT permissions_json FROM chat_agents WHERE id=?', (agent_id,)).fetchone()[0])
                    permissions['reply_mode'] = 'off'
                    chatstore.update_agent(conn, agent_id, actor='system', permissions_json=json.dumps(permissions))
            user_id = source.get('userId')
            contact = conn.execute('''SELECT c.id FROM chat_contacts c JOIN chat_agents a ON a.chat_id=c.chat_id
                                      WHERE a.id=? AND c.external_user_id IS ?''', (agent_id, user_id)).fetchone()
            contact_id = contact[0] if contact else chatstore.create_contact(conn, agent_id, external_user_id=user_id)
            timestamp = event.get('timestamp')
            ts = timestamp / 1000 if isinstance(timestamp, (int, float)) else time.time()
            if event.get('type') == 'message':
                content_type = msg.get('type', 'unknown')
                chatstore.create_message(conn, agent_id, contact_id=contact_id, direction='in', source='webhook',
                                         content_type=content_type, text=msg.get('text') if content_type == 'text' else None,
                                         line_message_id=msg['id'], ts=ts)
            elif event.get('type') == 'follow':
                existing = conn.execute('''SELECT 1 FROM chat_consents WHERE contact_id=? AND scope='store'
                                           AND basis='notice' AND withdrawn_at IS NULL''', (contact_id,)).fetchone()
                if not existing:
                    consent_id = conn.execute('''INSERT INTO chat_consents(contact_id,scope,basis,ts)
                                                 VALUES(?,'store','notice',?)''', (contact_id, ts)).lastrowid
                    chatstore._audit(conn, agent_id, 'create', 'consent', consent_id, 'system')
        conn.execute('RELEASE SAVEPOINT line_ingest')
    except Exception:
        conn.execute('ROLLBACK TO SAVEPOINT line_ingest')
        conn.execute('RELEASE SAVEPOINT line_ingest')
        raise
