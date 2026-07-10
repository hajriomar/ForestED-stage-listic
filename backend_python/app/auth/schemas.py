"""
Schémas Pydantic du module auth (entrées/sorties API).
"""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, EmailStr, Field

MIN_PASSWORD_LENGTH = 10


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # secondes


class UserOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# =====================================================
# Admin users (Phase 4)
# =====================================================

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=MIN_PASSWORD_LENGTH)
    role: Literal["admin", "viewer"] = "viewer"
    is_active: bool = True


class UserUpdate(BaseModel):
    """Tous les champs optionnels : seuls ceux fournis sont modifiés."""

    username: Optional[str] = Field(None, min_length=3, max_length=50)
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=MIN_PASSWORD_LENGTH)
    role: Optional[Literal["admin", "viewer"]] = None
    is_active: Optional[bool] = None


# =====================================================
# Admin permissions (Phase 4) — PAR SOURCE uniquement
# =====================================================

class PermissionIn(BaseModel):
    """Permission par source. Pas de programme_id (décision métier v1) :
    l'accès à une source couvre tous ses programmes, actuels et futurs."""

    source_name: str = Field(..., min_length=1, max_length=100,
                             description='Source (ex. "Polytech") ou "*"')
    scopes: List[str] = Field(..., min_length=1,
                              description='Ex. ["read:competence"] ou ["*"]')


class PermissionOut(BaseModel):
    id: int
    subject_type: str
    subject_id: int
    source_name: str
    scopes: List[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# =====================================================
# API keys (Phase 3, kind ajouté au patch 5.5)
# =====================================================

class ApiKeyPermissionIn(BaseModel):
    """Droit par source attaché à une API key à sa création."""

    source_name: str = Field(..., min_length=1, max_length=100,
                             description='Source (ex. "Polytech") ou "*"')
    scopes: List[str] = Field(..., min_length=1,
                              description='Ex. ["read:competence"] ou ["*"]')


class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    kind: Literal["data", "dashboard"] = "data"
    expires_in_days: Optional[int] = Field(
        None, gt=0, description="None = pas d'expiration"
    )
    permissions: List[ApiKeyPermissionIn] = Field(default_factory=list)


class ApiKeyCreated(BaseModel):
    """Réponse de création : contient la clé en clair, affichée UNE SEULE FOIS."""

    id: int
    name: str
    kind: str
    api_key: str
    key_prefix: str
    expires_at: Optional[datetime] = None
    message: str = (
        "Conservez cette clé maintenant : elle ne sera plus jamais affichée."
    )


class ApiKeyOut(BaseModel):
    """Listing admin : jamais de clé en clair, uniquement le préfixe."""

    id: int
    name: str
    kind: str
    key_prefix: str
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ApiKeyInfo(BaseModel):
    """Infos publiques d'une clé (validation de session invitée Dash)."""

    name: str
    kind: str
    sources: List[str]