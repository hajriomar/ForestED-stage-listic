# -*- coding: utf-8 -*-
"""
Tests Patch 4 (USMB v1) — intégration pipeline + registry.

Vérifie :
- registry : competence/usmb_licence retourne les bonnes classes,
  curriculum/usmb_licence reste NON supporté en v1 (422) ;
- upload d'un xlsx gabarit USMB -> 200, raw + processed + analytics
  + *_quality.json générés ;
- upload d'un xlsx hors gabarit (cas MATH) -> 422 message clair,
  raw nettoyé ;
- non-régression : source inconnue toujours 422 propre.

Lancer depuis backend_python :
    python -m pytest tests/test_usmb_licence_pipeline.py -v
"""

import io
import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

import app.auth.routes_admin_upload as upload_module
import app.etl.pipeline as pipeline_module
from app.auth.database import Base, SessionLocal, engine
from app.auth.models import ROLE_ADMIN, User
from app.auth.security import hash_password
from app.etl.normalize.normalizer_factory import NormalizerFactory
from app.etl.transform.transformer_factory import TransformerFactory
from app.main import app

client = TestClient(app)

PASSWORD = "motdepasse-test-123"
TEST_ROOT = Path("./test_data_usmb_pipeline").resolve()
RAW = TEST_ROOT / "raw"
PROCESSED = TEST_ROOT / "processed"
ANALYTICS = TEST_ROOT / "analytics"


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


def get_headers():
    r = client.post("/api/v1/auth/login",
                    data={"username": "admin", "password": PASSWORD})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# =====================================================
# Fabriques de classeurs
# =====================================================

def usmb_xlsx_bytes() -> bytes:
    """Classeur au gabarit USMB minimal (1 compétence, 3 AC, 4 liens)."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Compétence 1"
    ws["A1"] = "Titre de la compétence"
    ws["A2"] = "Résoudre un problème juridique en situation"
    ws["D1"] = "Composantes essentielles"
    ws["D2"] = "• en identifiant les règles applicables"
    ws["G1"] = "N° Fiche RNCP"
    ws["H1"] = "RNCP38186"
    ws["A9"] = "Niveaux de dévéloppement"
    ws["B9"] = "Acquis d'apprentissage (ou apprentissages critiques)"
    ws["C10"] = "période 1"
    ws["E10"] = "période 2"
    ws["C11"] = "UAF101"
    ws["E11"] = "UAF201"
    ws["C12"] = "DROIT101_TEST"
    ws["D12"] = "Introduction au droit privé"
    ws["E12"] = "DROIT201_TEST"
    ws["A13"] = "Niveau 1 : \nIdentifier les concepts"
    ws["B13"] = "• Comprendre le sens d'un énoncé"
    ws["C13"] = "x"
    ws["D13"] = "x"
    ws["B14"] = "• Qualifier juridiquement une situation"
    ws["C14"] = "x"
    ws["A15"] = "Niveau 2 : \nArticuler les concepts"
    ws["B15"] = "• Saisir l'esprit de la règle"
    ws["E15"] = "x"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def math_like_xlsx_bytes() -> bytes:
    """Classeur hors gabarit (cas MATH : pas de matrice AC×EC)."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Compétences MATH"
    ws["A2"] = "Produire un raisonnement mathématique"
    ws["A9"] = "Composantes essentielles"
    ws["A18"] = "Produire un raisonnement élémentaire"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# =====================================================
# Registry
# =====================================================

def test_registry_competence_usmb_licence():
    from app.etl.normalize.usmb_licence_competence_normalizer import (
        USMBLicenceCompetenceNormalizer,
    )
    from app.etl.transform.competence.USMB_licence_competence_transformer import (
        USMBLicenceCompetenceTransformer,
    )
    assert isinstance(
        NormalizerFactory.get_normalizer("competence", "USMB_Licence"),
        USMBLicenceCompetenceNormalizer)
    assert isinstance(
        TransformerFactory.get_transformer("competence", "usmb_licence"),
        USMBLicenceCompetenceTransformer)


def test_registry_curriculum_usmb_licence_supporte_v2():
    """Depuis C3, le domaine curriculum est supporté (curriculum lite) —
    avec le MÊME normalizer que le domaine competence."""
    from app.etl.normalize.usmb_licence_competence_normalizer import (
        USMBLicenceCompetenceNormalizer,
    )
    from app.etl.transform.curriculum.USMB_licence_curriculum_transformer import (
        USMBLicenceCurriculumTransformer,
    )
    assert isinstance(
        NormalizerFactory.get_normalizer("curriculum", "usmb_licence"),
        USMBLicenceCompetenceNormalizer)
    assert isinstance(
        TransformerFactory.get_transformer("curriculum", "usmb_licence"),
        USMBLicenceCurriculumTransformer)


def test_known_sources_contient_usmb():
    assert "competence/usmb_licence" in TransformerFactory.known_sources()
    assert "curriculum/usmb_licence" in TransformerFactory.known_sources()


# =====================================================
# Upload bout-en-bout
# =====================================================

