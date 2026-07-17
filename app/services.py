import hashlib
import hmac
import json
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.entities import (
    AuditLog, ContentEntry, ContentRevision, ContentType, EntryStatus, EntryTag,
    Tag, WebhookEndpoint, WebhookDelivery, WebhookDeliveryStatus
)


def audit(db: Session, actor_id: str | None, action: str, entity_type: str, entity_id: str | None = None,
          details: dict | None = None, site_id: str | None = None, request_id: str | None = None):
    db.add(AuditLog(
        site_id=site_id,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details or {},
        request_id=request_id,
    ))


def entry_snapshot(entry: ContentEntry) -> dict:
    return {
        'title': entry.title,
        'slug': entry.slug,
        'status': entry.status.value,
        'workflow_stage': entry.workflow_stage,
        'data': entry.data,
        'seo': entry.seo,
        'locale': entry.locale,
        'environment_id': entry.environment_id,
        'content_type_id': entry.content_type_id,
        'version': entry.version,
        'published_at': entry.published_at.isoformat() if entry.published_at else None,
        'scheduled_for': entry.scheduled_for.isoformat() if entry.scheduled_for else None,
    }


def create_revision(db: Session, entry: ContentEntry, user_id: str, note: str | None = None):
    db.add(ContentRevision(
        entry_id=entry.id,
        version=entry.version,
        snapshot=entry_snapshot(entry),
        note=note,
        created_by=user_id,
    ))


def validate_entry_data(content_type: ContentType, data: dict):
    schema = content_type.schema_definition or {}
    fields = schema.get('fields', [])
    errors = []
    for field in fields:
        key = field.get('key')
        field_type = field.get('type', 'text')
        required = bool(field.get('required'))
        value = data.get(key)
        if required and (value is None or value == ''):
            errors.append({'field': key, 'message': 'Field is required'})
            continue
        if value is None:
            continue
        if field_type in ('text', 'rich_text', 'email', 'url') and not isinstance(value, str):
            errors.append({'field': key, 'message': 'Expected string'})
        elif field_type in ('number', 'integer') and not isinstance(value, (int, float)):
            errors.append({'field': key, 'message': 'Expected number'})
        elif field_type == 'boolean' and not isinstance(value, bool):
            errors.append({'field': key, 'message': 'Expected boolean'})
        elif field_type in ('json', 'object') and not isinstance(value, dict):
            errors.append({'field': key, 'message': 'Expected object'})
        elif field_type in ('list', 'array', 'media_list', 'reference_list') and not isinstance(value, list):
            errors.append({'field': key, 'message': 'Expected list'})
        choices = field.get('choices')
        if choices and value not in choices:
            errors.append({'field': key, 'message': f'Value must be one of {choices}'})
    if errors:
        raise HTTPException(422, {'message': 'Content validation failed', 'errors': errors})


def replace_entry_tags(db: Session, entry_id: str, site_id: str, tag_ids: list[str]):
    db.query(EntryTag).filter(EntryTag.entry_id == entry_id).delete(synchronize_session=False)
    if not tag_ids:
        return
    found = db.scalars(select(Tag).where(Tag.id.in_(tag_ids), Tag.site_id == site_id)).all()
    if len(found) != len(set(tag_ids)):
        raise HTTPException(422, 'One or more tags are invalid for this site')
    for tag_id in set(tag_ids):
        db.add(EntryTag(entry_id=entry_id, tag_id=tag_id))


def enqueue_webhooks(db: Session, site_id: str, event_name: str, payload: dict):
    hooks = db.scalars(select(WebhookEndpoint).where(
        WebhookEndpoint.site_id == site_id,
        WebhookEndpoint.is_active.is_(True),
    )).all()
    for hook in hooks:
        if event_name in (hook.events or []) or '*' in (hook.events or []):
            db.add(WebhookDelivery(
                webhook_id=hook.id,
                event_name=event_name,
                payload=payload,
                status=WebhookDeliveryStatus.pending,
            ))


def sign_webhook(secret: str, payload: dict) -> str:
    body = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode()
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def mark_published(db: Session, entry: ContentEntry, user_id: str):
    now = datetime.now(timezone.utc)
    entry.status = EntryStatus.published
    entry.workflow_stage = 'published'
    entry.published_at = now
    entry.published_by = user_id
    entry.scheduled_for = None
    enqueue_webhooks(db, entry.site_id, 'entry.published', {
        'entry_id': entry.id,
        'site_id': entry.site_id,
        'slug': entry.slug,
        'locale': entry.locale,
        'published_at': now.isoformat(),
    })
