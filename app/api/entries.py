from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_, func
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.common import *
from app.models.entities import (
    User, ContentEntry, ContentType, Environment, Locale, ContentRevision, EntryStatus,
    EntryComment, EntryTag, SiteRole
)
from app.core.deps import current_user, site_access
from app.core.security import create_preview_token
from app.services import (
    audit, create_revision, validate_entry_data, replace_entry_tags,
    mark_published, enqueue_webhooks
)

router = APIRouter(prefix='/entries', tags=['Content Entries & Workflow'])
WRITE_ROLES = {SiteRole.owner, SiteRole.site_admin, SiteRole.content_manager, SiteRole.editor, SiteRole.author}
REVIEW_ROLES = {SiteRole.owner, SiteRole.site_admin, SiteRole.content_manager, SiteRole.reviewer}
PUBLISH_ROLES = {SiteRole.owner, SiteRole.site_admin, SiteRole.content_manager}
SEO_ROLES = {SiteRole.owner, SiteRole.site_admin, SiteRole.content_manager, SiteRole.seo_manager}


def _entry(db: Session, entry_id: str) -> ContentEntry:
    entry = db.get(ContentEntry, entry_id)
    if not entry:
        raise HTTPException(404, 'Entry not found')
    return entry


def _now():
    return datetime.now(timezone.utc)


def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


