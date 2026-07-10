"""
Tests Phase 3 — API keys : génération, hash, expiration, révocation,
accès data via X-API-Key avec permissions par source.

Lancer depuis backend_python :
    python -m pytest tests/test_api_keys_phase3.py -v
"""

import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_auth_phase3.db")

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.auth.database import Base, SessionLocal, engine
from app.auth.models import (
    ROLE_ADMIN,
    ROLE_VIEWER,
    SUBJECT_API_KEY,
    ApiKey,
    Permission,
    User,
)
from app.auth.security import generate_api_key, hash_api_key
from app.main import app

client = TestClient(app)

PASSWORD = "motdepasse-test-123"
TEST_DATA = Path("./test_data_phase3").resolve()


def _write(path: Path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content), encoding="utf-8")


@pytest.fixture(scope="module", autouse=True)
def data_tree():
    shutil.rmtree(TEST_DATA, ignore_errors=True)
    processed = TEST_DATA / "processed"
    _write(processed / "competence" / "BUT" / "QLIO_BUT_ref_processed.json",
           {"intitule": "Ref BUT QLIO"})
    _write(processed / "competence" / "Polytech" / "IDU_polytech_processed.json",
           {"intitule": "Ref Polytech IDU"})
    yield
    shutil.rmtree(TEST_DATA, ignore_errors=True)


@pytest.fixture(autouse=True)
def patch_data_folders(monkeypatch):
    monkeypatch.setattr(
        main_module, "PROCESSED_DATA_FOLDER", str(TEST_DATA / "processed")
    )
    monkeypatch.setattr(
        main_module, "ANALYTICS_DATA_FOLDER", str(TEST_DATA / "analytics")
    )


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    from app.auth.security import hash_password
    db.add_all([
        User(username="admin", email="admin@test.fr",
             hashed_password=hash_password(PASSWORD), role=ROLE_ADMIN),
        User(username="viewer", email="viewer@test.fr",
             hashed_password=hash_password(PASSWORD), role=ROLE_VIEWER),
    ])
    db.commit()
    db.close()
    yield


