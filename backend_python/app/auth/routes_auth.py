"""
Routes d'authentification : /auth/login, /auth/me et /auth/key-info.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.auth.database import get_db
from app.auth.dependencies import api_key_header, get_current_user
from app.auth.models import SUBJECT_API_KEY, ApiKey, User
from app.auth.permissions import get_subject_permissions
from app.auth.schemas import ApiKeyInfo, Token, UserOut
from app.auth.security import create_access_token, hash_api_key, verify_password
from app.config import ACCESS_TOKEN_EXPIRE_MINUTES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    """Authentifie un utilisateur (username ou email + password), retourne un JWT.

    Réponses :
        200 : token
        401 : identifiants invalides (message générique, pas d'indice)
        403 : compte désactivé
    """
    identifier = form_data.username.strip()
    user = (
        db.query(User)
        .filter(
            (User.username == identifier) | (User.email == identifier)
        )
        .first()
    )

    if user is None or not verify_password(form_data.password, user.hashed_password):
        # Message générique : ne révèle pas si le compte existe
        logger.info("Login failed for username=%r", form_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        logger.info("Login refused (inactive) for username=%r", form_data.username)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )

    token = create_access_token(subject=str(user.id), role=user.role)
    logger.info("Login OK for username=%r (role=%s)", user.username, user.role)

    return Token(
        access_token=token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> User:
    """Retourne le profil de l'utilisateur authentifié."""
    return current_user


@router.get("/key-info", response_model=ApiKeyInfo)
def key_info(
    api_key: Optional[str] = Depends(api_key_header),
    db: Session = Depends(get_db),
) -> ApiKeyInfo:
    """Infos d'une clé API (header X-API-Key) : nom, kind, sources.

    Utilisé par Dash pour valider un lien d'accès invité (/access/<clé>)
    et construire le badge « Accès invité — ... ». Clé révoquée, expirée
    ou inconnue -> 401. Ne révèle jamais la clé ni son hash.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
        )

    key = (
        db.query(ApiKey)
        .filter(ApiKey.hashed_key == hash_api_key(api_key))
        .first()
    )

    if key is None:
        logger.info("key-info: unknown key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    if key.is_revoked:
        logger.info("key-info: revoked key id=%s", key.id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key revoked",
        )
    if key.is_expired:
        logger.info("key-info: expired key id=%s", key.id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key expired",
        )

    permissions = get_subject_permissions(db, SUBJECT_API_KEY, key.id)
    sources = [p.source_name for p in permissions]

    logger.info(
        "key-info OK: id=%s name=%r kind=%s sources=%s",
        key.id, key.name, key.kind, sources,
    )
    return ApiKeyInfo(name=key.name, kind=key.kind, sources=sources)