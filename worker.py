from datetime import datetime, timezone
from celery import Celery
from sqlalchemy import select
from app.core.config import get_settings
from app.database import SessionLocal
from app.models.entities import ContentEntry, EntryStatus, WebhookDelivery, WebhookDeliveryStatus
from app.services import mark_published

settings = get_settings()
celery_app = Celery('enterprise-cms', broker=settings.redis_url or 'memory://', backend=settings.redis_url or 'cache+memory://')
celery_app.conf.beat_schedule = {
    'publish-scheduled-content-every-minute': {
        'task': 'worker.publish_scheduled_content',
        'schedule': 60.0,
    },
    'retry-webhook-deliveries-every-minute': {
        'task': 'worker.retry_webhook_deliveries',
        'schedule': 60.0,
    },
}


def _aware(value):
    return value if value is None or value.tzinfo else value.replace(tzinfo=timezone.utc)


@celery_app.task
def publish_scheduled_content():
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        entries = db.scalars(select(ContentEntry).where(
            ContentEntry.status == EntryStatus.scheduled,
            ContentEntry.scheduled_for.is_not(None),
        )).all()
        processed = 0
        for entry in entries:
            if _aware(entry.scheduled_for) <= now:
                mark_published(db, entry, entry.updated_by)
                processed += 1
        db.commit()
        return {'processed': processed}
    finally:
        db.close()


@celery_app.task
def retry_webhook_deliveries():
    db = SessionLocal()
    try:
        rows = db.scalars(select(WebhookDelivery).where(WebhookDelivery.status == WebhookDeliveryStatus.pending).limit(100)).all()
        for row in rows:
            row.attempt_count += 1
            row.status = WebhookDeliveryStatus.succeeded
            row.response_code = 202
            row.response_body = 'Mock worker delivery accepted. Replace with provider adapter in production.'
            row.delivered_at = datetime.now(timezone.utc)
        db.commit()
        return {'processed': len(rows)}
    finally:
        db.close()
