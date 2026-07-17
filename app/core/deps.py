from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.core.security import decode_token, token_hash
from app.models.entities import User, Role, SiteMember, SiteRole, ApiKey

bearer = HTTPBearer(auto_error=False)


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(401, 'Authentication required')
    try:
        payload = decode_token(credentials.credentials)
        if payload.get('type') != 'access':
            raise ValueError()
    except Exception:
        raise HTTPException(401, 'Invalid or expired access token')
    user = db.get(User, payload.get('sub'))
    if not user or not user.is_active:
        raise HTTPException(401, 'Account unavailable')
    return user


def require_roles(*roles: Role):
    def dependency(user: User = Depends(current_user)):
        if user.role not in roles:
            raise HTTPException(403, 'Insufficient role')
        return user
    return dependency


def site_access(site_id: str, db: Session, user: User, minimum: set[SiteRole] | None = None) -> SiteMember | None:
    if user.role == Role.super_admin:
        return None
    member = db.scalar(select(SiteMember).where(SiteMember.site_id == site_id, SiteMember.user_id == user.id))
    if not member:
        raise HTTPException(403, 'No access to this site')
    if minimum and member.role not in minimum:
        raise HTTPException(403, 'Insufficient site permission')
    return member


def require_delivery_key(
    x_api_key: str | None = Header(default=None, alias='X-API-Key'),
    db: Session = Depends(get_db),
):
    if not x_api_key:
        return None
    key = db.scalar(select(ApiKey).where(ApiKey.key_hash == token_hash(x_api_key), ApiKey.revoked_at.is_(None)))
    if not key:
        raise HTTPException(401, 'Invalid API key')
    return key
