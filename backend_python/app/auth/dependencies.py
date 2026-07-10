"""
Dependencies FastAPI du module auth.

get_current_user      : résout le JWT Bearer vers un User actif (401 sinon).
get_current_principal : accepte JWT Bearer OU header X-API-Key et retourne
                        un Principal unifié pour la couche permissions.
require_admin         : restreint une route au rôle admin.
                        - sans credentials → 401
                        - viewer → 403
                        - API key → 403 (une clé n'administre jamais)
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.auth.database import get_db
from app.auth.models import SUBJECT_API_KEY, SUBJECT_USER, ApiKey, User
from app.auth.security import TokenError, decode_access_token, hash_api_key

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

_credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


@dataclass
class Principal:
    """Sujet authentifié unifié : utilisateur (JWT) ou API key.

    La couche permissions ne connaît que subject_type/subject_id/is_admin,
    quel que soit le mode d'authentification.
    """

    subject_type: str
    subject_id: int
    name: str
    is_admin: bool = False


# =====================================================
# Utilisateur (JWT)
# =====================================================

def _user_from_token(token: str, db: Session) -> User:
    try:
        payload = decode_access_token(token)
    except TokenError as exc:
        logger.info("Auth failed: %s", exc)
        raise _credentials_exception from exc

    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError) as exc:
        raise _credentials_exception from exc

    user = db.get(User, user_id)

    if user is None or not user.is_active:
        raise _credentials_exception

    return user


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Résout le JWT en User actif, sinon 401."""
    return _user_from_token(token, db)


# =====================================================
# API key (X-API-Key)
# =====================================================

def _principal_from_api_key(api_key: str, db: Session) -> Principal:
    hashed = hash_api_key(api_key)
    key = db.query(ApiKey).filter(ApiKey.hashed_key == hashed).first()

    if key is None:
        logger.info("API key auth failed: unknown key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    if key.is_revoked:
        logger.info("API key auth failed: revoked (id=%s)", key.id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key revoked",
        )

    if key.is_expired:
        logger.info("API key auth failed: expired (id=%s)", key.id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key expired",
        )

    key.last_used_at = datetime.now(timezone.utc)
    db.commit()

    return Principal(
        subject_type=SUBJECT_API_KEY,
        subject_id=key.id,
        name=f"api_key:{key.name}",
        is_admin=False,  # une API key n'est jamais admin
    )


# =====================================================
# Principal unifié (JWT ou API key)
# =====================================================

def get_current_principal(
    token: Optional[str] = Depends(oauth2_scheme_optional),
    api_key: Optional[str] = Depends(api_key_header),
    db: Session = Depends(get_db),
) -> Principal:
    """Authentifie via X-API-Key ou JWT Bearer, sinon 401.

    L'API key est testée en premier si les deux sont fournis.
    """
    if api_key:
        return _principal_from_api_key(api_key, db)

    if token:
        user = _user_from_token(token, db)
        return Principal(
            subject_type=SUBJECT_USER,
            subject_id=user.id,
            name=user.username,
            is_admin=user.is_admin,
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


# =====================================================
# Admin (basé sur le Principal unifié)
# =====================================================

def require_admin(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> User:
    """Restreint la route au rôle admin et retourne le User admin.

    - sans credentials : 401 (levé par get_current_principal)
    - API key : 403 — les clés n'administrent jamais, quel que soit leur scope
    - user non admin : 403
    """
    if principal.subject_type == SUBJECT_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API keys cannot access admin routes",
        )

    if not principal.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )

    user = db.get(User, principal.subject_id)
    if user is None or not user.is_active:
        raise _credentials_exception

    return user