"""
Tests Phase 4 — API admin users & permissions (par source, sans programme_id).

Lancer depuis backend_python :
    python -m pytest tests/test_admin_phase4.py -v
"""

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.auth.database import Base, SessionLocal, engine
from app.auth.models import (
    ROLE_ADMIN,
    ROLE_VIEWER,
    SUBJECT_USER,
    Permission,
    User,
)
from app.auth.security import hash_password
from app.main import app

client = TestClient(app)

PASSWORD = "motdepasse-test-123"
TEST_DATA = Path("./test_data_phase4").resolve()


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
    db.add_all([
        User(username="admin", email="admin@test.fr",
             hashed_password=hash_password(PASSWORD), role=ROLE_ADMIN),
        User(username="viewer", email="viewer@test.fr",
             hashed_password=hash_password(PASSWORD), role=ROLE_VIEWER),
    ])
    db.commit()
    db.close()
    yield


def get_token(username, password=PASSWORD):
    r = client.post("/api/v1/auth/login",
                    data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def headers(username, password=PASSWORD):
    return {"Authorization": f"Bearer {get_token(username, password)}"}


def create_api_key_star():
    r = client.post(
        "/api/v1/admin/api-keys",
        json={"name": "cle-test",
              "permissions": [{"source_name": "*", "scopes": ["*"]}]},
        headers=headers("admin"),
    )
    assert r.status_code == 201, r.text
    return r.json()["api_key"]


# =====================================================
# Accès aux routes admin
# =====================================================

def test_admin_routes_require_auth():
    assert client.get("/api/v1/admin/users").status_code == 401
    assert client.post("/api/v1/admin/users", json={}).status_code == 401


def test_viewer_cannot_access_admin_users():
    r = client.get("/api/v1/admin/users", headers=headers("viewer"))
    assert r.status_code == 403

    r = client.post(
        "/api/v1/admin/users",
        json={"username": "intrus", "email": "i@test.fr",
              "password": "motdepasse-x-123"},
        headers=headers("viewer"),
    )
    assert r.status_code == 403


def test_api_key_cannot_access_admin_users():
    api_key = create_api_key_star()  # clé avec tous les droits data
    r = client.get("/api/v1/admin/users", headers={"X-API-Key": api_key})
    assert r.status_code == 403


# =====================================================
# CRUD users
# =====================================================

def test_admin_can_create_viewer_and_new_viewer_can_login():
    r = client.post(
        "/api/v1/admin/users",
        json={"username": "nouveau", "email": "nouveau@test.fr",
              "password": "motdepasse-n-123", "role": "viewer"},
        headers=headers("admin"),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["role"] == "viewer"
    assert "hashed_password" not in body
    assert "password" not in body

    # le nouveau viewer peut se connecter
    assert get_token("nouveau", "motdepasse-n-123")


def test_create_duplicate_username_conflict():
    r = client.post(
        "/api/v1/admin/users",
        json={"username": "viewer", "email": "autre@test.fr",
              "password": "motdepasse-x-123"},
        headers=headers("admin"),
    )
    assert r.status_code == 409


def test_create_password_too_short_rejected():
    r = client.post(
        "/api/v1/admin/users",
        json={"username": "courtmdp", "email": "c@test.fr",
              "password": "court"},
        headers=headers("admin"),
    )
    assert r.status_code == 422


def test_admin_can_list_users():
    r = client.get("/api/v1/admin/users", headers=headers("admin"))
    assert r.status_code == 200
    usernames = {u["username"] for u in r.json()}
    assert {"admin", "viewer"} <= usernames
    for u in r.json():
        assert "hashed_password" not in u


def test_admin_can_update_role_email_active():
    db = SessionLocal()
    viewer_id = db.query(User).filter(User.username == "viewer").first().id
    db.close()

    r = client.patch(
        f"/api/v1/admin/users/{viewer_id}",
        json={"email": "nouvel-email@test.fr", "role": "admin"},
        headers=headers("admin"),
    )
    assert r.status_code == 200
    assert r.json()["email"] == "nouvel-email@test.fr"
    assert r.json()["role"] == "admin"

    # désactivation (viewer redevenu admin mais pas le dernier : admin reste)
    r = client.patch(
        f"/api/v1/admin/users/{viewer_id}",
        json={"is_active": False},
        headers=headers("admin"),
    )
    assert r.status_code == 200
    assert r.json()["is_active"] is False

    # un user désactivé ne peut plus se connecter
    r = client.post("/api/v1/auth/login",
                    data={"username": "viewer", "password": PASSWORD})
    assert r.status_code == 403


def test_admin_can_change_user_password():
    db = SessionLocal()
    viewer_id = db.query(User).filter(User.username == "viewer").first().id
    db.close()

    r = client.patch(
        f"/api/v1/admin/users/{viewer_id}",
        json={"password": "nouveau-mdp-securise-1"},
        headers=headers("admin"),
    )
    assert r.status_code == 200

    # ancien mot de passe refusé, nouveau accepté
    r = client.post("/api/v1/auth/login",
                    data={"username": "viewer", "password": PASSWORD})
    assert r.status_code == 401
    assert get_token("viewer", "nouveau-mdp-securise-1")


def test_admin_cannot_deactivate_self():
    db = SessionLocal()
    admin_id = db.query(User).filter(User.username == "admin").first().id
    db.close()

    r = client.patch(
        f"/api/v1/admin/users/{admin_id}",
        json={"is_active": False},
        headers=headers("admin"),
    )
    assert r.status_code == 400


def test_admin_cannot_demote_self():
    db = SessionLocal()
    admin_id = db.query(User).filter(User.username == "admin").first().id
    db.close()

    r = client.patch(
        f"/api/v1/admin/users/{admin_id}",
        json={"role": "viewer"},
        headers=headers("admin"),
    )
    assert r.status_code == 400


def test_admin_cannot_delete_self():
    db = SessionLocal()
    admin_id = db.query(User).filter(User.username == "admin").first().id
    db.close()

    r = client.delete(f"/api/v1/admin/users/{admin_id}", headers=headers("admin"))
    assert r.status_code == 400


def test_cannot_remove_last_active_admin():
    # admin2 actif : le rétrograder est permis tant qu'admin reste
    r = client.post(
        "/api/v1/admin/users",
        json={"username": "admin2", "email": "admin2@test.fr",
              "password": "motdepasse-a-123", "role": "admin"},
        headers=headers("admin"),
    )
    admin2_id = r.json()["id"]

    # admin2 (connecté) rétrograde admin → il resterait admin2 seul : OK
    db = SessionLocal()
    admin_id = db.query(User).filter(User.username == "admin").first().id
    db.close()

    r = client.patch(
        f"/api/v1/admin/users/{admin_id}",
        json={"role": "viewer"},
        headers=headers("admin2", "motdepasse-a-123"),
    )
    assert r.status_code == 200

    # admin2 est maintenant le DERNIER admin actif :
    # personne ne peut le rétrograder/désactiver (ici : lui-même → self-guard,
    # et le guard dernier-admin le protège aussi de toute autre voie)
    r = client.patch(
        f"/api/v1/admin/users/{admin2_id}",
        json={"role": "viewer"},
        headers=headers("admin2", "motdepasse-a-123"),
    )
    assert r.status_code == 400


def test_delete_user_removes_permissions():
    # créer un user avec une permission
    r = client.post(
        "/api/v1/admin/users",
        json={"username": "ephemere", "email": "e@test.fr",
              "password": "motdepasse-e-123"},
        headers=headers("admin"),
    )
    user_id = r.json()["id"]

    client.post(
        f"/api/v1/admin/users/{user_id}/permissions",
        json={"source_name": "Polytech", "scopes": ["read:competence"]},
        headers=headers("admin"),
    )

    r = client.delete(f"/api/v1/admin/users/{user_id}", headers=headers("admin"))
    assert r.status_code == 200
    assert r.json()["permissions_deleted"] == 1

    # login impossible, permissions purgées
    r = client.post("/api/v1/auth/login",
                    data={"username": "ephemere",
                          "password": "motdepasse-e-123"})
    assert r.status_code == 401

    db = SessionLocal()
    remaining = db.query(Permission).filter(
        Permission.subject_type == SUBJECT_USER,
        Permission.subject_id == user_id,
    ).count()
    db.close()
    assert remaining == 0


def test_patch_unknown_user_404():
    r = client.patch("/api/v1/admin/users/9999", json={"role": "viewer"},
                     headers=headers("admin"))
    assert r.status_code == 404


# =====================================================
# Permissions par source
# =====================================================

def viewer_id():
    db = SessionLocal()
    uid = db.query(User).filter(User.username == "viewer").first().id
    db.close()
    return uid


def test_admin_can_grant_source_permission():
    uid = viewer_id()
    r = client.post(
        f"/api/v1/admin/users/{uid}/permissions",
        json={"source_name": "Polytech",
              "scopes": ["read:competence", "read:curriculum",
                         "read:analytics"]},
        headers=headers("admin"),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["source_name"] == "Polytech"
    assert body["subject_type"] == "user"
    assert body["subject_id"] == uid
    # AUCUN programme_id nulle part (décision métier v1)
    assert "programme_id" not in body


def test_admin_can_grant_wildcard_source():
    uid = viewer_id()
    r = client.post(
        f"/api/v1/admin/users/{uid}/permissions",
        json={"source_name": "*", "scopes": ["*"]},
        headers=headers("admin"),
    )
    assert r.status_code == 201
    assert r.json()["source_name"] == "*"


def test_admin_can_list_user_permissions():
    uid = viewer_id()
    client.post(
        f"/api/v1/admin/users/{uid}/permissions",
        json={"source_name": "BUT", "scopes": ["read:competence"]},
        headers=headers("admin"),
    )
    r = client.get(f"/api/v1/admin/users/{uid}/permissions",
                   headers=headers("admin"))
    assert r.status_code == 200
    sources = [p["source_name"] for p in r.json()]
    assert "BUT" in sources


def test_upsert_same_source_case_insensitive():
    uid = viewer_id()
    client.post(
        f"/api/v1/admin/users/{uid}/permissions",
        json={"source_name": "Polytech", "scopes": ["read:competence"]},
        headers=headers("admin"),
    )
    # même source en casse différente → mise à jour, pas de doublon
    r = client.post(
        f"/api/v1/admin/users/{uid}/permissions",
        json={"source_name": "POLYTECH",
              "scopes": ["read:competence", "read:curriculum"]},
        headers=headers("admin"),
    )
    assert r.status_code == 201
    assert set(r.json()["scopes"]) == {"read:competence", "read:curriculum"}

    r = client.get(f"/api/v1/admin/users/{uid}/permissions",
                   headers=headers("admin"))
    polytech_perms = [p for p in r.json()
                      if p["source_name"].lower() == "polytech"]
    assert len(polytech_perms) == 1


def test_unknown_scope_rejected():
    uid = viewer_id()
    r = client.post(
        f"/api/v1/admin/users/{uid}/permissions",
        json={"source_name": "BUT", "scopes": ["read:inconnu"]},
        headers=headers("admin"),
    )
    assert r.status_code == 422


def test_admin_can_delete_permission():
    uid = viewer_id()
    r = client.post(
        f"/api/v1/admin/users/{uid}/permissions",
        json={"source_name": "BUT", "scopes": ["read:competence"]},
        headers=headers("admin"),
    )
    perm_id = r.json()["id"]

    r = client.delete(f"/api/v1/admin/permissions/{perm_id}",
                      headers=headers("admin"))
    assert r.status_code == 200

    r = client.delete(f"/api/v1/admin/permissions/{perm_id}",
                      headers=headers("admin"))
    assert r.status_code == 404


# =====================================================
# Intégration : la permission accordée filtre bien les données
# =====================================================

def test_granted_viewer_sees_only_polytech():
    uid = viewer_id()
    client.post(
        f"/api/v1/admin/users/{uid}/permissions",
        json={"source_name": "polytech",  # casse volontairement différente
              "scopes": ["read:competence"]},
        headers=headers("admin"),
    )

    r = client.get("/api/v1/competences", headers=headers("viewer"))
    assert r.status_code == 200
    sources = sorted({i["source"] for i in r.json()["data"]})
    assert sources == ["Polytech"]  # jamais BUT


def test_viewer_without_grant_sees_nothing():
    r = client.get("/api/v1/competences", headers=headers("viewer"))
    assert r.json()["status"] == "empty"