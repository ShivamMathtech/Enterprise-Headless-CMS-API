import secrets
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.core.deps import current_user, site_access
from app.core.security import create_api_key
from app.models.entities import (
    User, Role, SiteRole, ApiKey, WebhookEndpoint, WebhookDelivery,
    WebhookDeliveryStatus
)
from app.schemas.common import *
from app.services import audit, sign_webhook

router = APIRouter(tags=['API Keys & Webhooks'])
DEV_ROLES = {SiteRole.owner, SiteRole.site_admin, SiteRole.developer}


@router.post('/api-keys', response_model=ApiKeyOut, status_code=201)
def create_key(data: ApiKeyIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if data.site_id:
        site_access(data.site_id, db, user, DEV_ROLES)
    elif user.role not in (Role.super_admin, Role.platform_admin, Role.developer):
        raise HTTPException(403, 'Platform developer role required')
    plaintext, prefix, key_hash = create_api_key()
    key = ApiKey(
        site_id=data.site_id,
        name=data.name,
        prefix=prefix,
        key_hash=key_hash,
        scopes=data.scopes,
        expires_at=data.expires_at,
        created_by=user.id,
    )
    db.add(key)
    db.flush()
    audit(db, user.id, 'api_key.created', 'api_key', key.id, {'prefix': prefix, 'scopes': data.scopes}, data.site_id)
    db.commit()
    db.refresh(key)
    return ApiKeyOut.model_validate(key).model_copy(update={'secret': plaintext})


@router.get('/api-keys', response_model=list[ApiKeyOut])
def list_keys(site_id: str | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if site_id:
        site_access(site_id, db, user, DEV_ROLES)
        stmt = select(ApiKey).where(ApiKey.site_id == site_id)
    else:
        if user.role not in (Role.super_admin, Role.platform_admin, Role.developer, Role.auditor):
            raise HTTPException(403, 'Platform role required')
        stmt = select(ApiKey)
    return db.scalars(stmt.order_by(ApiKey.created_at.desc())).all()


@router.post('/api-keys/{key_id}/rotate', response_model=ApiKeyOut)
def rotate_key(key_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    old = db.get(ApiKey, key_id)
    if not old:
        raise HTTPException(404, 'API key not found')
    if old.site_id:
        site_access(old.site_id, db, user, DEV_ROLES)
    elif user.role not in (Role.super_admin, Role.platform_admin, Role.developer):
        raise HTTPException(403, 'Platform developer role required')
    old.revoked_at = datetime.now(timezone.utc)
    plaintext, prefix, key_hash = create_api_key()
    new = ApiKey(
        site_id=old.site_id,
        name=f'{old.name} (rotated)',
        prefix=prefix,
        key_hash=key_hash,
        scopes=old.scopes,
        expires_at=old.expires_at,
        created_by=user.id,
    )
    db.add(new)
    db.flush()
    audit(db, user.id, 'api_key.rotated', 'api_key', new.id, {'previous_id': old.id}, old.site_id)
    db.commit()
    db.refresh(new)
    return ApiKeyOut.model_validate(new).model_copy(update={'secret': plaintext})


@router.post('/api-keys/{key_id}/revoke', response_model=Message)
def revoke_key(key_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    key = db.get(ApiKey, key_id)
    if not key:
        raise HTTPException(404, 'API key not found')
    if key.site_id:
        site_access(key.site_id, db, user, DEV_ROLES)
    elif user.role not in (Role.super_admin, Role.platform_admin, Role.developer):
        raise HTTPException(403, 'Platform developer role required')
    key.revoked_at = datetime.now(timezone.utc)
    audit(db, user.id, 'api_key.revoked', 'api_key', key.id, site_id=key.site_id)
    db.commit()
    return Message(message='API key revoked')


@router.post('/webhooks', response_model=WebhookOut, status_code=201)
def create_webhook(data: WebhookIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    site_access(data.site_id, db, user, DEV_ROLES)
    hook = WebhookEndpoint(
        site_id=data.site_id,
        name=data.name,
        url=data.url,
        secret=secrets.token_urlsafe(32),
        events=data.events,
        created_by=user.id,
    )
    db.add(hook)
    db.flush()
    audit(db, user.id, 'webhook.created', 'webhook', hook.id, {'events': data.events}, data.site_id)
    db.commit()
    db.refresh(hook)
    return hook


@router.get('/webhooks', response_model=list[WebhookOut])
def list_webhooks(site_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    site_access(site_id, db, user, DEV_ROLES)
    return db.scalars(select(WebhookEndpoint).where(WebhookEndpoint.site_id == site_id).order_by(WebhookEndpoint.created_at.desc())).all()


@router.patch('/webhooks/{webhook_id}', response_model=WebhookOut)
def update_webhook(webhook_id: str, data: WebhookUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    hook = db.get(WebhookEndpoint, webhook_id)
    if not hook:
        raise HTTPException(404, 'Webhook not found')
    site_access(hook.site_id, db, user, DEV_ROLES)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(hook, key, value)
    audit(db, user.id, 'webhook.updated', 'webhook', hook.id, site_id=hook.site_id)
    db.commit()
    db.refresh(hook)
    return hook


@router.post('/webhooks/{webhook_id}/rotate-secret', response_model=dict)
def rotate_webhook_secret(webhook_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    hook = db.get(WebhookEndpoint, webhook_id)
    if not hook:
        raise HTTPException(404, 'Webhook not found')
    site_access(hook.site_id, db, user, DEV_ROLES)
    hook.secret = secrets.token_urlsafe(32)
    audit(db, user.id, 'webhook.secret_rotated', 'webhook', hook.id, site_id=hook.site_id)
    db.commit()
    return {'webhook_id': hook.id, 'secret': hook.secret}


@router.post('/webhooks/{webhook_id}/test', response_model=WebhookDeliveryOut)
def test_webhook(webhook_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    hook = db.get(WebhookEndpoint, webhook_id)
    if not hook:
        raise HTTPException(404, 'Webhook not found')
    site_access(hook.site_id, db, user, DEV_ROLES)
    payload = {'event': 'webhook.test', 'site_id': hook.site_id, 'timestamp': datetime.now(timezone.utc).isoformat()}
    signature = sign_webhook(hook.secret, payload)
    delivery = WebhookDelivery(
        webhook_id=hook.id,
        event_name='webhook.test',
        payload=payload,
        status=WebhookDeliveryStatus.succeeded,
        attempt_count=1,
        response_code=200,
        response_body=f'Mock delivery accepted; signature={signature}',
        delivered_at=datetime.now(timezone.utc),
    )
    db.add(delivery)
    db.flush()
    audit(db, user.id, 'webhook.tested', 'webhook_delivery', delivery.id, site_id=hook.site_id)
    db.commit()
    db.refresh(delivery)
    return delivery


@router.get('/webhooks/{webhook_id}/deliveries', response_model=list[WebhookDeliveryOut])
def list_deliveries(webhook_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    hook = db.get(WebhookEndpoint, webhook_id)
    if not hook:
        raise HTTPException(404, 'Webhook not found')
    site_access(hook.site_id, db, user, DEV_ROLES)
    return db.scalars(select(WebhookDelivery).where(WebhookDelivery.webhook_id == webhook_id).order_by(WebhookDelivery.created_at.desc())).all()


@router.post('/webhook-deliveries/{delivery_id}/retry', response_model=WebhookDeliveryOut)
def retry_delivery(delivery_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    delivery = db.get(WebhookDelivery, delivery_id)
    if not delivery:
        raise HTTPException(404, 'Delivery not found')
    hook = db.get(WebhookEndpoint, delivery.webhook_id)
    site_access(hook.site_id, db, user, DEV_ROLES)
    delivery.status = WebhookDeliveryStatus.pending
    delivery.attempt_count += 1
    delivery.response_code = None
    delivery.response_body = None
    delivery.next_attempt_at = datetime.now(timezone.utc)
    audit(db, user.id, 'webhook.delivery_retried', 'webhook_delivery', delivery.id, site_id=hook.site_id)
    db.commit()
    db.refresh(delivery)
    return delivery


@router.delete('/webhooks/{webhook_id}', response_model=Message)
def delete_webhook(webhook_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    hook = db.get(WebhookEndpoint, webhook_id)
    if not hook:
        raise HTTPException(404, 'Webhook not found')
    site_access(hook.site_id, db, user, DEV_ROLES)
    db.delete(hook)
    audit(db, user.id, 'webhook.deleted', 'webhook', webhook_id, site_id=hook.site_id)
    db.commit()
    return Message(message='Webhook deleted')