def get_token(username):
    r = client.post("/auth/login",
                    data={"username": username, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def admin_headers():
    return {"Authorization": f"Bearer {get_token('admin')}"}


def create_key(name="cle-test", permissions=None, expires_in_days=None):
    payload = {"name": name, "permissions": permissions or []}
    if expires_in_days is not None:
        payload["expires_in_days"] = expires_in_days
    r = client.post("/admin/api-keys", json=payload, headers=admin_headers())
    assert r.status_code == 201, r.text
    return r.json()


def sources_of(response):
    return sorted({i["source"] for i in response.json().get("data", [])})


# =====================================================
# Génération / stockage
# =====================================================

def test_generate_api_key_hash_not_plain():
    full, prefix, hashed = generate_api_key()
    assert full.startswith("fed_")
    assert full[:12] == prefix
    assert hashed != full
    assert hashed == hash_api_key(full)
    assert len(hashed) == 64  # SHA-256 hex


def test_created_key_not_stored_in_plain():
    created = create_key(name="cle-stockage")
    db = SessionLocal()
    row = db.get(ApiKey, created["id"])
    db.close()
    assert row.hashed_key != created["api_key"]
    assert row.hashed_key == hash_api_key(created["api_key"])
    # le préfixe (non secret) est bien stocké pour identification
    assert created["api_key"].startswith(row.key_prefix)


def test_listing_never_shows_plain_key():
    create_key(name="cle-listing")
    r = client.get("/admin/api-keys", headers=admin_headers())
    assert r.status_code == 200
    for item in r.json():
        assert "api_key" not in item
        assert "hashed_key" not in item
        assert "key_prefix" in item


# =====================================================
# Accès data via X-API-Key
# =====================================================

def test_api_key_valid_accepted_and_filtered():
    created = create_key(
        name="cle-polytech",
        permissions=[{"source_name": "Polytech",
                      "scopes": ["read:competence"]}],
    )
    r = client.get("/competences",
                   headers={"X-API-Key": created["api_key"]})
    assert r.status_code == 200
    assert sources_of(r) == ["Polytech"]  # jamais BUT


def test_api_key_wildcard_sees_everything():
    created = create_key(
        name="cle-star",
        permissions=[{"source_name": "*", "scopes": ["*"]}],
    )
    r = client.get("/competences",
                   headers={"X-API-Key": created["api_key"]})
    assert sources_of(r) == ["BUT", "Polytech"]


def test_api_key_missing_scope_refused():
    created = create_key(
        name="cle-curriculum-seul",
        permissions=[{"source_name": "BUT",
                      "scopes": ["read:curriculum"]}],
    )
    r = client.get("/competences",
                   headers={"X-API-Key": created["api_key"]})
    assert r.status_code == 200
    assert r.json()["status"] == "empty"


def test_api_key_without_permissions_sees_nothing():
    created = create_key(name="cle-vide")
    r = client.get("/competences",
                   headers={"X-API-Key": created["api_key"]})
    assert r.json()["status"] == "empty"


def test_unknown_api_key_rejected():
    r = client.get("/competences",
                   headers={"X-API-Key": "fed_cle_inventee_12345"})
    assert r.status_code == 401


def test_revoked_api_key_rejected():
    created = create_key(name="cle-a-revoquer",
                         permissions=[{"source_name": "*", "scopes": ["*"]}])

    r = client.delete(f"/admin/api-keys/{created['id']}",
                      headers=admin_headers())
    assert r.status_code == 200
    assert r.json()["status"] == "revoked"

    r = client.get("/competences",
                   headers={"X-API-Key": created["api_key"]})
    assert r.status_code == 401
    assert "revoked" in r.json()["detail"].lower()


def test_expired_api_key_rejected():
    # Clé expirée créée directement en base (la route refuse expires<=0)
    full, prefix, hashed = generate_api_key()
    db = SessionLocal()
    admin = db.query(User).filter(User.username == "admin").first()
    key = ApiKey(
        name="cle-expiree",
        key_prefix=prefix,
        hashed_key=hashed,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        created_by_user_id=admin.id,
    )
    db.add(key)
    db.flush()
    db.add(Permission(subject_type=SUBJECT_API_KEY, subject_id=key.id,
                      source_name="*", scopes=["*"]))
    db.commit()
    db.close()

    r = client.get("/competences", headers={"X-API-Key": full})
    assert r.status_code == 401
    assert "expired" in r.json()["detail"].lower()


def test_last_used_at_updated():
    created = create_key(name="cle-usage",
                         permissions=[{"source_name": "*", "scopes": ["*"]}])
    client.get("/competences", headers={"X-API-Key": created["api_key"]})

    db = SessionLocal()
    row = db.get(ApiKey, created["id"])
    db.close()
    assert row.last_used_at is not None


# =====================================================
# Administration des clés
# =====================================================

def test_viewer_cannot_create_key():
    r = client.post(
        "/admin/api-keys",
        json={"name": "interdit"},
        headers={"Authorization": f"Bearer {get_token('viewer')}"},
    )
    assert r.status_code == 403


def test_create_key_requires_auth():
    assert client.post("/admin/api-keys", json={"name": "x"}).status_code == 401


def test_unknown_scope_rejected_at_creation():
    r = client.post(
        "/admin/api-keys",
        json={"name": "cle-scope-inconnu",
              "permissions": [{"source_name": "BUT",
                               "scopes": ["read:inconnu"]}]},
        headers=admin_headers(),
    )
    assert r.status_code == 422


def test_revoke_unknown_key_404():
    r = client.delete("/admin/api-keys/9999", headers=admin_headers())
    assert r.status_code == 404


# =====================================================
# Non-régression : JWT et pipeline
# =====================================================

def test_jwt_still_works_on_data():
    r = client.get("/competences", headers=admin_headers())
    assert r.status_code == 200
    assert sources_of(r) == ["BUT", "Polytech"]


def test_api_key_cannot_run_pipeline():
    created = create_key(name="cle-pipeline",
                         permissions=[{"source_name": "*", "scopes": ["*"]}])
    r = client.post("/pipeline/run",
                    headers={"X-API-Key": created["api_key"]})
    # une API key n'est jamais admin : 403 (authentifiee mais interdite)
    assert r.status_code == 403