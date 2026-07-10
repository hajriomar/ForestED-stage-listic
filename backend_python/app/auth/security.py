"""
Primitives de sécurité : hash de mots de passe (Argon2), JWT, API keys.

Aucune dépendance à FastAPI ni à la base de données :
ce module est testable isolément.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

import jwt
from pwdlib import PasswordHash

from app.config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ALGORITHM,
    API_KEY_PREFIX,
    SECRET_KEY,
)

# Argon2id (recommandé OWASP pour le hash de mots de passe)
_password_hash = PasswordHash.recommended()


# =====================================================
# Mots de passe
# =====================================================

def hash_password(password: str) -> str:
    """Hash un mot de passe en Argon2id."""
    return _password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Vérifie un mot de passe contre son hash."""
    try:
        return _password_hash.verify(plain_password, hashed_password)
    except Exception:
        # Hash corrompu ou format inconnu : refus, jamais d'exception
        return False


# =====================================================
# JWT
# =====================================================

class TokenError(Exception):
    """Token invalide, expiré ou mal formé."""


def create_access_token(
    subject: str,
    role: str,
    expires_minutes: Optional[int] = None,
) -> str:
    """Crée un JWT d'accès.

    Args:
        subject         : identifiant utilisateur (str(user.id))
        role            : rôle du user, embarqué pour information
        expires_minutes : durée de vie ; défaut = config
    """
    minutes = (
        expires_minutes
        if expires_minutes is not None
        else ACCESS_TOKEN_EXPIRE_MINUTES
    )
    now = datetime.now(timezone.utc)

    payload = {
        "sub": subject,
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Dict[str, Any]:
    """Décode et valide un JWT d'accès.

    Raises:
        TokenError : si le token est expiré, invalide ou du mauvais type.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Invalid token") from exc

    if payload.get("type") != "access":
        raise TokenError("Invalid token type")

    if "sub" not in payload:
        raise TokenError("Missing subject")

    return payload


# =====================================================
# API keys
# =====================================================

def hash_api_key(api_key: str) -> str:
    """Hash SHA-256 d'une clé API (lookup O(1) en base, clé jamais stockée)."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def generate_api_key() -> Tuple[str, str, str]:
    """Génère une nouvelle clé API.

    Returns:
        (full_key, key_prefix, hashed_key)
        - full_key   : la clé complète, à afficher UNE SEULE FOIS
        - key_prefix : début de la clé pour identification humaine
        - hashed_key : SHA-256 à stocker en base
    """
    raw = secrets.token_urlsafe(32)
    full_key = f"{API_KEY_PREFIX}{raw}"
    return full_key, full_key[:12], hash_api_key(full_key)