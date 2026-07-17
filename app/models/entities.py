from __future__ import annotations
import enum
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    String, Boolean, DateTime, ForeignKey, Integer, Text, Enum, UniqueConstraint,
    Index, JSON
)
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


def uid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(str, enum.Enum):
    super_admin = 'super_admin'
    platform_admin = 'platform_admin'
    auditor = 'auditor'
    support = 'support'
    developer = 'developer'
    user = 'user'


class SiteRole(str, enum.Enum):
    owner = 'owner'
    site_admin = 'site_admin'
    content_manager = 'content_manager'
    editor = 'editor'
    author = 'author'
    reviewer = 'reviewer'
    seo_manager = 'seo_manager'
    media_manager = 'media_manager'
    developer = 'developer'
    viewer = 'viewer'


class EntryStatus(str, enum.Enum):
    draft = 'draft'
    in_review = 'in_review'
    approved = 'approved'
    published = 'published'
    scheduled = 'scheduled'
    rejected = 'rejected'
    archived = 'archived'


class MediaStatus(str, enum.Enum):
    processing = 'processing'
    ready = 'ready'
    quarantined = 'quarantined'
    archived = 'archived'


class WebhookDeliveryStatus(str, enum.Enum):
    pending = 'pending'
    succeeded = 'succeeded'
    failed = 'failed'