@router.post('', response_model=EntryOut, status_code=201)
def create_entry(data: EntryCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    site_access(data.site_id, db, user, WRITE_ROLES)
    environment = db.get(Environment, data.environment_id)
    content_type = db.get(ContentType, data.content_type_id)
    if not environment or environment.site_id != data.site_id:
        raise HTTPException(422, 'Invalid environment')
    if not content_type or content_type.site_id != data.site_id:
        raise HTTPException(422, 'Invalid content type')
    if not content_type.is_published:
        raise HTTPException(409, 'Publish the content type before creating entries')
    locale = db.scalar(select(Locale).where(Locale.site_id == data.site_id, Locale.code == data.locale, Locale.is_active.is_(True)))
    if not locale:
        raise HTTPException(422, 'Unsupported locale')
    if content_type.is_singleton and db.scalar(select(ContentEntry).where(
        ContentEntry.environment_id == data.environment_id,
        ContentEntry.content_type_id == data.content_type_id,
        ContentEntry.locale == data.locale,
        ContentEntry.status != EntryStatus.archived,
    )):
        raise HTTPException(409, 'Singleton content type already has an entry')
    validate_entry_data(content_type, data.data)
    entry = ContentEntry(
        site_id=data.site_id,
        environment_id=data.environment_id,
        content_type_id=data.content_type_id,
        locale=data.locale,
        title=data.title,
        slug=data.slug,
        data=data.data,
        seo=data.seo,
        created_by=user.id,
        updated_by=user.id,
    )
    db.add(entry)
    db.flush()
    create_revision(db, entry, user.id, 'Initial version')
    replace_entry_tags(db, entry.id, entry.site_id, data.tag_ids)
    audit(db, user.id, 'entry.created', 'content_entry', entry.id, {'title': entry.title}, entry.site_id)
    db.commit()
    db.refresh(entry)
    return entry


@router.get('', response_model=list[EntryOut])
def list_entries(
    site_id: str,
    environment_id: str | None = None,
    content_type_id: str | None = None,
    locale: str | None = None,
    status: str | None = None,
    search: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    site_access(site_id, db, user)
    stmt = select(ContentEntry).where(ContentEntry.site_id == site_id)
    if environment_id:
        stmt = stmt.where(ContentEntry.environment_id == environment_id)
    if content_type_id:
        stmt = stmt.where(ContentEntry.content_type_id == content_type_id)
    if locale:
        stmt = stmt.where(ContentEntry.locale == locale)
    if status:
        try:
            stmt = stmt.where(ContentEntry.status == EntryStatus(status))
        except ValueError:
            raise HTTPException(422, 'Invalid status')
    if search:
        pattern = f'%{search}%'
        stmt = stmt.where(or_(ContentEntry.title.ilike(pattern), ContentEntry.slug.ilike(pattern)))
    return db.scalars(stmt.order_by(ContentEntry.updated_at.desc()).offset(offset).limit(limit)).all()


@router.get('/search', response_model=list[EntryOut])
def search_entries(
    site_id: str,
    q: str = Query(min_length=2),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    site_access(site_id, db, user)
    pattern = f'%{q}%'
    return db.scalars(select(ContentEntry).where(
        ContentEntry.site_id == site_id,
        or_(ContentEntry.title.ilike(pattern), ContentEntry.slug.ilike(pattern)),
    ).order_by(ContentEntry.updated_at.desc()).limit(100)).all()


@router.get('/{entry_id}', response_model=EntryOut)
def get_entry(entry_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    entry = _entry(db, entry_id)
    site_access(entry.site_id, db, user)
    return entry


@router.patch('/{entry_id}', response_model=EntryOut)
def update_entry(entry_id: str, data: EntryUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    entry = _entry(db, entry_id)
    site_access(entry.site_id, db, user, WRITE_ROLES | SEO_ROLES)
    if entry.status == EntryStatus.archived:
        raise HTTPException(409, 'Archived entries cannot be edited')
    if data.expected_version is not None and data.expected_version != entry.version:
        raise HTTPException(409, {'message': 'Version conflict', 'current_version': entry.version})
    content_type = db.get(ContentType, entry.content_type_id)
    values = data.model_dump(exclude_unset=True)
    values.pop('expected_version', None)
    note = values.pop('note', None)
    tag_ids = values.pop('tag_ids', None)
    proposed_data = values.get('data', entry.data)
    validate_entry_data(content_type, proposed_data)
    for key, value in values.items():
        setattr(entry, key, value)
    if tag_ids is not None:
        replace_entry_tags(db, entry.id, entry.site_id, tag_ids)
    entry.version += 1
    entry.updated_by = user.id
    if entry.status in (EntryStatus.approved, EntryStatus.rejected):
        entry.status = EntryStatus.draft
        entry.workflow_stage = 'draft'
        entry.approved_by = None
    create_revision(db, entry, user.id, note or f'Created version {entry.version}')
    audit(db, user.id, 'entry.updated', 'content_entry', entry.id, {'version': entry.version}, entry.site_id)
    enqueue_webhooks(db, entry.site_id, 'entry.updated', {'entry_id': entry.id, 'version': entry.version})
    db.commit()
    db.refresh(entry)
    return entry


@router.delete('/{entry_id}', response_model=Message)
def archive_entry(entry_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    entry = _entry(db, entry_id)
    site_access(entry.site_id, db, user, PUBLISH_ROLES)
    entry.status = EntryStatus.archived
    entry.workflow_stage = 'archived'
    entry.archived_at = _now()
    entry.updated_by = user.id
    audit(db, user.id, 'entry.archived', 'content_entry', entry.id, site_id=entry.site_id)
    enqueue_webhooks(db, entry.site_id, 'entry.archived', {'entry_id': entry.id})
    db.commit()
    return Message(message='Entry archived')


@router.get('/{entry_id}/revisions', response_model=list[RevisionOut])
def list_revisions(entry_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    entry = _entry(db, entry_id)
    site_access(entry.site_id, db, user)
    return db.scalars(select(ContentRevision).where(ContentRevision.entry_id == entry_id).order_by(ContentRevision.version.desc())).all()


@router.post('/{entry_id}/revisions/{version}/restore', response_model=EntryOut)
def restore_revision(entry_id: str, version: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    entry = _entry(db, entry_id)
    site_access(entry.site_id, db, user, WRITE_ROLES)
    revision = db.scalar(select(ContentRevision).where(ContentRevision.entry_id == entry_id, ContentRevision.version == version))
    if not revision:
        raise HTTPException(404, 'Revision not found')
    snapshot = revision.snapshot
    for key in ('title', 'slug', 'data', 'seo', 'locale', 'environment_id', 'content_type_id'):
        if key in snapshot:
            setattr(entry, key, snapshot[key])
    entry.version += 1
    entry.status = EntryStatus.draft
    entry.workflow_stage = 'draft'
    entry.updated_by = user.id
    entry.approved_by = None
    entry.scheduled_for = None
    create_revision(db, entry, user.id, f'Restored revision {version} as version {entry.version}')
    audit(db, user.id, 'entry.revision_restored', 'content_entry', entry.id, {'restored_version': version}, entry.site_id)
    db.commit()
    db.refresh(entry)
    return entry


@router.post('/{entry_id}/submit', response_model=EntryOut)
def submit_for_review(entry_id: str, data: ReviewDecisionIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    entry = _entry(db, entry_id)
    site_access(entry.site_id, db, user, WRITE_ROLES)
    if entry.status not in (EntryStatus.draft, EntryStatus.rejected):
        raise HTTPException(409, 'Only draft or rejected entries can be submitted')
    entry.status = EntryStatus.in_review
    entry.workflow_stage = 'review'
    entry.updated_by = user.id
    audit(db, user.id, 'entry.submitted', 'content_entry', entry.id, {'note': data.note}, entry.site_id)
    enqueue_webhooks(db, entry.site_id, 'entry.submitted', {'entry_id': entry.id})
    db.commit()
    db.refresh(entry)
    return entry


@router.post('/{entry_id}/approve', response_model=EntryOut)
def approve_entry(entry_id: str, data: ReviewDecisionIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    entry = _entry(db, entry_id)
    site_access(entry.site_id, db, user, REVIEW_ROLES)
    if entry.status != EntryStatus.in_review:
        raise HTTPException(409, 'Entry is not in review')
    entry.status = EntryStatus.approved
    entry.workflow_stage = 'approved'
    entry.approved_by = user.id
    entry.updated_by = user.id
    audit(db, user.id, 'entry.approved', 'content_entry', entry.id, {'note': data.note}, entry.site_id)
    enqueue_webhooks(db, entry.site_id, 'entry.approved', {'entry_id': entry.id})
    db.commit()
    db.refresh(entry)
    return entry


@router.post('/{entry_id}/reject', response_model=EntryOut)
def reject_entry(entry_id: str, data: ReviewDecisionIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    entry = _entry(db, entry_id)
    site_access(entry.site_id, db, user, REVIEW_ROLES)
    if entry.status != EntryStatus.in_review:
        raise HTTPException(409, 'Entry is not in review')
    entry.status = EntryStatus.rejected
    entry.workflow_stage = 'rejected'
    entry.updated_by = user.id
    audit(db, user.id, 'entry.rejected', 'content_entry', entry.id, {'note': data.note}, entry.site_id)
    enqueue_webhooks(db, entry.site_id, 'entry.rejected', {'entry_id': entry.id, 'note': data.note})
    db.commit()
    db.refresh(entry)
    return entry


@router.post('/{entry_id}/publish', response_model=EntryOut)
def publish_entry(entry_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    entry = _entry(db, entry_id)
    site_access(entry.site_id, db, user, PUBLISH_ROLES)
    if entry.status not in (EntryStatus.approved, EntryStatus.published):
        raise HTTPException(409, 'Entry must be approved before publishing')
    mark_published(db, entry, user.id)
    audit(db, user.id, 'entry.published', 'content_entry', entry.id, site_id=entry.site_id)
    db.commit()
    db.refresh(entry)
    return entry


@router.post('/{entry_id}/unpublish', response_model=EntryOut)
def unpublish_entry(entry_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    entry = _entry(db, entry_id)
    site_access(entry.site_id, db, user, PUBLISH_ROLES)
    if entry.status != EntryStatus.published:
        raise HTTPException(409, 'Entry is not published')
    entry.status = EntryStatus.approved
    entry.workflow_stage = 'approved'
    entry.published_at = None
    entry.published_by = None
    entry.updated_by = user.id
    audit(db, user.id, 'entry.unpublished', 'content_entry', entry.id, site_id=entry.site_id)
    enqueue_webhooks(db, entry.site_id, 'entry.unpublished', {'entry_id': entry.id})
    db.commit()
    db.refresh(entry)
    return entry


@router.post('/{entry_id}/schedule', response_model=EntryOut)
def schedule_entry(entry_id: str, data: ScheduleIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    entry = _entry(db, entry_id)
    site_access(entry.site_id, db, user, PUBLISH_ROLES)
    publish_at = data.publish_at if data.publish_at.tzinfo else data.publish_at.replace(tzinfo=timezone.utc)
    if publish_at <= _now():
        raise HTTPException(422, 'publish_at must be in the future')
    if entry.status != EntryStatus.approved:
        raise HTTPException(409, 'Entry must be approved before scheduling')
    entry.status = EntryStatus.scheduled
    entry.workflow_stage = 'scheduled'
    entry.scheduled_for = publish_at
    entry.updated_by = user.id
    audit(db, user.id, 'entry.scheduled', 'content_entry', entry.id, {'publish_at': publish_at.isoformat()}, entry.site_id)
    db.commit()
    db.refresh(entry)
    return entry


@router.post('/{entry_id}/cancel-schedule', response_model=EntryOut)
def cancel_schedule(entry_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    entry = _entry(db, entry_id)
    site_access(entry.site_id, db, user, PUBLISH_ROLES)
    if entry.status != EntryStatus.scheduled:
        raise HTTPException(409, 'Entry is not scheduled')
    entry.status = EntryStatus.approved
    entry.workflow_stage = 'approved'
    entry.scheduled_for = None
    audit(db, user.id, 'entry.schedule_cancelled', 'content_entry', entry.id, site_id=entry.site_id)
    db.commit()
    db.refresh(entry)
    return entry


@router.post('/{entry_id}/clone', response_model=EntryOut, status_code=201)
def clone_entry(entry_id: str, environment_id: str, locale: str, slug: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    source = _entry(db, entry_id)
    site_access(source.site_id, db, user, WRITE_ROLES)
    environment = db.get(Environment, environment_id)
    if not environment or environment.site_id != source.site_id:
        raise HTTPException(422, 'Invalid environment')
    clone = ContentEntry(
        site_id=source.site_id,
        environment_id=environment_id,
        content_type_id=source.content_type_id,
        locale=locale,
        title=source.title,
        slug=slug,
        data=source.data,
        seo=source.seo,
        created_by=user.id,
        updated_by=user.id,
    )
    db.add(clone)
    db.flush()
    create_revision(db, clone, user.id, f'Cloned from {source.id}')
    tag_ids = db.scalars(select(EntryTag.tag_id).where(EntryTag.entry_id == source.id)).all()
    replace_entry_tags(db, clone.id, clone.site_id, list(tag_ids))
    audit(db, user.id, 'entry.cloned', 'content_entry', clone.id, {'source_id': source.id}, source.site_id)
    db.commit()
    db.refresh(clone)
    return clone


@router.post('/{entry_id}/preview-token', response_model=PreviewTokenOut)
def preview_token(entry_id: str, expires_minutes: int = Query(60, ge=5, le=1440), db: Session = Depends(get_db), user: User = Depends(current_user)):
    entry = _entry(db, entry_id)
    site_access(entry.site_id, db, user)
    return PreviewTokenOut(token=create_preview_token(entry.id, expires_minutes), expires_in_minutes=expires_minutes)


@router.post('/{entry_id}/comments', response_model=CommentOut, status_code=201)
def add_comment(entry_id: str, data: CommentIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    entry = _entry(db, entry_id)
    site_access(entry.site_id, db, user)
    if data.parent_id:
        parent = db.get(EntryComment, data.parent_id)
        if not parent or parent.entry_id != entry_id:
            raise HTTPException(422, 'Invalid parent comment')
    comment = EntryComment(entry_id=entry_id, author_id=user.id, body=data.body, parent_id=data.parent_id)
    db.add(comment)
    db.flush()
    audit(db, user.id, 'entry.comment_added', 'entry_comment', comment.id, {'entry_id': entry_id}, entry.site_id)
    db.commit()
    db.refresh(comment)
    return comment


@router.get('/{entry_id}/comments', response_model=list[CommentOut])
def list_comments(entry_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    entry = _entry(db, entry_id)
    site_access(entry.site_id, db, user)
    return db.scalars(select(EntryComment).where(EntryComment.entry_id == entry_id).order_by(EntryComment.created_at)).all()


@router.post('/{entry_id}/comments/{comment_id}/resolve', response_model=CommentOut)
def resolve_comment(entry_id: str, comment_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    entry = _entry(db, entry_id)
    site_access(entry.site_id, db, user, REVIEW_ROLES | WRITE_ROLES)
    comment = db.get(EntryComment, comment_id)
    if not comment or comment.entry_id != entry_id:
        raise HTTPException(404, 'Comment not found')
    comment.is_resolved = True
    comment.resolved_by = user.id
    audit(db, user.id, 'entry.comment_resolved', 'entry_comment', comment.id, site_id=entry.site_id)
    db.commit()
    db.refresh(comment)
    return comment


@router.post('/process-scheduled', response_model=dict)
def process_scheduled(db: Session = Depends(get_db), user: User = Depends(current_user)):
    if user.role.value not in ('super_admin', 'platform_admin'):
        raise HTTPException(403, 'Platform administrator required')
    now = _now()
    entries = db.scalars(select(ContentEntry).where(
        ContentEntry.status == EntryStatus.scheduled,
        ContentEntry.scheduled_for.is_not(None),
    )).all()
    processed = 0
    for entry in entries:
        if _aware(entry.scheduled_for) <= now:
            mark_published(db, entry, user.id)
            audit(db, user.id, 'entry.auto_published', 'content_entry', entry.id, site_id=entry.site_id)
            processed += 1
    db.commit()
    return {'processed': processed}


@router.get('/metrics/status-counts', response_model=dict)
def status_counts(site_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    site_access(site_id, db, user)
    rows = db.execute(select(ContentEntry.status, func.count(ContentEntry.id)).where(ContentEntry.site_id == site_id).group_by(ContentEntry.status)).all()
    return {status.value: count for status, count in rows}
