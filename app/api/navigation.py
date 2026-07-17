from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.core.deps import current_user, site_access
from app.models.entities import User, Tag, Menu, MenuItem, Redirect, ContentEntry, SiteRole
from app.schemas.common import *
from app.services import audit

router = APIRouter(tags=['Taxonomy, Navigation & Redirects'])
MANAGE = {SiteRole.owner, SiteRole.site_admin, SiteRole.content_manager, SiteRole.editor, SiteRole.seo_manager}


@router.post('/tags', response_model=TagOut, status_code=201)
def create_tag(data: TagIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    site_access(data.site_id, db, user, MANAGE)
    if db.scalar(select(Tag).where(Tag.site_id == data.site_id, Tag.slug == data.slug)):
        raise HTTPException(409, 'Tag slug already exists')
    tag = Tag(**data.model_dump())
    db.add(tag)
    db.flush()
    audit(db, user.id, 'tag.created', 'tag', tag.id, {'slug': tag.slug}, data.site_id)
    db.commit()
    db.refresh(tag)
    return tag


@router.get('/tags', response_model=list[TagOut])
def list_tags(site_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    site_access(site_id, db, user)
    return db.scalars(select(Tag).where(Tag.site_id == site_id).order_by(Tag.name)).all()


@router.patch('/tags/{tag_id}', response_model=TagOut)
def update_tag(tag_id: str, data: TagIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    tag = db.get(Tag, tag_id)
    if not tag:
        raise HTTPException(404, 'Tag not found')
    site_access(tag.site_id, db, user, MANAGE)
    if data.site_id != tag.site_id:
        raise HTTPException(422, 'Cannot move tag to another site')
    tag.name = data.name
    tag.slug = data.slug
    tag.color = data.color
    audit(db, user.id, 'tag.updated', 'tag', tag.id, site_id=tag.site_id)
    db.commit()
    db.refresh(tag)
    return tag


@router.delete('/tags/{tag_id}', response_model=Message)
def delete_tag(tag_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    tag = db.get(Tag, tag_id)
    if not tag:
        raise HTTPException(404, 'Tag not found')
    site_access(tag.site_id, db, user, MANAGE)
    db.delete(tag)
    audit(db, user.id, 'tag.deleted', 'tag', tag_id, site_id=tag.site_id)
    db.commit()
    return Message(message='Tag deleted')


@router.post('/menus', response_model=MenuOut, status_code=201)
def create_menu(data: MenuIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    site_access(data.site_id, db, user, MANAGE)
    if db.scalar(select(Menu).where(Menu.site_id == data.site_id, Menu.key == data.key)):
        raise HTTPException(409, 'Menu key already exists')
    menu = Menu(**data.model_dump(), created_by=user.id)
    db.add(menu)
    db.flush()
    audit(db, user.id, 'menu.created', 'menu', menu.id, {'key': menu.key}, data.site_id)
    db.commit()
    db.refresh(menu)
    return menu


@router.get('/menus', response_model=list[MenuOut])
def list_menus(site_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    site_access(site_id, db, user)
    return db.scalars(select(Menu).where(Menu.site_id == site_id).order_by(Menu.name)).all()


@router.post('/menus/{menu_id}/items', response_model=MenuItemOut, status_code=201)
def add_menu_item(menu_id: str, data: MenuItemIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    menu = db.get(Menu, menu_id)
    if not menu:
        raise HTTPException(404, 'Menu not found')
    site_access(menu.site_id, db, user, MANAGE)
    if data.parent_id:
        parent = db.get(MenuItem, data.parent_id)
        if not parent or parent.menu_id != menu_id:
            raise HTTPException(422, 'Invalid parent item')
    if data.entry_id:
        entry = db.get(ContentEntry, data.entry_id)
        if not entry or entry.site_id != menu.site_id:
            raise HTTPException(422, 'Invalid content entry')
    if not data.url and not data.entry_id:
        raise HTTPException(422, 'Provide either url or entry_id')
    item = MenuItem(menu_id=menu_id, **data.model_dump())
    db.add(item)
    db.flush()
    audit(db, user.id, 'menu.item_added', 'menu_item', item.id, {'menu_id': menu_id}, menu.site_id)
    db.commit()
    db.refresh(item)
    return item


@router.get('/menus/{menu_id}/items', response_model=list[MenuItemOut])
def list_menu_items(menu_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    menu = db.get(Menu, menu_id)
    if not menu:
        raise HTTPException(404, 'Menu not found')
    site_access(menu.site_id, db, user)
    return db.scalars(select(MenuItem).where(MenuItem.menu_id == menu_id).order_by(MenuItem.position, MenuItem.label)).all()


@router.patch('/menus/{menu_id}/items/{item_id}', response_model=MenuItemOut)
def update_menu_item(menu_id: str, item_id: str, data: MenuItemIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    menu = db.get(Menu, menu_id)
    item = db.get(MenuItem, item_id)
    if not menu or not item or item.menu_id != menu_id:
        raise HTTPException(404, 'Menu item not found')
    site_access(menu.site_id, db, user, MANAGE)
    for key, value in data.model_dump().items():
        setattr(item, key, value)
    audit(db, user.id, 'menu.item_updated', 'menu_item', item.id, site_id=menu.site_id)
    db.commit()
    db.refresh(item)
    return item


@router.post('/menus/{menu_id}/reorder', response_model=list[MenuItemOut])
def reorder_menu(menu_id: str, data: ReorderIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    menu = db.get(Menu, menu_id)
    if not menu:
        raise HTTPException(404, 'Menu not found')
    site_access(menu.site_id, db, user, MANAGE)
    items = db.scalars(select(MenuItem).where(MenuItem.menu_id == menu_id, MenuItem.id.in_(data.item_ids))).all()
    if len(items) != len(set(data.item_ids)):
        raise HTTPException(422, 'One or more menu items are invalid')
    by_id = {item.id: item for item in items}
    for position, item_id in enumerate(data.item_ids):
        by_id[item_id].position = position
    audit(db, user.id, 'menu.reordered', 'menu', menu.id, {'item_ids': data.item_ids}, menu.site_id)
    db.commit()
    return db.scalars(select(MenuItem).where(MenuItem.menu_id == menu_id).order_by(MenuItem.position)).all()


@router.delete('/menus/{menu_id}/items/{item_id}', response_model=Message)
def delete_menu_item(menu_id: str, item_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    menu = db.get(Menu, menu_id)
    item = db.get(MenuItem, item_id)
    if not menu or not item or item.menu_id != menu_id:
        raise HTTPException(404, 'Menu item not found')
    site_access(menu.site_id, db, user, MANAGE)
    db.delete(item)
    audit(db, user.id, 'menu.item_deleted', 'menu_item', item_id, site_id=menu.site_id)
    db.commit()
    return Message(message='Menu item deleted')


@router.post('/redirects', response_model=RedirectOut, status_code=201)
def create_redirect(data: RedirectIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    site_access(data.site_id, db, user, MANAGE)
    if db.scalar(select(Redirect).where(Redirect.site_id == data.site_id, Redirect.source_path == data.source_path)):
        raise HTTPException(409, 'Redirect source already exists')
    redirect = Redirect(**data.model_dump(), created_by=user.id)
    db.add(redirect)
    db.flush()
    audit(db, user.id, 'redirect.created', 'redirect', redirect.id, site_id=data.site_id)
    db.commit()
    db.refresh(redirect)
    return redirect


@router.get('/redirects', response_model=list[RedirectOut])
def list_redirects(site_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    site_access(site_id, db, user)
    return db.scalars(select(Redirect).where(Redirect.site_id == site_id).order_by(Redirect.source_path)).all()


@router.patch('/redirects/{redirect_id}', response_model=RedirectOut)
def update_redirect(redirect_id: str, data: RedirectIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    redirect = db.get(Redirect, redirect_id)
    if not redirect:
        raise HTTPException(404, 'Redirect not found')
    site_access(redirect.site_id, db, user, MANAGE)
    if data.site_id != redirect.site_id:
        raise HTTPException(422, 'Cannot move redirect to another site')
    redirect.source_path = data.source_path
    redirect.destination_url = data.destination_url
    redirect.status_code = data.status_code
    audit(db, user.id, 'redirect.updated', 'redirect', redirect.id, site_id=redirect.site_id)
    db.commit()
    db.refresh(redirect)
    return redirect


@router.delete('/redirects/{redirect_id}', response_model=Message)
def delete_redirect(redirect_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    redirect = db.get(Redirect, redirect_id)
    if not redirect:
        raise HTTPException(404, 'Redirect not found')
    site_access(redirect.site_id, db, user, MANAGE)
    db.delete(redirect)
    audit(db, user.id, 'redirect.deleted', 'redirect', redirect_id, site_id=redirect.site_id)
    db.commit()
    return Message(message='Redirect deleted')
