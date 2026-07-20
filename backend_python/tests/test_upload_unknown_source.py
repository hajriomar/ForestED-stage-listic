"""
Tests R1 (intégration) — upload/import API vers une source INCONNUE du
pipeline : erreur propre (422) + fichier raw nettoyé.

Contexte : depuis la Phase 6, l'admin peut saisir un source_name libre.
Avec la registry R1, le pipeline lève un ValueError explicite ; les
routes upload/import doivent continuer à répondre 422 et à supprimer
le fichier raw (aucun résidu).

Lancer depuis backend_python :
    python -m pytest tests/test_upload_unknown_source.py -v
"""

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.auth.admin_api_import_service as service
import app.auth.routes_admin_upload as upload_module
import app.etl.pipeline as pipeline_module
from app.auth.database import Base, SessionLocal, engine
from app.auth.models import ROLE_ADMIN, User
from app.auth.security import hash_password
from app.main import app

client = TestClient(app)

PASSWORD = "motdepasse-test-123"
TEST_ROOT = Path("./test_data_unknown_source").resolve()
RAW = TEST_ROOT / "raw"
PROCESSED = TEST_ROOT / "processed"
ANALYTICS = TEST_ROOT / "analytics"

PUBLIC_URL = "https://93.184.216.34/api/data"


@pytest.fixture(autouse=True)
def data_dirs(monkeypatch):
    shutil.rmtree(TEST_ROOT, ignore_errors=True)
    for folder in (RAW, PROCESSED, ANALYTICS):
        folder.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(service, "RAW_DATA_FOLDER", str(RAW))
    monkeypatch.setattr(upload_module, "RAW_DATA_FOLDER", str(RAW))
    monkeypatch.setattr(pipeline_module, "PROCESSED_FOLDER", str(PROCESSED))
    monkeypatch.setattr(pipeline_module, "ANALYTICS_FOLDER", str(ANALYTICS))
    yield
    shutil.rmtree(TEST_ROOT, ignore_errors=True)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.add(User(username="admin", email="admin@test.fr",
                hashed_password=hash_password(PASSWORD), role=ROLE_ADMIN))
    db.commit()
    db.close()
    yield


def get_headers():
    r = client.post("/api/v1/auth/login",
                    data={"username": "admin", "password": PASSWORD})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def valid_json_payload() -> bytes:
    return json.dumps({"fiches": [{"code": "XX101", "nom": "Module X"}]}).encode()


# =====================================================
# Upload fichier vers une source inconnue du pipeline
# =====================================================

def test_upload_unknown_source_422_and_raw_cleaned():
    r = client.post(
        "/api/v1/admin/sources/upload",
        data={"domain": "curriculum", "source_name": "UNITA",
              "formation_name": "TEST"},
        files={"file": ("ref.json", valid_json_payload(),
                        "application/json")},
        headers=get_headers(),
    )
    assert r.status_code == 422, r.text
    # Message explicite de la registry remonté à l'admin
    assert "No transformer registered" in r.json()["detail"] \
        or "pipeline" in r.json()["detail"].lower()
    # Aucun résidu : le raw a été nettoyé
    assert not (RAW / "curriculum" / "UNITA" / "TEST_ref.json").exists()
    # Rien n'a été produit
    assert not list(PROCESSED.rglob("*.json"))
    assert not list(ANALYTICS.rglob("*.json"))


# =====================================================
# Import API vers une source inconnue du pipeline
# =====================================================

@pytest.fixture
def stub_fetch(monkeypatch):
    def fake_fetch(url, headers=None, **kwargs):
        return valid_json_payload()
    monkeypatch.setattr(service, "fetch_json_from_api", fake_fetch)


def test_import_api_unknown_source_422_and_raw_cleaned(stub_fetch):
    r = client.post(
        "/api/v1/admin/sources/import-api",
        json={"domain": "curriculum", "source_name": "UNITA",
              "formation_name": "TEST", "url": PUBLIC_URL,
              "output_filename": "export.json"},
        headers=get_headers(),
    )
    assert r.status_code == 422, r.text
    assert not (RAW / "curriculum" / "UNITA" / "TEST_export.json").exists()


# =====================================================
# Non-régression : une source CONNUE fonctionne toujours
# =====================================================

def test_upload_known_source_still_works():
    row = {
        "code_competence": "COMP_IDU1", "id_competence": "1",
        "libelle_competence": "Concevoir",
        "code_ce": "COMP_IDU1_CE1",
        "libelle_composante_essentielle": "En autonomie",
        "code_niveau": "COMP_IDU1_N1", "niveau": "1",
        "code_ac": "COMP_IDU1_N1_AC1",
        "libelle_apprentissage": "Concevoir une BD (INFO502)",
        "code_module": "INFO502_IDU", "nom": "BD", "ects": "2",
        "hCM": "6", "hTD": "4", "hTP": "10",
        "IFNULL(MAQUETTE_module.hPROJ,0)": "0",
        "learning_unit_code": "UE502", "learning_unit_name": "Sciences",
        "nom_filiere": "IDU", "nom_statut": "FISE", "annee": "3",
    }
    payload = json.dumps([
        {"type": "header", "version": "5", "comment": ""},
        {"type": "database", "name": "test"},
        {"type": "table", "name": "APC_competence",
         "database": "test", "data": [row]},
    ]).encode()

    r = client.post(
        "/api/v1/admin/sources/upload",
        data={"domain": "competence", "source_name": "Polytech",
              "formation_name": "IDU"},
        files={"file": ("ref.json", payload, "application/json")},
        headers=get_headers(),
    )
    assert r.status_code == 200, r.text
    assert (RAW / "competence" / "Polytech" / "IDU_ref.json").exists()
    assert (PROCESSED / "competence" / "Polytech"
            / "IDU_ref_processed.json").exists()