def test_upload_usmb_200_et_fichiers_generes():
    r = client.post(
        "/api/v1/admin/sources/upload",
        data={"domain": "competence", "source_name": "usmb_licence",
              "formation_name": "DROIT"},
        files={"file": ("ref.xlsx", usmb_xlsx_bytes(),
                        "application/vnd.openxmlformats-officedocument"
                        ".spreadsheetml.sheet")},
        headers=get_headers(),
    )
    assert r.status_code == 200, r.text

    raw = RAW / "competence" / "usmb_licence" / "DROIT_ref.xlsx"
    processed = (PROCESSED / "competence" / "usmb_licence"
                 / "DROIT_ref_processed.json")
    analytics = (ANALYTICS / "competence" / "usmb_licence"
                 / "DROIT_ref_flat.json")
    quality = (ANALYTICS / "competence" / "usmb_licence"
               / "DROIT_ref_quality.json")
    assert raw.exists()
    assert processed.exists()
    assert analytics.exists()
    assert quality.exists()

    # canonique exploitable + identité programme depuis le nom uploadé
    canonical = json.loads(processed.read_text(encoding="utf-8"))
    sous = canonical["sous_classifications"][0]
    assert sous["code"] == "USMB_DROIT"
    comp = sous["competences"][0]
    assert comp["code"] == "COMP_1"
    acs = [ac for niv in comp["niveaux_developpement"]
           for ac in niv["apprentissages_critiques"]]
    assert len(acs) == 3
    assert any("DROIT101_TEST" in ac["modules"] for ac in acs)

    # flat conforme + quality report cohérent
    flat = json.loads(analytics.read_text(encoding="utf-8"))
    assert len(flat) == 3
    assert flat[0]["source"] == "usmb_licence"
    q = json.loads(quality.read_text(encoding="utf-8"))
    assert q["competences"] == 1
    assert q["acs"] == 3
    assert q["liens_ac_module"] == 4
    assert q["errors"] == []


def test_upload_curriculum_usmb_200_et_lite_genere():
    """Le MÊME xlsx, uploadé en domaine curriculum -> Programme lite :
    S1/S2, UA, EC à 0.0, quality curriculum_type=lite."""
    r = client.post(
        "/api/v1/admin/sources/upload",
        data={"domain": "curriculum", "source_name": "usmb_licence",
              "formation_name": "DROIT"},
        files={"file": ("ref.xlsx", usmb_xlsx_bytes(),
                        "application/vnd.openxmlformats-officedocument"
                        ".spreadsheetml.sheet")},
        headers=get_headers(),
    )
    assert r.status_code == 200, r.text

    processed = (PROCESSED / "curriculum" / "usmb_licence"
                 / "DROIT_ref_processed.json")
    quality = (ANALYTICS / "curriculum" / "usmb_licence"
               / "DROIT_ref_quality.json")
    assert processed.exists() and quality.exists()

    prog = json.loads(processed.read_text(encoding="utf-8"))
    assert prog["id"] == "USMB_DROIT"
    assert prog["type"] == "Licence" and prog["ects_total"] == 180.0
    assert [p["numero"] for p in prog["periodes"]] == [1, 2]
    s1 = prog["periodes"][0]
    assert s1["ects"] == 0.0
    groupes = s1["groupes_elements_pedagogiques"]
    assert {g["code"] for g in groupes} == {"UAF101"}
    elements = groupes[0]["elements_pedagogiques"]
    assert {e["id"] for e in elements} == {
        "S1_DROIT101_TEST", "S1_INTRODUCTION_AU_DROIT_PRIVE"}
    assert all(e["credits"] == 0.0 and e["cm"] == 0.0 for e in elements)
    assert all(e["acquis_apprentissage"] == [] for e in elements)

    q = json.loads(quality.read_text(encoding="utf-8"))
    assert q["curriculum_type"] == "lite"
    assert q["ects_renseignes"] is False
    assert any("Squelette curriculaire" in w for w in q["warnings"])


def test_upload_hors_gabarit_math_422_et_raw_nettoye():
    r = client.post(
        "/api/v1/admin/sources/upload",
        data={"domain": "competence", "source_name": "usmb_licence",
              "formation_name": "MATH"},
        files={"file": ("ref.xlsx", math_like_xlsx_bytes(),
                        "application/vnd.openxmlformats-officedocument"
                        ".spreadsheetml.sheet")},
        headers=get_headers(),
    )
    assert r.status_code == 422, r.text
    assert "hors gabarit" in r.json()["detail"] \
        or "pipeline" in r.json()["detail"].lower()
    assert not (RAW / "competence" / "usmb_licence" / "MATH_ref.xlsx").exists()
    assert not list(PROCESSED.rglob("*.json"))
    assert not list(ANALYTICS.rglob("*.json"))


def test_source_inconnue_toujours_422():
    r = client.post(
        "/api/v1/admin/sources/upload",
        data={"domain": "competence", "source_name": "inconnue",
              "formation_name": "X"},
        files={"file": ("ref.xlsx", usmb_xlsx_bytes(),
                        "application/octet-stream")},
        headers=get_headers(),
    )
    assert r.status_code == 422
    assert not (RAW / "competence" / "inconnue" / "X_ref.xlsx").exists()