from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.database import get_db
from app.core.deps import current_user, site_access
from app.models.entities import (
    User, Site, ContentEntry, ContentType, MediaAsset, WebhookDelivery,
    AuditLog, EntryStatus, WebhookDeliveryStatus, WebhookEndpoint
)
from app.schemas.common import AuditOut

router = APIRouter(prefix='/reports', tags=['Analytics & Audit'])


@router.get('/dashboard', response_model=dict)
def dashboard(site_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    site_access(site_id, db, user)
    statuses = db.execute(select(ContentEntry.status, func.count(ContentEntry.id)).where(
        ContentEntry.site_id == site_id
    ).group_by(ContentEntry.status)).all()
    return {
        'site_id': site_id,
        'content_types': db.scalar(select(func.count(ContentType.id)).where(ContentType.site_id == site_id)) or 0,
        'entries': db.scalar(select(func.count(ContentEntry.id)).where(ContentEntry.site_id == site_id)) or 0,
        'media_assets': db.scalar(select(func.count(MediaAsset.id)).where(MediaAsset.site_id == site_id)) or 0,
        'status_counts': {status.value: count for status, count in statuses},
        'failed_webhooks': db.scalar(select(func.count(WebhookDelivery.id)).join(
            WebhookEndpoint, WebhookDelivery.webhook_id == WebhookEndpoint.id
        ).where(
            WebhookEndpoint.site_id == site_id,
            WebhookDelivery.status == WebhookDeliveryStatus.failed,
        )) or 0,
    }


@router.get('/publishing-calendar', response_model=list[dict])
def publishing_calendar(
    site_id: str,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    site_access(site_id, db, user)
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days)
    entries = db.scalars(select(ContentEntry).where(
        ContentEntry.site_id == site_id,
        ContentEntry.scheduled_for.is_not(None),
        ContentEntry.scheduled_for <= end,
    ).order_by(ContentEntry.scheduled_for)).all()
    return [{'id': e.id, 'title': e.title, 'slug': e.slug, 'status': e.status.value, 'scheduled_for': e.scheduled_for} for e in entries]


@router.get('/content-health', response_model=dict)
def content_health(site_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    site_access(site_id, db, user)
    entries = db.scalars(select(ContentEntry).where(ContentEntry.site_id == site_id, ContentEntry.status != EntryStatus.archived)).all()
    missing_seo_title = sum(1 for e in entries if not (e.seo or {}).get('title'))
    missing_description = sum(1 for e in entries if not (e.seo or {}).get('description'))
    stale_cutoff = datetime.now(timezone.utc) - timedelta(days=180)
    stale = sum(1 for e in entries if (e.updated_at if e.updated_at.tzinfo else e.updated_at.replace(tzinfo=timezone.utc)) < stale_cutoff)
    return {
        'total_entries': len(entries),
        'missing_seo_title': missing_seo_title,
        'missing_meta_description': missing_description,
        'stale_entries_180_days': stale,
        'health_score': max(0, 100 - missing_seo_title * 2 - missing_description * 2 - stale),
    }


@router.get('/audit-logs', response_model=list[AuditOut])
def audit_logs(
    site_id: str | None = None,
    action: str | None = None,
    actor_id: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if site_id:
        site_access(site_id, db, user)
    stmt = select(AuditLog)
    if site_id:
        stmt = stmt.where(AuditLog.site_id == site_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if actor_id:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    return db.scalars(stmt.order_by(AuditLog.created_at.desc()).limit(limit)).all()


@router.get('/platform', response_model=dict)
def platform_dashboard(db: Session = Depends(get_db), user: User = Depends(current_user)):
    if user.role.value not in ('super_admin', 'platform_admin', 'auditor', 'support'):
        from fastapi import HTTPException
        raise HTTPException(403, 'Platform role required')
    return {
        'sites': db.scalar(select(func.count(Site.id))) or 0,
        'content_types': db.scalar(select(func.count(ContentType.id))) or 0,
        'entries': db.scalar(select(func.count(ContentEntry.id))) or 0,
        'published_entries': db.scalar(select(func.count(ContentEntry.id)).where(ContentEntry.status == EntryStatus.published)) or 0,
        'media_assets': db.scalar(select(func.count(MediaAsset.id))) or 0,
    }
