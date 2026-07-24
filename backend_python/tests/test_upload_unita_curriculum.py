# -*- coding: utf-8 -*-
"""
Tests U5-FRONT (backend) — upload admin curriculum UNITA multi-institution.

Vérifie le flux réel via l'API :
    POST /admin/sources/upload (curriculum/unita)
        -> extract -> normalize -> transform -> CurriculumUpsertService
        -> data/processed/curriculum/unita/JB_SCRL_processed.json

- import JSON générique -> processed contient le générique (aucune institution) ;
- import Excel USMB      -> processed contient générique + USMB ;
- réimport USMB (autre nom de fichier) -> idempotent (aucun ajout) ;
- un upload non-UNITA (Polytech competence) continue de fonctionner.

Lancer depuis backend_python :
    python -m pytest tests/test_upload_unita_curriculum.py -v
"""

import json
import shutil
from collections import Counter
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.auth.routes_admin_upload as upload_module
import app.etl.pipeline as pipeline_module
from app.auth.database import Base, SessionLocal, engine
from app.auth.models import ROLE_ADMIN, User
from app.auth.security import hash_password
from app.main import app

client = TestClient(app)

PASSWORD = "motdepasse-test-123"
TEST_ROOT = Path("./test_data_u5").resolve()
RAW = TEST_ROOT / "raw"
PROCESSED = TEST_ROOT / "processed"
ANALYTICS = TEST_ROOT / "analytics"

_FIX = Path(__file__).parent / "fixtures"
_GENERIC = _FIX / "JB_SCRL_curriculum_generic.json"
_EXCEL = _FIX / "MAQUETTE_JD_JUILLET_26.xlsx"

_PROCESSED_UNITA = PROCESSED / "curriculum" / "unita" / "JB_SCRL_processed.json"


@pytest.fixture(autouse=True)
def data_dirs(monkeypatch):
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
    db.add(User(username="admin", email="admin@test.fr",
                hashed_password=hash_password(PASSWORD), role=ROLE_ADMIN))
    db.commit()
    db.close()
    yield


def _headers():
    r = client.post("/api/v1/auth/login",
                    data={"username": "admin", "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _upload(source, formation, filename, content, ctype):
    return client.post(
        "/api/v1/admin/sources/upload",
        data={"domain": "curriculum", "source_name": source,
              "formation_name": formation},
        files={"file": (filename, content, ctype)},
        headers=_headers(),
    )


def _scope_counts():
    p = json.loads(_PROCESSED_UNITA.read_text(encoding="utf-8"))
    return Counter(r["scope"] for r in p["elements"].values())


# ---------------------------------------------------------------------------

def test_import_generic_then_usmb_via_api():
    if not _GENERIC.exists() or not _EXCEL.exists():
        pytest.skip("fixtures UNITA absentes")

    # 1) JSON générique -> aucune institution
    r1 = _upload("unita", "GEN", "JB_SCRL_curriculum_generic.json",
                 _GENERIC.read_bytes(), "application/json")
    assert r1.status_code == 200, r1.text
    b1 = r1.json()
    assert b1["status"] == "success"
    assert b1["scopes"] == ["generic"]
    assert b1["institutions"] == []
    assert _PROCESSED_UNITA.exists()
    assert _scope_counts()["generic"] == 10

    # 2) Excel USMB -> générique + USMB
    r2 = _upload("unita", "USMB", "MAQUETTE_JD_JUILLET_26.xlsx",
                 _EXCEL.read_bytes(),
                 "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    assert r2.status_code == 200, r2.text
    b2 = r2.json()
    assert b2["institutions"] == ["USMB"]
    assert b2["added"] > 20
    c = _scope_counts()
    assert c["generic"] == 10 and c["institution_specific"] > 20


def test_reimport_usmb_is_idempotent_via_api():
    if not _EXCEL.exists():
        pytest.skip("fixture Excel absente")
    xls = _EXCEL.read_bytes()
    a = _upload("unita", "USMBA", "MAQUETTE_JD_JUILLET_26.xlsx", xls,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    assert a.status_code == 200, a.text
    total1 = a.json()["total_elements"]
    # réimport du MÊME contenu (autre nom de formation -> pas de 409) :
    # mêmes upsert_key -> que des updates, total stable.
    b = _upload("unita", "USMBB", "MAQUETTE_JD_JUILLET_26.xlsx", xls,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    assert b.status_code == 200, b.text
    assert b.json()["added"] == 0
    assert b.json()["total_elements"] == total1


def test_non_unita_upload_still_works():
    # Polytech competence (autre domaine/source) : réponse historique,
    # pas de champs d'upsert curriculum.
    row = {
        "code_competence": "COMP_SNI1", "id_competence": "1",
        "libelle_competence": "Concevoir des systèmes numériques",
        "code_ce": "COMP_SNI1_CE1",
        "libelle_composante_essentielle": "En autonomie",
        "code_niveau": "COMP_SNI1_N1", "niveau": "1",
        "code_ac": "COMP_SNI1_N1_AC1",
        "libelle_apprentissage": "Concevoir une base de données (INFO502)",
        "code_module": "INFO502_SNI", "nom": "Bases de données",
        "ects": "2", "hCM": "6", "hTD": "4", "hTP": "10",
        "IFNULL(MAQUETTE_module.hPROJ,0)": "0",
        "learning_unit_code": "UE502", "learning_unit_name": "Sciences",
        "nom_filiere": "SNI", "nom_statut": "FISE", "annee": "3",
    }
    export = [
        {"type": "header", "version": "5", "comment": ""},
        {"type": "database", "name": "test"},
        {"type": "table", "name": "APC_competence",
         "database": "test", "data": [row]},
    ]
    r = client.post(
        "/api/v1/admin/sources/upload",
        data={"domain": "competence", "source_name": "Polytech",
              "formation_name": "SNI"},
        files={"file": ("referentiel.json",
                        json.dumps(export).encode("utf-8"), "application/json")},
        headers=_headers(),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "success"
    assert "added" not in body        # pas d'upsert pour les non-UNITA
