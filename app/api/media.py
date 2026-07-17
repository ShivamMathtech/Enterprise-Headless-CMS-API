import hashlib
import os
import re
import secrets
from pathlib import Path
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.core.config import get_settings
from app.core.deps import current_user, site_access
from app.models.entities import User, MediaAsset, MediaFolder, MediaStatus, SiteRole
from app.schemas.common import *
from app.services import audit, enqueue_webhooks

router = APIRouter(prefix='/media', tags=['Media Library'])
settings = get_settings()
MEDIA_ROLES = {SiteRole.owner, SiteRole.site_admin, SiteRole.content_manager, SiteRole.media_manager, SiteRole.editor}


def _safe_filename(name: str) -> str:
    base = os.path.basename(name or 'upload.bin')
    stem, ext = os.path.splitext(base)
    stem = re.sub(r'[^A-Za-z0-9._-]+', '-', stem).strip('-') or 'asset'
    ext = re.sub(r'[^A-Za-z0-9.]', '', ext)[:15]
    return f'{stem}-{secrets.token_hex(6)}{ext.lower()}'


@router.post('/folders', response_model=MediaFolderOut, status_code=201)
def create_folder(data: MediaFolderIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    site_access(data.site_id, db, user, MEDIA_ROLES)
    if data.parent_id:
        parent = db.get(MediaFolder, data.parent_id)
        if not parent or parent.site_id != data.site_id:
            raise HTTPException(422, 'Invalid parent folder')
    folder = MediaFolder(site_id=data.site_id, name=data.name, parent_id=data.parent_id, created_by=user.id)
    db.add(folder)
    db.flush()
    audit(db, user.id, 'media.folder_created', 'media_folder', folder.id, site_id=data.site_id)
    db.commit()
    db.refresh(folder)
    return folder


@router.get('/folders', response_model=list[MediaFolderOut])
def list_folders(site_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    site_access(site_id, db, user)
    return db.scalars(select(MediaFolder).where(MediaFolder.site_id == site_id).order_by(MediaFolder.name)).all()


@router.delete('/folders/{folder_id}', response_model=Message)
def delete_folder(folder_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    folder = db.get(MediaFolder, folder_id)
    if not folder:
        raise HTTPException(404, 'Folder not found')
    site_access(folder.site_id, db, user, MEDIA_ROLES)
    if db.scalar(select(MediaAsset).where(MediaAsset.folder_id == folder_id)):
        raise HTTPException(409, 'Move or delete assets before deleting this folder')
    if db.scalar(select(MediaFolder).where(MediaFolder.parent_id == folder_id)):
        raise HTTPException(409, 'Delete child folders first')
    db.delete(folder)
    audit(db, user.id, 'media.folder_deleted', 'media_folder', folder_id, site_id=folder.site_id)
    db.commit()
    return Message(message='Folder deleted')


@router.post('/upload', response_model=MediaOut, status_code=201)
async def upload_asset(
    site_id: str = Form(...),
    folder_id: str | None = Form(None),
    title: str | None = Form(None),
    alt_text: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    site_access(site_id, db, user, MEDIA_ROLES)
    if folder_id:
        folder = db.get(MediaFolder, folder_id)
        if not folder or folder.site_id != site_id:
            raise HTTPException(422, 'Invalid folder')
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(413, f'File exceeds {settings.max_upload_bytes} bytes')
    if not content:
        raise HTTPException(422, 'Empty files are not allowed')
    safe_name = _safe_filename(file.filename or 'upload.bin')
    site_dir = Path(settings.upload_dir) / site_id
    site_dir.mkdir(parents=True, exist_ok=True)
    path = site_dir / safe_name
    path.write_bytes(content)
    storage_key = f'{site_id}/{safe_name}'
    url = f'{settings.public_media_base_url.rstrip("/")}/{storage_key}'
    asset = MediaAsset(
        site_id=site_id,
        folder_id=folder_id,
        filename=safe_name,
        original_filename=file.filename or safe_name,
        mime_type=file.content_type or 'application/octet-stream',
        size_bytes=len(content),
        storage_key=storage_key,
        public_url=url,
        checksum_sha256=hashlib.sha256(content).hexdigest(),
        title=title,
        alt_text=alt_text,
        metadata_json={},
        status=MediaStatus.ready,
        uploaded_by=user.id,
    )
    db.add(asset)
    db.flush()
    audit(db, user.id, 'media.uploaded', 'media_asset', asset.id, {'mime_type': asset.mime_type, 'size_bytes': asset.size_bytes}, site_id)
    enqueue_webhooks(db, site_id, 'media.created', {'asset_id': asset.id, 'url': asset.public_url})
    db.commit()
    db.refresh(asset)
    return asset


@router.get('', response_model=list[MediaOut])
def list_assets(
    site_id: str,
    folder_id: str | None = None,
    mime_prefix: str | None = None,
    search: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    site_access(site_id, db, user)
    stmt = select(MediaAsset).where(MediaAsset.site_id == site_id, MediaAsset.status != MediaStatus.archived)
    if folder_id:
        stmt = stmt.where(MediaAsset.folder_id == folder_id)
    if mime_prefix:
        stmt = stmt.where(MediaAsset.mime_type.like(f'{mime_prefix}%'))
    if search:
        stmt = stmt.where(MediaAsset.original_filename.ilike(f'%{search}%'))
    return db.scalars(stmt.order_by(MediaAsset.created_at.desc()).offset(offset).limit(limit)).all()


@router.get('/{asset_id}', response_model=MediaOut)
def get_asset(asset_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    asset = db.get(MediaAsset, asset_id)
    if not asset:
        raise HTTPException(404, 'Asset not found')
    site_access(asset.site_id, db, user)
    return asset


@router.patch('/{asset_id}', response_model=MediaOut)
def update_asset(asset_id: str, data: MediaUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    asset = db.get(MediaAsset, asset_id)
    if not asset:
        raise HTTPException(404, 'Asset not found')
    site_access(asset.site_id, db, user, MEDIA_ROLES)
    values = data.model_dump(exclude_unset=True)
    if values.get('folder_id'):
        folder = db.get(MediaFolder, values['folder_id'])
        if not folder or folder.site_id != asset.site_id:
            raise HTTPException(422, 'Invalid folder')
    for key, value in values.items():
        setattr(asset, key, value)
    audit(db, user.id, 'media.updated', 'media_asset', asset.id, values, asset.site_id)
    db.commit()
    db.refresh(asset)
    return asset


@router.delete('/{asset_id}', response_model=Message)
def archive_asset(asset_id: str, hard_delete: bool = False, db: Session = Depends(get_db), user: User = Depends(current_user)):
    asset = db.get(MediaAsset, asset_id)
    if not asset:
        raise HTTPException(404, 'Asset not found')
    site_access(asset.site_id, db, user, MEDIA_ROLES)
    if hard_delete:
        path = Path(settings.upload_dir) / asset.storage_key
        if path.exists():
            path.unlink()
        db.delete(asset)
        action = 'media.deleted'
    else:
        asset.status = MediaStatus.archived
        action = 'media.archived'
    audit(db, user.id, action, 'media_asset', asset_id, site_id=asset.site_id)
    enqueue_webhooks(db, asset.site_id, action, {'asset_id': asset_id})
    db.commit()
    return Message(message='Asset deleted' if hard_delete else 'Asset archived')
