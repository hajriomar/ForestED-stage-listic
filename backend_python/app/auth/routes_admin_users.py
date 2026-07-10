"""
Routes admin de gestion des utilisateurs et de leurs permissions par source.

Users :
    GET    /admin/users                     : lister
    POST   /admin/users                     : créer (mot de passe hashé Argon2id)
    GET    /admin/users/{user_id}           : détail
    PATCH  /admin/users/{user_id}           : modifier (username, email, role,
                                              is_active, password)
    DELETE /admin/users/{user_id}           : supprimer (permissions incluses)

Permissions (PAR SOURCE uniquement — pas de programme_id) :
    GET    /admin/users/{user_id}/permissions : lister
    POST   /admin/users/{user_id}/permissions : ajouter/mettre à jour (upsert)
    DELETE /admin/permissions/{permission_id} : supprimer

Garde-fous :
    - un admin ne peut pas se désactiver, se rétrograder ni se supprimer ;
    - impossible de désactiver/rétrograder/supprimer le dernier admin actif ;
    - viewer → 403, API key → 403, sans token → 401 (via require_admin).
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.database import get_db
from app.auth.dependencies import require_admin
from app.auth.models import (
    ROLE_ADMIN,
    SUBJECT_USER,
    Permission,
    User,
)
from app.auth.permissions import KNOWN_SCOPES
from app.auth.schemas import (
    PermissionIn,
    PermissionOut,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.auth.security import hash_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# =====================================================
# Helpers
# =====================================================

def _get_user_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


def _count_active_admins(db: Session) -> int:
    return (
        db.query(User)
        .filter(User.role == ROLE_ADMIN, User.is_active.is_(True))
        .count()
    )


def _check_unique(db: Session, username=None, email=None, exclude_id=None) -> None:
    """409 si username ou email déjà pris par un autre utilisateur."""
    if username is not None:
        q = db.query(User).filter(User.username == username)
        if exclude_id is not None:
            q = q.filter(User.id != exclude_id)
        if q.first() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already exists",
            )
    if email is not None:
        q = db.query(User).filter(User.email == email)
        if exclude_id is not None:
            q = q.filter(User.id != exclude_id)
        if q.first() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already exists",
            )


def _validate_scopes(scopes: List[str]) -> None:
    unknown = [s for s in scopes if s not in KNOWN_SCOPES]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown scopes: {unknown}. Known: {sorted(KNOWN_SCOPES)}",
        )


# =====================================================
# Users
# =====================================================

@router.get("/users", response_model=List[UserOut])
def list_users(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> List[User]:
    """Liste tous les utilisateurs."""
    return db.query(User).order_by(User.id).all()


@router.post("/users", response_model=UserOut,
             status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> User:
    """Crée un utilisateur (mot de passe hashé, jamais stocké en clair)."""
    _check_unique(db, username=payload.username, email=payload.email)

    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        is_active=payload.is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info(
        "User created id=%s username=%r role=%s by admin=%s",
        user.id, user.username, user.role, admin.username,
    )
    return user


@router.get("/users/{user_id}", response_model=UserOut)
def get_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> User:
    """Détail d'un utilisateur."""
    return _get_user_or_404(db, user_id)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> User:
    """Met à jour un utilisateur. Seuls les champs fournis sont modifiés."""
    target = _get_user_or_404(db, user_id)
    data = payload.model_dump(exclude_unset=True)

    # --- Garde-fous anti-lockout ---
    if target.id == admin.id:
        if data.get("is_active") is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Admins cannot deactivate themselves",
            )
        if "role" in data and data["role"] != ROLE_ADMIN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Admins cannot demote themselves",
            )

    removes_active_admin = (
        target.role == ROLE_ADMIN
        and target.is_active
        and (
            data.get("is_active") is False
            or ("role" in data and data["role"] != ROLE_ADMIN)
        )
    )
    if removes_active_admin and _count_active_admins(db) <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate or demote the last active admin",
        )

    # --- Unicité ---
    _check_unique(
        db,
        username=data.get("username"),
        email=data.get("email"),
        exclude_id=target.id,
    )

    # --- Application ---
    if "password" in data:
        target.hashed_password = hash_password(data.pop("password"))

    for field, value in data.items():
        setattr(target, field, value)

    db.commit()
    db.refresh(target)

    logger.info(
        "User updated id=%s (%s) by admin=%s",
        target.id, sorted(data.keys()), admin.username,
    )
    return target


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Supprime un utilisateur et toutes ses permissions.

    Pour une mesure réversible, préférer PATCH is_active=false.
    """
    target = _get_user_or_404(db, user_id)

    if target.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admins cannot delete themselves",
        )

    if (
        target.role == ROLE_ADMIN
        and target.is_active
        and _count_active_admins(db) <= 1
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete the last active admin",
        )

    deleted_permissions = (
        db.query(Permission)
        .filter(
            Permission.subject_type == SUBJECT_USER,
            Permission.subject_id == target.id,
        )
        .delete()
    )
    db.delete(target)
    db.commit()

    logger.info(
        "User deleted id=%s username=%r (+%d permissions) by admin=%s",
        user_id, target.username, deleted_permissions, admin.username,
    )
    return {"status": "deleted", "id": user_id,
            "permissions_deleted": deleted_permissions}


# =====================================================
# Permissions par source (pas de programme_id)
# =====================================================

@router.get("/users/{user_id}/permissions", response_model=List[PermissionOut])
def list_user_permissions(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> List[Permission]:
    """Liste les permissions par source d'un utilisateur."""
    _get_user_or_404(db, user_id)
    return (
        db.query(Permission)
        .filter(
            Permission.subject_type == SUBJECT_USER,
            Permission.subject_id == user_id,
        )
        .order_by(Permission.id)
        .all()
    )


