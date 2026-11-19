"""Owner-only chat management API."""
import json
import sqlite3
import time
import uuid
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, StrictBool

from .. import chatstore, db

router = APIRouter()

class StrictModel(BaseModel):
    class Config:
        extra = 'forbid'

class CreateChat(StrictModel):
    channel: str = Field(min_length=1, max_length=100)
    external_id: str = Field(min_length=1, max_length=255)
    kind: Literal['user', 'group', 'room', 'import']
    display_name: str = Field(min_length=1, max_length=255)

class Permissions(StrictModel):
    read_owner_profile: Optional[StrictBool] = None
    reply_mode: Optional[Literal['off', 'draft', 'auto_low_risk', 'auto']] = None
    learn: Optional[StrictBool] = None
    use_tools: Optional[list[str]] = None
    share_across_chats: Optional[Literal[False]] = None
    push_allowed: Optional[StrictBool] = None

class AgentPatch(StrictModel):
    persona_id: Optional[int] = None
    permissions: Optional[Permissions] = None
    status: Optional[Literal['pending', 'active', 'paused', 'archived']] = None


def agent_for_chat(conn, chat_id):
    row = conn.execute('SELECT id FROM chat_agents WHERE chat_id=?', (chat_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'chat not found')
    return row['id']


def agent_or_404(conn, agent_id):
    row = chatstore.get_agent(conn, agent_id)
    if row is None:
        raise HTTPException(404, 'agent not found')
    return row


@router.get('/chats')
def list_chats(status: Optional[Literal['pending', 'active', 'paused', 'archived']] = None, q: str = ''):
    with db.tx() as conn:
        has_outbox = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='chat_outbox'").fetchone()
        count = "(SELECT count(*) FROM chat_outbox o WHERE o.agent_id=a.id AND o.status='draft')" if has_outbox else '0'
        rows = conn.execute(f'''SELECT c.id,c.display_name AS name,c.kind,a.id AS agent_id,a.status AS agent_status,
            COALESCE((SELECT MAX(m.ts) FROM chat_messages m WHERE m.chat_id=c.id),c.last_message_at) AS last_activity,
            {count} AS pending_drafts_count FROM chat_chats c JOIN chat_agents a ON a.chat_id=c.id
            WHERE (a.status=? OR (? IS NULL AND a.status!='archived')) AND (instr(lower(COALESCE(c.display_name,'')),lower(?))>0 OR ?='') ORDER BY c.id''', (status, status, q, q)).fetchall()
        return {'chats': [dict(r) for r in rows]}


@router.post('/chats')
def create_chat(body: CreateChat):
    aid = uuid.uuid4().hex
    try:
        with db.tx() as conn:
            chatstore.create_agent(conn, aid, channel=body.channel, external_id=body.external_id, kind=body.kind, display_name=body.display_name, actor='owner')
            if body.kind in ('group', 'room', 'import'):
                permissions = json.loads(chatstore.get_agent(conn, aid)['permissions_json'])
                permissions['reply_mode'] = 'off'
                chatstore.update_agent(conn, aid, permissions_json=json.dumps(permissions))
            cid = chatstore._chat_id(conn, aid)
    except sqlite3.IntegrityError:
        raise HTTPException(409, 'chat already exists')
    return {'id': cid, 'agent_id': aid}


@router.get('/chats/{chat_id}')
def chat_detail(chat_id: int):
    with db.tx() as conn:
        aid = agent_for_chat(conn, chat_id)
        chat = dict(conn.execute('SELECT c.* FROM chat_chats c JOIN chat_agents a ON a.chat_id=c.id WHERE a.id=?', (aid,)).fetchone())
        agent = dict(agent_or_404(conn, aid))
        agent['permissions'] = json.loads(agent.pop('permissions_json'))
        contacts = [dict(r) for r in conn.execute('SELECT c.* FROM chat_contacts c JOIN chat_agents a ON a.chat_id=c.chat_id WHERE a.id=?', (aid,))]
        return {'chat': chat, 'agent': agent, 'contacts': contacts, 'messages': [dict(r) for r in chatstore.list_messages(conn, aid)]}


@router.patch('/agents/{agent_id}')
def patch_agent(agent_id: str, body: AgentPatch):
    with db.tx() as conn:
        agent = agent_or_404(conn, agent_id)
        fields = body.dict(exclude_unset=True)
        if not fields:
            raise HTTPException(422, 'no fields supplied')
        if 'persona_id' in fields and fields['persona_id'] is not None and not conn.execute('SELECT 1 FROM chat_personas WHERE id=?', (fields['persona_id'],)).fetchone():
            raise HTTPException(422, 'unknown persona')
        if 'permissions' in fields:
            if body.permissions is None:
                raise HTTPException(422, 'permissions cannot be null')
            permissions = json.loads(agent['permissions_json'])
            changes = body.permissions.dict(exclude_unset=True)
            if any(v is None for v in changes.values()):
                raise HTTPException(422, 'permission cannot be null')
            permissions.update(changes)
            fields['permissions_json'] = json.dumps(permissions)
            del fields['permissions']
        if 'status' in fields:
            if fields['status'] is None:
                raise HTTPException(422, 'status cannot be null')
            fields['archived_at'] = time.time() if fields['status'] == 'archived' else None
        chatstore.update_agent(conn, agent_id, **fields)
    return {'ok': True}


@router.post('/agents/{agent_id}/{action}')
def change_status(agent_id: str, action: Literal['archive', 'restore', 'pause']):
    return patch_agent(agent_id, AgentPatch(status={'archive': 'archived', 'restore': 'active', 'pause': 'paused'}[action]))


@router.delete('/chats/{chat_id}')
def delete_chat(chat_id: int, confirm: str):
    with db.tx() as conn:
        aid = agent_for_chat(conn, chat_id)
        try:
            chatstore.delete_chat(conn, aid, confirm=confirm)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
    return {'ok': True}


@router.get('/owner-profile')
def get_owner_profile():
    with db.tx() as conn:
        row = conn.execute('SELECT * FROM chat_owner_profile WHERE id=1').fetchone()
        return {'data': json.loads(row['data_json']) if row else {}, 'version': row['version'] if row else 0, 'updated_at': row['updated_at'] if row else None}


@router.put('/owner-profile')
def put_owner_profile(data: dict):
    with db.tx() as conn:
        chatstore.set_owner_profile(conn, data)
    return {'ok': True}


@router.get('/audit')
def audit(target: str):
    with db.tx() as conn:
        return {'rows': [dict(r) for r in chatstore.list_audit(conn, target)]}


@router.get('/contacts/{contact_id}/profile')
def get_person_profile(contact_id: int, agent_id: str):
    with db.tx() as conn:
        if chatstore.get_contact(conn, agent_id, contact_id) is None:
            raise HTTPException(404, 'contact not found')
        profile = chatstore.get_person_profile(conn, agent_id, contact_id)
        if profile is None:
            raise HTTPException(404, 'profile not found')
        return profile


@router.put('/contacts/{contact_id}/profile')
@router.patch('/contacts/{contact_id}/profile')
def put_person_profile(contact_id: int, agent_id: str, data: dict):
    with db.tx() as conn:
        if chatstore.get_contact(conn, agent_id, contact_id) is None:
            raise HTTPException(404, 'contact not found')
        try:
            return chatstore.set_person_profile(conn, agent_id, contact_id, data)
        except ValueError as exc:
            raise HTTPException(422, str(exc))


@router.delete('/contacts/{contact_id}/profile')
def delete_person_profile(contact_id: int, agent_id: str):
    with db.tx() as conn:
        if not chatstore.delete_person_profile(conn, agent_id, contact_id):
            raise HTTPException(404, 'profile not found')
    return {'ok': True}
