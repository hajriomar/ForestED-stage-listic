# -*- coding: utf-8 -*-
"""
Tests Patch 5 (UI) — GET /admin/sources/supported.

La route expose les sources qui ont un transformer (registry R1),
pour alimenter le dropdown d'upload de la page admin.

Lancer depuis backend_python :
    python -m pytest tests/test_supported_sources.py -v
"""

import pytest
from fastapi.testclient import TestClient

from app.auth.database import Base, SessionLocal, engine
from app.auth.models import ROLE_ADMIN, ROLE_VIEWER, User
from app.auth.security import hash_password
from app.main import app

client = TestClient(app)
PASSWORD = "motdepasse-test-123"


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


def get_headers(username="admin"):
    r = client.post("/api/v1/auth/login",
                    data={"username": username, "password": PASSWORD})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_admin_liste_les_sources_supportees():
    r = client.get("/api/v1/admin/sources/supported", headers=get_headers())
    assert r.status_code == 200, r.text
    body = r.json()
    # Union des sources de la registry (dont usmb_licence, SANS données)
    assert "usmb_licence" in body["sources"]
    assert "but" in body["sources"]
    assert "polytech" in body["sources"]
    # Détail par domaine : competence (v1) ET curriculum lite (v2/C3)
    assert "usmb_licence" in body["by_domain"]["competence"]
    assert "usmb_licence" in body["by_domain"]["curriculum"]


def test_viewer_forbidden():
    r = client.get("/api/v1/admin/sources/supported",
                   headers=get_headers("viewer"))
    assert r.status_code == 403


def test_sans_token_401():
    assert client.get("/api/v1/admin/sources/supported").status_code == 401


def test_coherent_avec_la_factory():
    from app.etl.transform.transformer_factory import TransformerFactory
    body = client.get("/api/v1/admin/sources/supported",
                      headers=get_headers()).json()
    expected = sorted({k.split("/")[1]
                       for k in TransformerFactory.known_sources()})
    assert body["sources"] == expected