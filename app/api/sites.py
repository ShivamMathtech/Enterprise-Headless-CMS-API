from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.common import *
from app.models.entities import User, Role, Site, SiteMember, SiteRole, Environment, Locale
from app.core.deps import current_user, require_roles, site_access
from app.services import audit

router = APIRouter(tags=['Sites & Localization'])
ADMIN_SITE_ROLES = {SiteRole.owner, SiteRole.site_admin}


@router.post('/sites', response_model=SiteOut, status_code=201)
def create_site(
    data: SiteCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.super_admin, Role.platform_admin)),
):
    if db.scalar(select(Site).where(Site.key == data.key)):
        raise HTTPException(409, 'Site key already exists')
    site = Site(**data.model_dump(), created_by=user.id)
    db.add(site)
    db.flush()
    db.add(SiteMember(site_id=site.id, user_id=user.id, role=SiteRole.owner))
    db.add(Environment(site_id=site.id, key='development', name='Development', is_production=False))
    db.add(Environment(site_id=site.id, key='production', name='Production', is_production=True))
    db.add(Locale(site_id=site.id, code=data.default_locale, name=data.default_locale, is_default=True))
    audit(db, user.id, 'site.created', 'site', site.id, {'key': site.key}, site.id)
    db.commit()
    db.refresh(site)
    return site


@router.get('/sites', response_model=list[SiteOut])
def list_sites(db: Session = Depends(get_db), user: User = Depends(current_user)):
    if user.role in (Role.super_admin, Role.platform_admin, Role.auditor, Role.support):
        return db.scalars(select(Site).order_by(Site.created_at.desc())).all()
    ids = db.scalars(select(SiteMember.site_id).where(SiteMember.user_id == user.id)).all()
    if not ids:
        return []
    return db.scalars(select(Site).where(Site.id.in_(ids)).order_by(Site.created_at.desc())).all()


@router.get('/sites/{site_id}', response_model=SiteOut)
def get_site(site_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    site_access(site_id, db, user)
    site = db.get(Site, site_id)
    if not site:
        raise HTTPException(404, 'Site not found')
    return site


@router.patch('/sites/{site_id}', response_model=SiteOut)
def update_site(site_id: str, data: SiteUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    site_access(site_id, db, user, ADMIN_SITE_ROLES)
    site = db.get(Site, site_id)
    if not site:
        raise HTTPException(404, 'Site not found')
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(site, key, value)
    audit(db, user.id, 'site.updated', 'site', site.id, data.model_dump(exclude_unset=True), site.id)
    db.commit()
    db.refresh(site)
    return site


@router.post('/sites/{site_id}/members', response_model=SiteMemberOut, status_code=201)
def add_member(site_id: str, data: SiteMemberIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    site_access(site_id, db, user, ADMIN_SITE_ROLES)
    if not db.get(User, data.user_id):
        raise HTTPException(404, 'User not found')
    if db.scalar(select(SiteMember).where(SiteMember.site_id == site_id, SiteMember.user_id == data.user_id)):
        raise HTTPException(409, 'User is already a site member')
    try:
        role = SiteRole(data.role)
    except ValueError:
        raise HTTPException(422, 'Invalid site role')
    member = SiteMember(site_id=site_id, user_id=data.user_id, role=role)
    db.add(member)
    db.flush()
    audit(db, user.id, 'site.member_added', 'site_member', member.id, {'role': role.value}, site_id)
    db.commit()
    db.refresh(member)
    return member


@router.get('/sites/{site_id}/members', response_model=list[SiteMemberOut])
def list_members(site_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    site_access(site_id, db, user)
    return db.scalars(select(SiteMember).where(SiteMember.site_id == site_id).order_by(SiteMember.created_at)).all()


@router.patch('/sites/{site_id}/members/{member_id}', response_model=SiteMemberOut)
def change_member_role(site_id: str, member_id: str, data: SiteMemberIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    site_access(site_id, db, user, ADMIN_SITE_ROLES)
    member = db.get(SiteMember, member_id)
    if not member or member.site_id != site_id:
        raise HTTPException(404, 'Membership not found')
    try:
        member.role = SiteRole(data.role)
    except ValueError:
        raise HTTPException(422, 'Invalid site role')
    audit(db, user.id, 'site.member_role_changed', 'site_member', member.id, {'role': member.role.value}, site_id)
    db.commit()
    db.refresh(member)
    return member


@router.delete('/sites/{site_id}/members/{member_id}', response_model=Message)
def remove_member(site_id: str, member_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    site_access(site_id, db, user, ADMIN_SITE_ROLES)
    member = db.get(SiteMember, member_id)
    if not member or member.site_id != site_id:
        raise HTTPException(404, 'Membership not found')
    if member.role == SiteRole.owner:
        raise HTTPException(409, 'Transfer ownership before removing the owner')
    db.delete(member)
    audit(db, user.id, 'site.member_removed', 'site_member', member_id, site_id=site_id)
    db.commit()
    return Message(message='Member removed')


@router.post('/sites/{site_id}/environments', response_model=EnvironmentOut, status_code=201)
def create_environment(site_id: str, data: EnvironmentIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    site_access(site_id, db, user, ADMIN_SITE_ROLES | {SiteRole.developer})
    if db.scalar(select(Environment).where(Environment.site_id == site_id, Environment.key == data.key)):
        raise HTTPException(409, 'Environment key already exists')
    if data.is_production:
        existing = db.scalar(select(Environment).where(Environment.site_id == site_id, Environment.is_production.is_(True)))
        if existing:
            raise HTTPException(409, 'A production environment already exists')
    env = Environment(site_id=site_id, **data.model_dump())
    db.add(env)
    db.flush()
    audit(db, user.id, 'environment.created', 'environment', env.id, {'key': env.key}, site_id)
    db.commit()
    db.refresh(env)
    return env


@router.get('/sites/{site_id}/environments', response_model=list[EnvironmentOut])
def list_environments(site_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    site_access(site_id, db, user)
    return db.scalars(select(Environment).where(Environment.site_id == site_id).order_by(Environment.is_production, Environment.name)).all()


@router.post('/sites/{site_id}/locales', response_model=LocaleOut, status_code=201)
def create_locale(site_id: str, data: LocaleIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    site_access(site_id, db, user, ADMIN_SITE_ROLES | {SiteRole.content_manager})
    if db.scalar(select(Locale).where(Locale.site_id == site_id, Locale.code == data.code)):
        raise HTTPException(409, 'Locale already exists')
    if data.is_default:
        for row in db.scalars(select(Locale).where(Locale.site_id == site_id)).all():
            row.is_default = False
    locale = Locale(site_id=site_id, **data.model_dump())
    db.add(locale)
    audit(db, user.id, 'locale.created', 'locale', locale.id, {'code': locale.code}, site_id)
    db.commit()
    db.refresh(locale)
    return locale


@router.get('/sites/{site_id}/locales', response_model=list[LocaleOut])
def list_locales(site_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    site_access(site_id, db, user)
    return db.scalars(select(Locale).where(Locale.site_id == site_id).order_by(Locale.is_default.desc(), Locale.code)).all()