@router.post("/users/{user_id}/permissions", response_model=PermissionOut,
             status_code=status.HTTP_201_CREATED)
def upsert_user_permission(
    user_id: int,
    payload: PermissionIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Permission:
    """Ajoute une permission par source, ou met à jour ses scopes si une
    permission existe déjà pour cette source (comparaison insensible à la
    casse, cohérente avec can_access).
    """
    target = _get_user_or_404(db, user_id)
    _validate_scopes(payload.scopes)

    requested = payload.source_name.strip()

    existing = next(
        (
            p for p in db.query(Permission).filter(
                Permission.subject_type == SUBJECT_USER,
                Permission.subject_id == target.id,
            )
            if p.source_name.strip().lower() == requested.lower()
        ),
        None,
    )

    if existing is not None:
        existing.scopes = payload.scopes
        db.commit()
        db.refresh(existing)
        logger.info(
            "Permission updated id=%s user=%r source=%r scopes=%s by admin=%s",
            existing.id, target.username, existing.source_name,
            payload.scopes, admin.username,
        )
        return existing

    permission = Permission(
        subject_type=SUBJECT_USER,
        subject_id=target.id,
        source_name=requested,
        scopes=payload.scopes,
    )
    db.add(permission)
    db.commit()
    db.refresh(permission)

    logger.info(
        "Permission created id=%s user=%r source=%r scopes=%s by admin=%s",
        permission.id, target.username, requested,
        payload.scopes, admin.username,
    )
    return permission


@router.delete("/permissions/{permission_id}")
def delete_permission(
    permission_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Supprime une permission (user ou api_key) par id."""
    permission = db.get(Permission, permission_id)
    if permission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Permission not found",
        )

    db.delete(permission)
    db.commit()

    logger.info(
        "Permission deleted id=%s (%s:%s source=%r) by admin=%s",
        permission_id, permission.subject_type, permission.subject_id,
        permission.source_name, admin.username,
    )
    return {"status": "deleted", "id": permission_id}