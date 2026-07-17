from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Message(BaseModel):
    message: str


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = 'bearer'


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=150)
    password: str = Field(min_length=10, max_length=128)
    role: str = 'user'


class UserOut(ORMModel):
    id: str
    email: EmailStr
    full_name: str
    role: str
    is_active: bool
    created_at: datetime


class UserStatusIn(BaseModel):
    is_active: bool


class SiteCreate(BaseModel):
    key: str = Field(pattern=r'^[a-z0-9][a-z0-9_-]{1,78}[a-z0-9]$')
    name: str = Field(min_length=2, max_length=160)
    description: str | None = None
    default_locale: str = 'en-US'
    timezone: str = 'UTC'
    domain: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)


class SiteUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    default_locale: str | None = None
    timezone: str | None = None
    domain: str | None = None
    settings: dict[str, Any] | None = None
    is_active: bool | None = None


class SiteOut(ORMModel):
    id: str
    key: str
    name: str
    description: str | None
    default_locale: str
    timezone: str
    domain: str | None
    settings: dict[str, Any]
    is_active: bool
    created_at: datetime


class SiteMemberIn(BaseModel):
    user_id: str
    role: str


class SiteMemberOut(ORMModel):
    id: str
    site_id: str
    user_id: str
    role: str
    created_at: datetime


class EnvironmentIn(BaseModel):
    key: str = Field(pattern=r'^[a-z0-9_-]+$')
    name: str
    is_production: bool = False


class EnvironmentOut(ORMModel):
    id: str
    site_id: str
    key: str
    name: str
    is_production: bool
    is_active: bool
    created_at: datetime


class LocaleIn(BaseModel):
    code: str = Field(min_length=2, max_length=20)
    name: str
    is_default: bool = False


class LocaleOut(ORMModel):
    id: str
    site_id: str
    code: str
    name: str
    is_default: bool
    is_active: bool


class ContentTypeCreate(BaseModel):
    site_id: str
    key: str = Field(pattern=r'^[a-z][a-z0-9_-]{1,78}$')
    name: str
    description: str | None = None
    schema_definition: dict[str, Any]
    display_field: str = 'title'
    is_singleton: bool = False


class ContentTypeUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    schema_definition: dict[str, Any] | None = None
    display_field: str | None = None
    is_singleton: bool | None = None


class ContentTypeOut(ORMModel):
    id: str
    site_id: str
    key: str
    name: str
    description: str | None
    schema_definition: dict[str, Any]
    display_field: str
    is_singleton: bool
    is_published: bool
    version: int
    created_at: datetime
    updated_at: datetime


class EntryCreate(BaseModel):
    site_id: str
    environment_id: str
    content_type_id: str
    locale: str
    title: str = Field(min_length=1, max_length=250)
    slug: str = Field(pattern=r'^[a-z0-9][a-z0-9\-_/]*$')
    data: dict[str, Any]
    seo: dict[str, Any] = Field(default_factory=dict)
    tag_ids: list[str] = Field(default_factory=list)


class EntryUpdate(BaseModel):
    title: str | None = None
    slug: str | None = None
    data: dict[str, Any] | None = None
    seo: dict[str, Any] | None = None
    tag_ids: list[str] | None = None
    note: str | None = None
    expected_version: int | None = None


class EntryOut(ORMModel):
    id: str
    site_id: str
    environment_id: str
    content_type_id: str
    locale: str
    title: str
    slug: str
    status: str
    workflow_stage: str
    data: dict[str, Any]
    seo: dict[str, Any]
    version: int
    created_by: str
    updated_by: str
    approved_by: str | None
    published_by: str | None
    published_at: datetime | None
    scheduled_for: datetime | None
    created_at: datetime
    updated_at: datetime


class ReviewDecisionIn(BaseModel):
    note: str | None = None


class ScheduleIn(BaseModel):
    publish_at: datetime


class PreviewTokenOut(BaseModel):
    token: str
    expires_in_minutes: int


class RevisionOut(ORMModel):
    id: str
    entry_id: str
    version: int
    snapshot: dict[str, Any]
    note: str | None
    created_by: str
    created_at: datetime


