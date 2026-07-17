from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.common import *
from app.models.entities import User, ContentType, SiteRole
from app.core.deps import current_user, site_access
from app.services import audit

router = APIRouter(prefix='/content-types', tags=['Content Types'])
MANAGE_TYPES = {SiteRole.owner, SiteRole.site_admin, SiteRole.content_manager, SiteRole.developer}


def _validate_schema(schema: dict):
    fields = schema.get('fields')
    if not isinstance(fields, list):
        raise HTTPException(422, 'schema_definition.fields must be a list')
    keys = []
    allowed = {'text','rich_text','number','integer','boolean','date','datetime','email','url','json','object','list','array','media','media_list','reference','reference_list','enum'}
    for field in fields:
        if not isinstance(field, dict) or not field.get('key') or not field.get('type'):
            raise HTTPException(422, 'Every field requires key and type')
        if field['key'] in keys:
            raise HTTPException(422, f'Duplicate field key: {field["key"]}')
        if field['type'] not in allowed:
            raise HTTPException(422, f'Unsupported field type: {field["type"]}')
        keys.append(field['key'])


@router.post('', response_model=ContentTypeOut, status_code=201)
def create_content_type(data: ContentTypeCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    site_access(data.site_id, db, user, MANAGE_TYPES)
    if db.scalar(select(ContentType).where(ContentType.site_id == data.site_id, ContentType.key == data.key)):
        raise HTTPException(409, 'Content type key already exists')
    _validate_schema(data.schema_definition)
    content_type = ContentType(**data.model_dump(), created_by=user.id)
    db.add(content_type)
    db.flush()
    audit(db, user.id, 'content_type.created', 'content_type', content_type.id, {'key': content_type.key}, data.site_id)
    db.commit()
    db.refresh(content_type)
    return content_type


@router.get('', response_model=list[ContentTypeOut])
def list_content_types(site_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    site_access(site_id, db, user)
    return db.scalars(select(ContentType).where(ContentType.site_id == site_id).order_by(ContentType.name)).all()


@router.get('/{content_type_id}', response_model=ContentTypeOut)
def get_content_type(content_type_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = db.get(ContentType, content_type_id)
    if not row:
        raise HTTPException(404, 'Content type not found')
    site_access(row.site_id, db, user)
    return row


@router.patch('/{content_type_id}', response_model=ContentTypeOut)
def update_content_type(content_type_id: str, data: ContentTypeUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = db.get(ContentType, content_type_id)
    if not row:
        raise HTTPException(404, 'Content type not found')
    site_access(row.site_id, db, user, MANAGE_TYPES)
    values = data.model_dump(exclude_unset=True)
    if 'schema_definition' in values:
        _validate_schema(values['schema_definition'])
        row.version += 1
        row.is_published = False
    for key, value in values.items():
        setattr(row, key, value)
    audit(db, user.id, 'content_type.updated', 'content_type', row.id, {'version': row.version}, row.site_id)
    db.commit()
    db.refresh(row)
    return row


@router.post('/{content_type_id}/publish', response_model=ContentTypeOut)
def publish_content_type(content_type_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = db.get(ContentType, content_type_id)
    if not row:
        raise HTTPException(404, 'Content type not found')
    site_access(row.site_id, db, user, MANAGE_TYPES)
    _validate_schema(row.schema_definition)
    row.is_published = True
    audit(db, user.id, 'content_type.published', 'content_type', row.id, {'version': row.version}, row.site_id)
    db.commit()
    db.refresh(row)
    return row


@router.post('/{content_type_id}/duplicate', response_model=ContentTypeOut, status_code=201)
def duplicate_content_type(content_type_id: str, new_key: str, new_name: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = db.get(ContentType, content_type_id)
    if not row:
        raise HTTPException(404, 'Content type not found')
    site_access(row.site_id, db, user, MANAGE_TYPES)
    if db.scalar(select(ContentType).where(ContentType.site_id == row.site_id, ContentType.key == new_key)):
        raise HTTPException(409, 'Content type key already exists')
    clone = ContentType(
        site_id=row.site_id,
        key=new_key,
        name=new_name,
        description=row.description,
        schema_definition=row.schema_definition,
        display_field=row.display_field,
        is_singleton=row.is_singleton,
        created_by=user.id,
    )
    db.add(clone)
    db.flush()
    audit(db, user.id, 'content_type.duplicated', 'content_type', clone.id, {'source_id': row.id}, row.site_id)
    db.commit()
    db.refresh(clone)
    return clone


@router.delete('/{content_type_id}', response_model=Message)
def archive_content_type(content_type_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = db.get(ContentType, content_type_id)
    if not row:
        raise HTTPException(404, 'Content type not found')
    site_access(row.site_id, db, user, MANAGE_TYPES)
    row.is_published = False
    audit(db, user.id, 'content_type.archived', 'content_type', row.id, site_id=row.site_id)
    db.commit()
    return Message(message='Content type archived')
