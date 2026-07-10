"""
Routes admin de gestion des API keys.

POST   /admin/api-keys        : créer une clé (affichée une seule fois)
                                kind "data" (accès JSON) ou "dashboard"
                                (lien d'accès invité au dashboard)
GET    /admin/api-keys        : lister (préfixes uniquement, jamais la clé)
DELETE /admin/api-keys/{id}   : révoquer

Toutes réservées au rôle admin.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.database import get_db
from app.auth.dependencies import require_admin
from app.auth.models import SUBJECT_API_KEY, ApiKey, Permission, User
from app.auth.permissions import KNOWN_SCOPES
from app.auth.schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyOut
from app.auth.security import generate_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/api-keys", tags=["admin"])


@router.post("", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
def create_api_key(
    payload: ApiKeyCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ApiKeyCreated:
    """Crée une API key et ses permissions par source.

    La clé complète n'est retournée qu'ici, une seule fois.
    Seul son hash SHA-256 est stocké.
    """
    for perm in payload.permissions:
        unknown = [s for s in perm.scopes if s not in KNOWN_SCOPES]
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown scopes: {unknown}. "
                       f"Known: {sorted(KNOWN_SCOPES)}",
            )

    full_key, key_prefix, hashed_key = generate_api_key()

    expires_at = None
    if payload.expires_in_days is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(
            days=payload.expires_in_days
        )

    api_key = ApiKey(
        name=payload.name,
        kind=payload.kind,
        key_prefix=key_prefix,
        hashed_key=hashed_key,
        expires_at=expires_at,
        created_by_user_id=admin.id,
    )
    db.add(api_key)
    db.flush()  # obtenir api_key.id avant les permissions

    for perm in payload.permissions:
        db.add(Permission(
            subject_type=SUBJECT_API_KEY,
            subject_id=api_key.id,
            source_name=perm.source_name,
            scopes=perm.scopes,
        ))

    db.commit()

    logger.info(
        "API key created id=%s name=%r kind=%s by admin=%s (%d permissions)",
        api_key.id, api_key.name, api_key.kind, admin.username,
        len(payload.permissions),
    )

    return ApiKeyCreated(
        id=api_key.id,
        name=api_key.name,
        kind=api_key.kind,
        api_key=full_key,
        key_prefix=key_prefix,
        expires_at=api_key.expires_at,
    )


@router.get("", response_model=List[ApiKeyOut])
def list_api_keys(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> List[ApiKey]:
    """Liste les API keys (préfixes uniquement, jamais de clé en clair)."""
    return db.query(ApiKey).order_by(ApiKey.id).all()


@router.delete("/{api_key_id}")
def revoke_api_key(
    api_key_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Révoque une API key (refus définitif, la ligne est conservée)."""
    api_key = db.get(ApiKey, api_key_id)

    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )

    if api_key.is_revoked:
        return {"status": "already_revoked", "id": api_key_id}

    api_key.revoked_at = datetime.now(timezone.utc)
    db.commit()

    logger.info(
        "API key revoked id=%s name=%r kind=%s by admin=%s",
        api_key.id, api_key.name, api_key.kind, admin.username,
    )
    return {"status": "revoked", "id": api_key_id}