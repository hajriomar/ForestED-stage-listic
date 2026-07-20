"""
Tests Phase 2 — permissions par source, protection pipeline, filtrage data.

Lancer depuis backend_python :
    python -m pytest tests/test_permissions_phase2.py -v

Les dossiers de données sont patchés par test (monkeypatch) pour être
indépendants de l'ordre d'exécution de la suite complète.
"""

import json
import os
import shutil
from pathlib import Path

# Base de test isolée — définie avant tout import app.* (exécution standalone).
# setdefault : si une autre suite a déjà importé l'app, on garde sa base test.
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_auth_phase2.db")

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
from app.auth.permissions import can_access
from app.auth.security import hash_password
from app.main import app

client = TestClient(app)

PASSWORD = "motdepasse-test-123"
TEST_DATA = Path("./test_data_phase2").resolve()


def _write(path: Path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content), encoding="utf-8")


@pytest.fixture(scope="module", autouse=True)
def data_tree():
    """Arborescence processed/analytics avec 2 sources (casse mixte)."""
    shutil.rmtree(TEST_DATA, ignore_errors=True)
    processed = TEST_DATA / "processed"
    analytics = TEST_DATA / "analytics"

    _write(processed / "competence" / "BUT" / "QLIO_BUT_ref_processed.json",
           {"intitule": "Ref BUT QLIO"})
    _write(processed / "competence" / "Polytech" / "IDU_polytech_processed.json",
           {"intitule": "Ref Polytech IDU"})
    _write(processed / "curriculum" / "BUT" / "QLIO_BUT_curr_processed.json",
           {"id": "BUT_QLIO", "nom": "BUT QLIO"})
    _write(analytics / "competence" / "Polytech" / "IDU_polytech_flat.json",
           [{"row": 1}])
    yield
    shutil.rmtree(TEST_DATA, ignore_errors=True)


@pytest.fixture(autouse=True)
def patch_data_folders(monkeypatch):
    """Redirige les dossiers data de l'app vers l'arborescence de test.

    Patch des globals du module main (lus à chaque requête) : fiable
    quel que soit l'ordre d'import des suites de tests.
    """
    monkeypatch.setattr(
        main_module, "PROCESSED_DATA_FOLDER", str(TEST_DATA / "processed")
    )
    monkeypatch.setattr(
        main_module, "ANALYTICS_DATA_FOLDER", str(TEST_DATA / "analytics")
    )


