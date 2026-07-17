from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.core.deps import require_delivery_key
from app.core.security import decode_token
from app.models.entities import (
    ApiKey, Site, Environment, ContentType, ContentEntry, EntryStatus,
    Menu, MenuItem, Redirect
)
from app.schemas.common import PublicEntry

router = APIRouter(tags=['Content Delivery & Preview'])


def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _site(db: Session, site_key: str) -> Site:
    site = db.scalar(select(Site).where(Site.key == site_key, Site.is_active.is_(True)))
    if not site:
        raise HTTPException(404, 'Site not found')
    return site


def _validate_key(key: ApiKey | None, site_id: str, db: Session):
    if not key:
        return
    if key.site_id and key.site_id != site_id:
        raise HTTPException(403, 'API key is not valid for this site')
    if key.expires_at and _aware(key.expires_at) <= datetime.now(timezone.utc):
        raise HTTPException(401, 'API key expired')
    if 'delivery:read' not in (key.scopes or []) and '*' not in (key.scopes or []):
        raise HTTPException(403, 'API key lacks delivery:read scope')
    key.last_used_at = datetime.now(timezone.utc)
    db.commit()


def _public_entry(entry: ContentEntry, content_type: ContentType) -> PublicEntry:
    return PublicEntry(
        id=entry.id,
        content_type=content_type.key,
        locale=entry.locale,
        title=entry.title,
        slug=entry.slug,
        data=entry.data,
        seo=entry.seo,
        published_at=entry.published_at,
        updated_at=entry.updated_at,
    )


@router.get('/delivery/sites/{site_key}/entries', response_model=list[PublicEntry])
def delivery_entries(
    site_key: str,
    content_type: str | None = None,
    locale: str | None = None,
    environment: str = 'production',
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    key: ApiKey | None = Depends(require_delivery_key),
):
    site = _site(db, site_key)
    _validate_key(key, site.id, db)
    env = db.scalar(select(Environment).where(Environment.site_id == site.id, Environment.key == environment, Environment.is_active.is_(True)))
    if not env:
        raise HTTPException(404, 'Environment not found')
    stmt = select(ContentEntry, ContentType).join(ContentType, ContentEntry.content_type_id == ContentType.id).where(
        ContentEntry.site_id == site.id,
        ContentEntry.environment_id == env.id,
        ContentEntry.status == EntryStatus.published,
    )
    if content_type:
        stmt = stmt.where(ContentType.key == content_type)
    if locale:
        stmt = stmt.where(ContentEntry.locale == locale)
    else:
        stmt = stmt.where(ContentEntry.locale == site.default_locale)
    rows = db.execute(stmt.order_by(ContentEntry.published_at.desc()).offset(offset).limit(limit)).all()
    return [_public_entry(entry, ctype) for entry, ctype in rows]


@router.get('/delivery/sites/{site_key}/entries/{content_type_key}/{slug:path}', response_model=PublicEntry)
def delivery_entry(
    site_key: str,
    content_type_key: str,
    slug: str,
    locale: str | None = None,
    environment: str = 'production',
    db: Session = Depends(get_db),
    key: ApiKey | None = Depends(require_delivery_key),
):
    site = _site(db, site_key)
    _validate_key(key, site.id, db)
    env = db.scalar(select(Environment).where(Environment.site_id == site.id, Environment.key == environment, Environment.is_active.is_(True)))
    ctype = db.scalar(select(ContentType).where(ContentType.site_id == site.id, ContentType.key == content_type_key))
    if not env or not ctype:
        raise HTTPException(404, 'Content scope not found')
    entry = db.scalar(select(ContentEntry).where(
        ContentEntry.environment_id == env.id,
        ContentEntry.content_type_id == ctype.id,
        ContentEntry.locale == (locale or site.default_locale),
        ContentEntry.slug == slug,
        ContentEntry.status == EntryStatus.published,
    ))
    if not entry:
        raise HTTPException(404, 'Published entry not found')
    return _public_entry(entry, ctype)


@router.get('/delivery/sites/{site_key}/menus/{menu_key}', response_model=dict)
def delivery_menu(
    site_key: str,
    menu_key: str,
    locale: str | None = None,
    db: Session = Depends(get_db),
    key: ApiKey | None = Depends(require_delivery_key),
):
    site = _site(db, site_key)
    _validate_key(key, site.id, db)
    menu = db.scalar(select(Menu).where(Menu.site_id == site.id, Menu.key == menu_key, Menu.locale == (locale or site.default_locale)))
    if not menu:
        raise HTTPException(404, 'Menu not found')
    items = db.scalars(select(MenuItem).where(MenuItem.menu_id == menu.id, MenuItem.is_visible.is_(True)).order_by(MenuItem.position)).all()
    return {
        'id': menu.id,
        'key': menu.key,
        'name': menu.name,
        'locale': menu.locale,
        'items': [
            {
                'id': item.id,
                'parent_id': item.parent_id,
                'label': item.label,
                'url': item.url,
                'entry_id': item.entry_id,
                'position': item.position,
                'open_in_new_tab': item.open_in_new_tab,
            }
            for item in items
        ],
    }


@router.get('/delivery/sites/{site_key}/redirects/resolve', response_model=dict)
def resolve_redirect(
    site_key: str,
    path: str,
    db: Session = Depends(get_db),
    key: ApiKey | None = Depends(require_delivery_key),
):
    site = _site(db, site_key)
    _validate_key(key, site.id, db)
    redirect = db.scalar(select(Redirect).where(
        Redirect.site_id == site.id,
        Redirect.source_path == path,
        Redirect.is_active.is_(True),
    ))
    if not redirect:
        raise HTTPException(404, 'Redirect not found')
    return {'destination_url': redirect.destination_url, 'status_code': redirect.status_code}


@router.get('/preview/{token}', response_model=PublicEntry)
def preview_entry(token: str, db: Session = Depends(get_db)):
    try:
        payload = decode_token(token)
        if payload.get('type') != 'preview':
            raise ValueError()
    except Exception:
        raise HTTPException(401, 'Invalid or expired preview token')
    entry = db.get(ContentEntry, payload.get('sub'))
    if not entry:
        raise HTTPException(404, 'Entry not found')
    content_type = db.get(ContentType, entry.content_type_id)
    return _public_entry(entry, content_type)
