"""
Tests Patch 6.1 — upload de fichiers sources par l'admin.

POST /admin/sources/upload : validations, sécurité, traitement du SEUL
fichier uploadé, non-régression des autres outputs.

Lancer depuis backend_python :
    python -m pytest tests/test_upload_phase6.py -v
"""

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.auth.routes_admin_upload as upload_module
import app.etl.pipeline as pipeline_module
from app.auth.database import Base, SessionLocal, engine
from app.auth.models import ROLE_ADMIN, ROLE_VIEWER, User
from app.auth.security import hash_password
from app.main import app

client = TestClient(app)

PASSWORD = "motdepasse-test-123"
TEST_ROOT = Path("./test_data_phase6").resolve()
RAW = TEST_ROOT / "raw"
PROCESSED = TEST_ROOT / "processed"
ANALYTICS = TEST_ROOT / "analytics"


def polytech_competence_json() -> bytes:
    """Export phpMyAdmin minimal au NOUVEAU format (accepté par le
    PolytechCompetenceNormalizer + PolytechTransformer)."""
    row = {
        "code_competence": "COMP_SNI1",
        "id_competence": "1",
        "libelle_competence": "Concevoir des systèmes numériques",
        "code_ce": "COMP_SNI1_CE1",
        "libelle_composante_essentielle": "En autonomie",
        "code_niveau": "COMP_SNI1_N1",
        "niveau": "1",
        "code_ac": "COMP_SNI1_N1_AC1",
        "libelle_apprentissage": "Concevoir une base de données (INFO502)",
        "code_module": "INFO502_SNI",
        "nom": "Bases de données",
        "ects": "2", "hCM": "6", "hTD": "4", "hTP": "10",
        "IFNULL(MAQUETTE_module.hPROJ,0)": "0",
        "learning_unit_code": "UE502",
        "learning_unit_name": "Sciences",
        "nom_filiere": "SNI", "nom_statut": "FISE", "annee": "3",
    }
    export = [
        {"type": "header", "version": "5", "comment": ""},
        {"type": "database", "name": "test"},
        {"type": "table", "name": "APC_competence",
         "database": "test", "data": [row]},
    ]
    return json.dumps(export).encode("utf-8")


@pytest.fixture(autouse=True)
def data_dirs(monkeypatch):
    """Arborescence data isolée + redirection des constantes de chemins."""
    shutil.rmtree(TEST_ROOT, ignore_errors=True)
    for folder in (RAW, PROCESSED, ANALYTICS):
        folder.mkdir(parents=True, exist_ok=True)

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
    r = client.post("/auth/login",
                    data={"username": username, "password": PASSWORD})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def do_upload(headers=None, domain="competence", source="Polytech",
              formation="SNI", filename="referentiel.json", content=None):
    return client.post(
        "/admin/sources/upload",
        data={"domain": domain, "source_name": source,
              "formation_name": formation},
        files={"file": (filename,
                        content if content is not None
                        else polytech_competence_json(),
                        "application/json")},
        headers=headers if headers is not None else get_headers(),
    )


# =====================================================
# Cas nominal + isolation stricte
# =====================================================

