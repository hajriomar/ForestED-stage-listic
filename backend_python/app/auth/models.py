"""
Modèles SQLAlchemy du module auth.

Phase 1 : User.
Phase 2 : Permission (par source uniquement).
Phase 3 : ApiKey — la clé brute n'est JAMAIS stockée (hash SHA-256).
Patch 5.5 : ApiKey.kind — "data" (accès programmatique JSON) ou
            "dashboard" (lien d'accès invité au dashboard, viewer strict).
"""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)

from app.auth.database import Base

ROLE_ADMIN = "admin"
ROLE_VIEWER = "viewer"
ROLES = (ROLE_ADMIN, ROLE_VIEWER)

SUBJECT_USER = "user"
SUBJECT_API_KEY = "api_key"
SUBJECT_TYPES = (SUBJECT_USER, SUBJECT_API_KEY)

KIND_DATA = "data"
KIND_DASHBOARD = "dashboard"
API_KEY_KINDS = (KIND_DATA, KIND_DASHBOARD)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    """Normalise un datetime en UTC aware (SQLite retourne du naive)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default=ROLE_VIEWER)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} role={self.role}>"

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN


class Permission(Base):
    """Droit d'accès d'un sujet (user ou api_key) à une source.

    source_name : nom de la source ("Polytech", "BUT", …) ou "*" (toutes).
                  Comparaison insensible à la casse (voir permissions.py).
    scopes      : liste JSON d'actions autorisées sur cette source,
                  ex. ["read:competence", "read:curriculum"] ou ["*"].
    """

    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, index=True)
    subject_type = Column(String(20), nullable=False, default=SUBJECT_USER)
    subject_id = Column(Integer, nullable=False, index=True)
    source_name = Column(String(100), nullable=False)
    scopes = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        UniqueConstraint(
            "subject_type", "subject_id", "source_name",
            name="uq_permission_subject_source",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Permission id={self.id} {self.subject_type}:{self.subject_id} "
            f"source={self.source_name!r} scopes={self.scopes}>"
        )


class ApiKey(Base):
    """Clé API.

    kind :
    - "data"      : accès programmatique aux endpoints JSON (X-API-Key).
    - "dashboard" : lien d'accès invité au dashboard Dash (viewer strict).
                    Les deux kinds sont acceptés sur les endpoints de
                    données ; kind ne gate que l'entrée dashboard.

    Sécurité :
    - hashed_key : SHA-256 de la clé complète. La clé brute est affichée
      UNE SEULE FOIS à la création, jamais stockée.
    - key_prefix : premiers caractères, identification humaine (non secret).
    - expires_at : None = pas d'expiration.
    - revoked_at : non None = clé révoquée (refusée définitivement).
    - une clé n'est JAMAIS admin (ni routes /admin, ni pipeline).

    Les droits par source sont des lignes Permission
    (subject_type="api_key", subject_id=ApiKey.id).
    """

    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    kind = Column(String(20), nullable=False, default=KIND_DATA)
    key_prefix = Column(String(20), nullable=False)
    hashed_key = Column(String(64), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    def __repr__(self) -> str:
        return (f"<ApiKey id={self.id} name={self.name!r} "
                f"kind={self.kind} prefix={self.key_prefix}>")

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return as_utc(self.expires_at) <= _utcnow()

    @property
    def is_valid(self) -> bool:
        return not self.is_revoked and not self.is_expired