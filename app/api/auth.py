from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.common import *
from app.models.entities import User, RefreshToken, Role
from app.core.security import *
from app.core.deps import current_user, require_roles
from app.services import audit

router = APIRouter(prefix='/auth', tags=['Authentication'])


def _as_aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


@router.post('/login', response_model=TokenOut)
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    now = datetime.now(timezone.utc)
    if user and user.locked_until and _as_aware(user.locked_until) > now:
        raise HTTPException(423, 'Account temporarily locked')
    if not user or not verify_password(data.password, user.password_hash):
        if user:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= 5:
                user.locked_until = now + timedelta(minutes=15)
            db.commit()
        raise HTTPException(401, 'Invalid credentials')
    if not user.is_active:
        raise HTTPException(403, 'Account disabled')
    user.failed_login_attempts = 0
    user.locked_until = None
    access = create_access_token(user.id, user.role.value)
    refresh, payload = create_refresh_token(user.id)
    expiry = payload['exp'] if isinstance(payload['exp'], datetime) else datetime.fromtimestamp(payload['exp'], timezone.utc)
    db.add(RefreshToken(user_id=user.id, token_hash=token_hash(refresh), family_id=payload['family'], expires_at=expiry))
    audit(db, user.id, 'auth.login', 'user', user.id)
    db.commit()
    return TokenOut(access_token=access, refresh_token=refresh)


@router.post('/refresh', response_model=TokenOut)
def refresh(data: RefreshIn, db: Session = Depends(get_db)):
    try:
        payload = decode_token(data.refresh_token)
        if payload.get('type') != 'refresh':
            raise ValueError()
    except Exception:
        raise HTTPException(401, 'Invalid refresh token')
    current_hash = token_hash(data.refresh_token)
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == current_hash))
    if not row or row.revoked_at:
        family = payload.get('family')
        if family:
            db.execute(update(RefreshToken).where(
                RefreshToken.family_id == family,
                RefreshToken.revoked_at.is_(None),
            ).values(revoked_at=datetime.now(timezone.utc)))
            db.commit()
        raise HTTPException(401, 'Refresh token reuse detected')
    user = db.get(User, row.user_id)
    if not user or not user.is_active:
        raise HTTPException(401, 'Account unavailable')
    new_refresh, new_payload = create_refresh_token(user.id, row.family_id)
    row.revoked_at = datetime.now(timezone.utc)
    row.replaced_by_hash = token_hash(new_refresh)
    expiry = new_payload['exp'] if isinstance(new_payload['exp'], datetime) else datetime.fromtimestamp(new_payload['exp'], timezone.utc)
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=token_hash(new_refresh),
        family_id=row.family_id,
        expires_at=expiry,
    ))
    db.commit()
    return TokenOut(access_token=create_access_token(user.id, user.role.value), refresh_token=new_refresh)


@router.post('/logout', response_model=Message)
def logout(data: RefreshIn, db: Session = Depends(get_db)):
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash(data.refresh_token)))
    if row and not row.revoked_at:
        row.revoked_at = datetime.now(timezone.utc)
        db.commit()
    return Message(message='Logged out')


@router.post('/logout-all', response_model=Message)
def logout_all(db: Session = Depends(get_db), user: User = Depends(current_user)):
    db.execute(update(RefreshToken).where(
        RefreshToken.user_id == user.id,
        RefreshToken.revoked_at.is_(None),
    ).values(revoked_at=datetime.now(timezone.utc)))
    audit(db, user.id, 'auth.logout_all', 'user', user.id)
    db.commit()
    return Message(message='All sessions revoked')


@router.get('/me', response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.post('/users', response_model=UserOut, status_code=201)
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(Role.super_admin, Role.platform_admin)),
):
    if db.scalar(select(User).where(User.email == data.email.lower())):
        raise HTTPException(409, 'Email already exists')
    try:
        role = Role(data.role)
    except ValueError:
        raise HTTPException(422, 'Invalid platform role')
    user = User(
        email=data.email.lower(),
        full_name=data.full_name,
        password_hash=hash_password(data.password),
        role=role,
    )
    db.add(user)
    db.flush()
    audit(db, admin.id, 'user.created', 'user', user.id, {'role': role.value})
    db.commit()
    db.refresh(user)
    return user


@router.get('/users', response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(Role.super_admin, Role.platform_admin, Role.auditor)),
):
    return db.scalars(select(User).order_by(User.created_at.desc())).all()


@router.patch('/users/{user_id}/status', response_model=UserOut)
def set_user_status(
    user_id: str,
    data: UserStatusIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(Role.super_admin, Role.platform_admin)),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, 'User not found')
    if user.id == admin.id and not data.is_active:
        raise HTTPException(409, 'You cannot disable your own account')
    user.is_active = data.is_active
    if not data.is_active:
        db.execute(update(RefreshToken).where(
            RefreshToken.user_id == user.id,
            RefreshToken.revoked_at.is_(None),
        ).values(revoked_at=datetime.now(timezone.utc)))
    audit(db, admin.id, 'user.status_changed', 'user', user.id, {'is_active': data.is_active})
    db.commit()
    db.refresh(user)
    return user
