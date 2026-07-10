"""
Tests Phase 1 — authentification (User, JWT, /auth/login, /auth/me).

Lancer depuis backend_python :
    pytest tests/test_auth_phase1.py -v
"""

import os

# Base de test isolée — DOIT être défini avant tout import app.*
os.environ["DATABASE_URL"] = "sqlite:///./test_auth.db"

import pytest
from fastapi.testclient import TestClient

from app.auth.database import Base, SessionLocal, engine
from app.auth.models import ROLE_ADMIN, ROLE_VIEWER, User
from app.auth.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.main import app

client = TestClient(app)

PASSWORD = "motdepasse-test-123"


@pytest.fixture(autouse=True)
def setup_db():
    """Base propre avec 3 users : admin, viewer, inactif."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    db.add_all([
        User(
            username="admin",
            email="admin@test.fr",
            hashed_password=hash_password(PASSWORD),
            role=ROLE_ADMIN,
        ),
        User(
            username="viewer",
            email="viewer@test.fr",
            hashed_password=hash_password(PASSWORD),
            role=ROLE_VIEWER,
        ),
        User(
            username="inactif",
            email="inactif@test.fr",
            hashed_password=hash_password(PASSWORD),
            role=ROLE_VIEWER,
            is_active=False,
        ),
    ])
    db.commit()
    db.close()
    yield


def do_login(username: str, password: str):
    return client.post(
        "/auth/login",
        data={"username": username, "password": password},
    )


# =====================================================
# Sécurité (unitaires, sans HTTP)
# =====================================================

def test_password_hash_and_verify():
    hashed = hash_password(PASSWORD)
    assert hashed != PASSWORD
    assert hashed.startswith("$argon2")
    assert verify_password(PASSWORD, hashed)
    assert not verify_password("mauvais", hashed)


def test_jwt_roundtrip():
    token = create_access_token(subject="42", role="viewer")
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert payload["role"] == "viewer"
    assert payload["type"] == "access"


def test_jwt_expired():
    token = create_access_token(subject="42", role="viewer", expires_minutes=-1)
    with pytest.raises(TokenError):
        decode_access_token(token)


def test_jwt_invalid():
    with pytest.raises(TokenError):
        decode_access_token("pas-un-token")


# =====================================================
# /auth/login
# =====================================================

def test_login_ok():
    r = do_login("admin", PASSWORD)
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["expires_in"] > 0


def test_login_wrong_password():
    r = do_login("admin", "mauvais-mot-de-passe")
    assert r.status_code == 401
    # Message générique : aucun indice sur l'existence du compte
    assert "Incorrect" in r.json()["detail"]


def test_login_unknown_user():
    r = do_login("fantome", PASSWORD)
    assert r.status_code == 401


def test_login_inactive_user():
    r = do_login("inactif", PASSWORD)
    assert r.status_code == 403


# =====================================================
# /auth/me
# =====================================================

def test_me_with_valid_token():
    token = do_login("viewer", PASSWORD).json()["access_token"]
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["username"] == "viewer"
    assert body["role"] == "viewer"
    assert "hashed_password" not in body


def test_me_without_token():
    r = client.get("/auth/me")
    assert r.status_code == 401


def test_me_with_expired_token():
    db = SessionLocal()
    user = db.query(User).filter(User.username == "viewer").first()
    db.close()
    token = create_access_token(subject=str(user.id), role=user.role, expires_minutes=-1)
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_me_with_garbage_token():
    r = client.get("/auth/me", headers={"Authorization": "Bearer nimporte.quoi.xyz"})
    assert r.status_code == 401


# =====================================================
# Non-régression Phase 0
# =====================================================

def test_health_still_public():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"