class CommentIn(BaseModel):
    body: str = Field(min_length=1)
    parent_id: str | None = None


class CommentOut(ORMModel):
    id: str
    entry_id: str
    author_id: str
    body: str
    parent_id: str | None
    is_resolved: bool
    resolved_by: str | None
    created_at: datetime


class TagIn(BaseModel):
    site_id: str
    name: str
    slug: str = Field(pattern=r'^[a-z0-9-]+$')
    color: str | None = None


class TagOut(ORMModel):
    id: str
    site_id: str
    name: str
    slug: str
    color: str | None


class MediaFolderIn(BaseModel):
    site_id: str
    name: str
    parent_id: str | None = None


class MediaFolderOut(ORMModel):
    id: str
    site_id: str
    parent_id: str | None
    name: str
    created_by: str
    created_at: datetime


class MediaUpdate(BaseModel):
    title: str | None = None
    alt_text: str | None = None
    folder_id: str | None = None
    metadata_json: dict[str, Any] | None = None


class MediaOut(ORMModel):
    id: str
    site_id: str
    folder_id: str | None
    filename: str
    original_filename: str
    mime_type: str
    size_bytes: int
    public_url: str
    checksum_sha256: str
    title: str | None
    alt_text: str | None
    metadata_json: dict[str, Any]
    status: str
    uploaded_by: str
    created_at: datetime


class MenuIn(BaseModel):
    site_id: str
    key: str = Field(pattern=r'^[a-z0-9_-]+$')
    name: str
    locale: str = 'en-US'


class MenuOut(ORMModel):
    id: str
    site_id: str
    key: str
    name: str
    locale: str


class MenuItemIn(BaseModel):
    parent_id: str | None = None
    label: str
    url: str | None = None
    entry_id: str | None = None
    position: int = 0
    is_visible: bool = True
    open_in_new_tab: bool = False


class MenuItemOut(ORMModel):
    id: str
    menu_id: str
    parent_id: str | None
    label: str
    url: str | None
    entry_id: str | None
    position: int
    is_visible: bool
    open_in_new_tab: bool


class ReorderIn(BaseModel):
    item_ids: list[str]


class RedirectIn(BaseModel):
    site_id: str
    source_path: str
    destination_url: str
    status_code: int = 301

    @field_validator('status_code')
    @classmethod
    def valid_redirect(cls, value):
        if value not in (301, 302, 307, 308):
            raise ValueError('Unsupported redirect status')
        return value


class RedirectOut(ORMModel):
    id: str
    site_id: str
    source_path: str
    destination_url: str
    status_code: int
    is_active: bool


class ApiKeyIn(BaseModel):
    site_id: str | None = None
    name: str
    scopes: list[str] = Field(default_factory=lambda: ['delivery:read'])
    expires_at: datetime | None = None


class ApiKeyOut(ORMModel):
    id: str
    site_id: str | None
    name: str
    prefix: str
    scopes: list[str]
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
    secret: str | None = None


class WebhookIn(BaseModel):
    site_id: str
    name: str
    url: str
    events: list[str]


class WebhookUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    events: list[str] | None = None
    is_active: bool | None = None


class WebhookOut(ORMModel):
    id: str
    site_id: str
    name: str
    url: str
    events: list[str]
    is_active: bool
    created_at: datetime


class WebhookDeliveryOut(ORMModel):
    id: str
    webhook_id: str
    event_name: str
    payload: dict[str, Any]
    status: str
    attempt_count: int
    response_code: int | None
    response_body: str | None
    created_at: datetime


class AuditOut(ORMModel):
    id: str
    site_id: str | None
    actor_id: str | None
    action: str
    entity_type: str
    entity_id: str | None
    details: dict[str, Any]
    request_id: str | None
    created_at: datetime


class PublicEntry(BaseModel):
    id: str
    content_type: str
    locale: str
    title: str
    slug: str
    data: dict[str, Any]
    seo: dict[str, Any]
    published_at: datetime | None
    updated_at: datetime