def test_upload_success_creates_only_its_outputs():
    # Marqueurs pré-existants : outputs BUT (autre source) et curriculum
    # (autre domaine) qui ne doivent PAS être modifiés.
    but_processed = PROCESSED / "competence" / "BUT" / "QLIO_x_processed.json"
    but_processed.parent.mkdir(parents=True, exist_ok=True)
    but_processed.write_text('{"marqueur": "intact"}', encoding="utf-8")

    curr_processed = PROCESSED / "curriculum" / "Polytech" / "IDU_x_processed.json"
    curr_processed.parent.mkdir(parents=True, exist_ok=True)
    curr_processed.write_text('{"marqueur": "intact2"}', encoding="utf-8")

    r = do_upload(filename="referentiel export.json")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "success"
    # nom nettoyé : FORMATION_{nom sans espaces}
    assert body["file"] == "competence/Polytech/SNI_referentiel_export.json"

    # fichier brut sauvegardé
    saved = RAW / "competence" / "Polytech" / "SNI_referentiel_export.json"
    assert saved.exists()

    # outputs générés UNIQUEMENT pour ce fichier
    processed = (PROCESSED / "competence" / "Polytech"
                 / "SNI_referentiel_export_processed.json")
    analytics = (ANALYTICS / "competence" / "Polytech"
                 / "SNI_referentiel_export_flat.json")
    assert processed.exists()
    assert analytics.exists()

    data = json.loads(processed.read_text(encoding="utf-8"))
    assert data["sous_classifications"][0]["competences"][0]["code"] == "COMP_SNI1"

    # NON-RÉGRESSION : les marqueurs des autres source/domaine sont intacts
    assert but_processed.read_text(encoding="utf-8") == '{"marqueur": "intact"}'
    assert curr_processed.read_text(encoding="utf-8") == '{"marqueur": "intact2"}'
    # et aucun nouveau fichier n'est apparu chez eux
    assert len(list(but_processed.parent.iterdir())) == 1
    assert len(list(curr_processed.parent.iterdir())) == 1


# =====================================================
# Sécurité d'accès
# =====================================================

def test_upload_requires_auth():
    r = do_upload(headers={})
    assert r.status_code == 401


def test_viewer_forbidden():
    r = do_upload(headers=get_headers("viewer"))
    assert r.status_code == 403


def test_api_key_forbidden():
    created = client.post(
        "/admin/api-keys",
        json={"name": "cle", "permissions": [
            {"source_name": "*", "scopes": ["*"]}]},
        headers=get_headers(),
    ).json()
    r = do_upload(headers={"X-API-Key": created["api_key"]})
    assert r.status_code == 403


# =====================================================
# Validations
# =====================================================

def test_unknown_domain_rejected():
    r = do_upload(domain="inconnu")
    assert r.status_code == 400


def test_bad_extension_rejected():
    r = do_upload(filename="script.txt", content=b"hello")
    assert r.status_code == 400
    assert "Extension" in r.json()["detail"]


def test_path_traversal_in_formation_rejected():
    for bad in ("../evil", "..", "a/b", "a\\b", ".hidden", ""):
        r = do_upload(formation=bad)
        assert r.status_code in (400, 422), bad
    # rien n'a été écrit hors cible
    assert not (RAW.parent / "evil_referentiel.json").exists()


def test_path_traversal_in_source_rejected():
    r = do_upload(source="../../etc")
    assert r.status_code == 400


def test_empty_file_rejected():
    r = do_upload(content=b"")
    assert r.status_code == 400


def test_duplicate_file_conflict():
    assert do_upload().status_code == 200
    r = do_upload()  # même nom final
    assert r.status_code == 409
    assert "existe déjà" in r.json()["detail"]


# =====================================================
# Rejet pipeline -> 422 + raw nettoyé
# =====================================================

def test_invalid_content_422_and_raw_cleaned():
    r = do_upload(formation="BAD",
                  content=json.dumps({"pas": "un export"}).encode())
    assert r.status_code == 422
    assert "pipeline" in r.json()["detail"].lower()

    # le fichier cassé n'est PAS resté dans raw/
    leftover = RAW / "competence" / "Polytech" / "BAD_referentiel.json"
    assert not leftover.exists()
    # et aucun output n'a été créé
    assert not (PROCESSED / "competence" / "Polytech"
                / "BAD_referentiel_processed.json").exists()


def test_no_source_registered_422_and_cleaned():
    # curriculum/SourceInconnue : TransformerFactory ne connaît pas
    r = do_upload(domain="curriculum", source="SourceInconnue",
                  formation="X",
                  content=json.dumps({"fiches": []}).encode())
    assert r.status_code == 422
    assert not (RAW / "curriculum" / "SourceInconnue"
                / "X_referentiel.json").exists()