class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(150))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.user, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class RefreshToken(Base):
    __tablename__ = 'refresh_tokens'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    family_id: Mapped[str] = mapped_column(String(64), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Site(Base):
    __tablename__ = 'sites'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_locale: Mapped[str] = mapped_column(String(20), default='en-US')
    timezone: Mapped[str] = mapped_column(String(80), default='UTC')
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SiteMember(Base):
    __tablename__ = 'site_members'
    __table_args__ = (UniqueConstraint('site_id', 'user_id', name='uq_site_member'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    site_id: Mapped[str] = mapped_column(ForeignKey('sites.id', ondelete='CASCADE'), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    role: Mapped[SiteRole] = mapped_column(Enum(SiteRole), default=SiteRole.viewer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Environment(Base):
    __tablename__ = 'environments'
    __table_args__ = (UniqueConstraint('site_id', 'key', name='uq_site_environment'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    site_id: Mapped[str] = mapped_column(ForeignKey('sites.id', ondelete='CASCADE'), index=True)
    key: Mapped[str] = mapped_column(String(50), index=True)
    name: Mapped[str] = mapped_column(String(100))
    is_production: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Locale(Base):
    __tablename__ = 'locales'
    __table_args__ = (UniqueConstraint('site_id', 'code', name='uq_site_locale'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    site_id: Mapped[str] = mapped_column(ForeignKey('sites.id', ondelete='CASCADE'), index=True)
    code: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(80))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ContentType(Base):
    __tablename__ = 'content_types'
    __table_args__ = (UniqueConstraint('site_id', 'key', name='uq_site_content_type'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    site_id: Mapped[str] = mapped_column(ForeignKey('sites.id', ondelete='CASCADE'), index=True)
    key: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    schema_definition: Mapped[dict] = mapped_column(JSON, default=dict)
    display_field: Mapped[str] = mapped_column(String(80), default='title')
    is_singleton: Mapped[bool] = mapped_column(Boolean, default=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ContentEntry(Base):
    __tablename__ = 'content_entries'
    __table_args__ = (
        UniqueConstraint('environment_id', 'content_type_id', 'locale', 'slug', name='uq_entry_slug_scope'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    site_id: Mapped[str] = mapped_column(ForeignKey('sites.id', ondelete='CASCADE'), index=True)
    environment_id: Mapped[str] = mapped_column(ForeignKey('environments.id', ondelete='CASCADE'), index=True)
    content_type_id: Mapped[str] = mapped_column(ForeignKey('content_types.id', ondelete='CASCADE'), index=True)
    locale: Mapped[str] = mapped_column(String(20), index=True)
    title: Mapped[str] = mapped_column(String(250), index=True)
    slug: Mapped[str] = mapped_column(String(250), index=True)
    status: Mapped[EntryStatus] = mapped_column(Enum(EntryStatus), default=EntryStatus.draft, index=True)
    workflow_stage: Mapped[str] = mapped_column(String(50), default='draft')
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    seo: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    updated_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    approved_by: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    published_by: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ContentRevision(Base):
    __tablename__ = 'content_revisions'
    __table_args__ = (UniqueConstraint('entry_id', 'version', name='uq_entry_revision'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    entry_id: Mapped[str] = mapped_column(ForeignKey('content_entries.id', ondelete='CASCADE'), index=True)
    version: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Tag(Base):
    __tablename__ = 'tags'
    __table_args__ = (UniqueConstraint('site_id', 'slug', name='uq_site_tag'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    site_id: Mapped[str] = mapped_column(ForeignKey('sites.id', ondelete='CASCADE'), index=True)
    name: Mapped[str] = mapped_column(String(100))
    slug: Mapped[str] = mapped_column(String(100), index=True)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)


class EntryTag(Base):
    __tablename__ = 'entry_tags'
    __table_args__ = (UniqueConstraint('entry_id', 'tag_id', name='uq_entry_tag'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    entry_id: Mapped[str] = mapped_column(ForeignKey('content_entries.id', ondelete='CASCADE'), index=True)
    tag_id: Mapped[str] = mapped_column(ForeignKey('tags.id', ondelete='CASCADE'), index=True)


class EntryComment(Base):
    __tablename__ = 'entry_comments'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    entry_id: Mapped[str] = mapped_column(ForeignKey('content_entries.id', ondelete='CASCADE'), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    body: Mapped[str] = mapped_column(Text)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey('entry_comments.id', ondelete='CASCADE'), nullable=True)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    resolved_by: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MediaFolder(Base):
    __tablename__ = 'media_folders'
    __table_args__ = (UniqueConstraint('site_id', 'parent_id', 'name', name='uq_media_folder'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    site_id: Mapped[str] = mapped_column(ForeignKey('sites.id', ondelete='CASCADE'), index=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey('media_folders.id', ondelete='CASCADE'), nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    created_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MediaAsset(Base):
    __tablename__ = 'media_assets'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    site_id: Mapped[str] = mapped_column(ForeignKey('sites.id', ondelete='CASCADE'), index=True)
    folder_id: Mapped[str | None] = mapped_column(ForeignKey('media_folders.id', ondelete='SET NULL'), nullable=True, index=True)
    filename: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(120), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    public_url: Mapped[str] = mapped_column(String(800))
    checksum_sha256: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    alt_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[MediaStatus] = mapped_column(Enum(MediaStatus), default=MediaStatus.ready, index=True)
    uploaded_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Menu(Base):
    __tablename__ = 'menus'
    __table_args__ = (UniqueConstraint('site_id', 'key', name='uq_site_menu'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    site_id: Mapped[str] = mapped_column(ForeignKey('sites.id', ondelete='CASCADE'), index=True)
    key: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(120))
    locale: Mapped[str] = mapped_column(String(20), default='en-US')
    created_by: Mapped[str] = mapped_column(ForeignKey('users.id'))


class MenuItem(Base):
    __tablename__ = 'menu_items'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    menu_id: Mapped[str] = mapped_column(ForeignKey('menus.id', ondelete='CASCADE'), index=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey('menu_items.id', ondelete='CASCADE'), nullable=True)
    label: Mapped[str] = mapped_column(String(160))
    url: Mapped[str | None] = mapped_column(String(800), nullable=True)
    entry_id: Mapped[str | None] = mapped_column(ForeignKey('content_entries.id', ondelete='SET NULL'), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    open_in_new_tab: Mapped[bool] = mapped_column(Boolean, default=False)


class Redirect(Base):
    __tablename__ = 'redirects'
    __table_args__ = (UniqueConstraint('site_id', 'source_path', name='uq_site_redirect'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    site_id: Mapped[str] = mapped_column(ForeignKey('sites.id', ondelete='CASCADE'), index=True)
    source_path: Mapped[str] = mapped_column(String(500), index=True)
    destination_url: Mapped[str] = mapped_column(String(1000))
    status_code: Mapped[int] = mapped_column(Integer, default=301)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(ForeignKey('users.id'))


class ApiKey(Base):
    __tablename__ = 'api_keys'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    site_id: Mapped[str | None] = mapped_column(ForeignKey('sites.id', ondelete='CASCADE'), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    prefix: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WebhookEndpoint(Base):
    __tablename__ = 'webhook_endpoints'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    site_id: Mapped[str] = mapped_column(ForeignKey('sites.id', ondelete='CASCADE'), index=True)
    name: Mapped[str] = mapped_column(String(120))
    url: Mapped[str] = mapped_column(String(1000))
    secret: Mapped[str] = mapped_column(String(160))
    events: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WebhookDelivery(Base):
    __tablename__ = 'webhook_deliveries'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    webhook_id: Mapped[str] = mapped_column(ForeignKey('webhook_endpoints.id', ondelete='CASCADE'), index=True)
    event_name: Mapped[str] = mapped_column(String(100), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[WebhookDeliveryStatus] = mapped_column(Enum(WebhookDeliveryStatus), default=WebhookDeliveryStatus.pending, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = 'audit_logs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    site_id: Mapped[str | None] = mapped_column(ForeignKey('sites.id', ondelete='SET NULL'), nullable=True, index=True)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    entity_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    request_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


Index('ix_entries_site_status_updated', ContentEntry.site_id, ContentEntry.status, ContentEntry.updated_at)
Index('ix_entries_type_locale_status', ContentEntry.content_type_id, ContentEntry.locale, ContentEntry.status)
Index('ix_audit_site_time', AuditLog.site_id, AuditLog.created_at)