@pytest.fixture(autouse=True)
def setup_db():
    """Users : admin, viewer_polytech, viewer_but, viewer_star, viewer_rien."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    def add_user(username, role=ROLE_VIEWER):
        u = User(
            username=username,
            email=f"{username}@test.fr",
            hashed_password=hash_password(PASSWORD),
            role=role,
        )
        db.add(u)
        db.flush()
        return u

    add_user("admin", ROLE_ADMIN)
    v_poly = add_user("viewer_polytech")
    v_but = add_user("viewer_but")
    v_star = add_user("viewer_star")
    add_user("viewer_rien")
    v_curr = add_user("viewer_curriculum_only")

    def grant(user, source, scopes):
        db.add(Permission(
            subject_type=SUBJECT_USER,
            subject_id=user.id,
            source_name=source,
            scopes=scopes,
        ))

    # casse volontairement différente des dossiers (BUT / Polytech)
    grant(v_poly, "polytech",
          ["read:competence", "read:curriculum", "read:analytics"])
    grant(v_but, "but",
          ["read:competence", "read:curriculum", "read:analytics"])
    grant(v_star, "*", ["*"])
    grant(v_curr, "BUT", ["read:curriculum"])

    db.commit()
    db.close()
    yield


def get_token(username):
    r = client.post(
        "/api/v1/auth/login",
        data={"username": username, "password": PASSWORD},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth_get(path, username):
    return client.get(
        path, headers={"Authorization": f"Bearer {get_token(username)}"}
    )


def sources_of(response):
    body = response.json()
    return sorted({i["source"] for i in body.get("data", [])})


# =====================================================
# can_access (unitaires)
# =====================================================

class FakePerm:
    def __init__(self, source, scopes):
        self.source_name = source
        self.scopes = scopes


def test_can_access_admin_bypass():
    assert can_access([], "nimporte", "read:competence", is_admin=True)


def test_can_access_source_case_insensitive():
    perms = [FakePerm("Polytech", ["read:competence"])]
    assert can_access(perms, "polytech", "read:competence")
    assert can_access(perms, "POLYTECH", "read:competence")
    assert not can_access(perms, "but", "read:competence")


def test_can_access_wildcard_source_and_scope():
    perms = [FakePerm("*", ["*"])]
    assert can_access(perms, "Licence", "read:analytics")


def test_can_access_missing_scope():
    perms = [FakePerm("BUT", ["read:curriculum"])]
    assert not can_access(perms, "BUT", "read:competence")
    assert can_access(perms, "BUT", "read:curriculum")


def test_can_access_no_permission():
    assert not can_access([], "BUT", "read:competence")


# =====================================================
# Endpoints data — filtrage par source
# =====================================================

def test_data_requires_auth():
    for path in ("/api/v1/competences", "/api/v1/curricula", "/api/v1/analytics/competence"):
        assert client.get(path).status_code == 401


def test_admin_sees_everything():
    r = auth_get("/api/v1/competences", "admin")
    assert r.status_code == 200
    assert sources_of(r) == ["BUT", "Polytech"]


def test_viewer_polytech_sees_only_polytech():
    r = auth_get("/api/v1/competences", "viewer_polytech")
    assert r.status_code == 200
    assert sources_of(r) == ["Polytech"]


def test_viewer_but_sees_only_but():
    r = auth_get("/api/v1/competences", "viewer_but")
    assert sources_of(r) == ["BUT"]


def test_viewer_star_sees_everything():
    r = auth_get("/api/v1/competences", "viewer_star")
    assert sources_of(r) == ["BUT", "Polytech"]


def test_viewer_without_permission_sees_nothing():
    r = auth_get("/api/v1/competences", "viewer_rien")
    assert r.status_code == 200
    assert r.json()["status"] == "empty"
    assert r.json()["data"] == []


def test_scope_filtering_curriculum_only():
    # A le droit curriculum sur BUT, mais pas competence
    r = auth_get("/api/v1/competences", "viewer_curriculum_only")
    assert r.json()["status"] == "empty"

    r = auth_get("/api/v1/curricula", "viewer_curriculum_only")
    assert sources_of(r) == ["BUT"]


def test_analytics_filtering():
    # Le dossier analytics de test ne contient QUE Polytech
    r = auth_get("/api/v1/analytics/competence", "viewer_polytech")
    assert sources_of(r) == ["Polytech"]

    r = auth_get("/api/v1/analytics/competence", "viewer_but")
    assert r.json()["status"] == "empty"


# =====================================================
# Pipeline — admin uniquement
# =====================================================

def test_pipeline_requires_auth():
    assert client.post("/api/v1/pipeline/run").status_code == 401


def test_pipeline_forbidden_for_viewer():
    r = client.post(
        "/api/v1/pipeline/run",
        headers={"Authorization": f"Bearer {get_token('viewer_star')}"},
    )
    assert r.status_code == 403


def test_pipeline_allowed_for_admin(monkeypatch):
    called = {}
    monkeypatch.setattr(main_module, "run_pipeline", lambda: called.setdefault("ok", True))
    r = client.post(
        "/api/v1/pipeline/run",
        headers={"Authorization": f"Bearer {get_token('admin')}"},
    )
    assert r.status_code == 200
    assert called.get("ok") is True


def test_pipeline_domain_forbidden_for_viewer():
    r = client.post(
        "/api/v1/pipeline/domain/competence",
        headers={"Authorization": f"Bearer {get_token('viewer_polytech')}"},
    )
    assert r.status_code == 403


# =====================================================
# Non-régression
# =====================================================

def test_health_still_public():
    assert client.get("/health").status_code == 200