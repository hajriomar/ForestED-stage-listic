"""
Tests — import d'une source depuis une API JSON externe.

POST /admin/sources/import-api : sécurité d'accès, anti-SSRF,
validations, flux raw -> process_file, nettoyage en échec.

Lancer depuis backend_python :
    python -m pytest tests/test_api_import.py -v
"""

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.auth.admin_api_import_service as service
import app.auth.routes_admin_upload as upload_module
import app.etl.pipeline as pipeline_module
from app.auth.admin_api_import_service import ApiImportError, validate_api_url
from app.auth.database import Base, SessionLocal, engine
from app.auth.models import ROLE_ADMIN, ROLE_VIEWER, User
from app.auth.security import hash_password
from app.main import app

client = TestClient(app)

PASSWORD = "motdepasse-test-123"
TEST_ROOT = Path("./test_data_api_import").resolve()
RAW = TEST_ROOT / "raw"
PROCESSED = TEST_ROOT / "processed"
ANALYTICS = TEST_ROOT / "analytics"

PUBLIC_URL = "https://93.184.216.34/api/data"  # IP publique : pas de DNS


def polytech_competence_json() -> bytes:
    """Export phpMyAdmin minimal (nouveau format) accepté par le pipeline."""
    row = {
        "code_competence": "COMP_IDU1", "id_competence": "1",
        "libelle_competence": "Concevoir des systèmes",
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
    return json.dumps([
        {"type": "header", "version": "5", "comment": ""},
        {"type": "database", "name": "test"},
        {"type": "table", "name": "APC_competence",
         "database": "test", "data": [row]},
    ]).encode("utf-8")


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
    db.add_all([
        User(username="admin", email="admin@test.fr",
             hashed_password=hash_password(PASSWORD), role=ROLE_ADMIN),
        User(username="viewer", email="viewer@test.fr",
             hashed_password=hash_password(PASSWORD), role=ROLE_VIEWER),
    ])
    db.commit()
    db.close()
    yield


@pytest.fixture
def stub_fetch(monkeypatch):
    """Stub réseau : fetch retourne un JSON pipeline-valide, et on
    capture l'URL appelée. validate_api_url reste ACTIF (vraie logique)."""
    calls = {}

    def fake_fetch(url, headers=None, **kwargs):
        calls["url"] = url
        calls["header_names"] = sorted((headers or {}).keys())
        return calls.get("payload", polytech_competence_json())

    monkeypatch.setattr(service, "fetch_json_from_api", fake_fetch)
    return calls


def get_headers(username="admin"):
    r = client.post("/api/v1/auth/login",
                    data={"username": username, "password": PASSWORD})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def do_import(headers=None, **overrides):
    body = {
        "domain": "competence", "source_name": "Polytech",
        "formation_name": "IDU", "url": PUBLIC_URL,
        "output_filename": "curriculum_api.json",
    }
    body.update(overrides)
    return client.post("/api/v1/admin/sources/import-api", json=body,
                       headers=headers if headers is not None
                       else get_headers())


# =====================================================
# Anti-SSRF : validate_api_url (vraie logique, unitaire)
# =====================================================

@pytest.mark.parametrize("bad_url", [
    "http://localhost/api",
    "http://127.0.0.1/api",
    "http://0.0.0.0/api",
    "http://[::1]/api",
    "http://192.168.1.10/api",
    "http://10.0.0.5/api",
    "http://172.16.3.4/api",
    "file:///etc/passwd",
    "ftp://example.com/x",
    "pas-une-url",
])
def test_validate_api_url_rejects_dangerous(bad_url):
    with pytest.raises(ApiImportError):
        validate_api_url(bad_url)


def test_validate_api_url_accepts_public_ip():
    validate_api_url(PUBLIC_URL)  # ne lève pas


def test_route_rejects_localhost_url(stub_fetch):
    r = do_import(url="http://127.0.0.1:8000/steal")
    assert r.status_code == 400
    assert "SSRF" in r.json()["detail"] or "interdite" in r.json()["detail"]
    # le fetch n'a jamais été appelé
    assert "url" not in stub_fetch


# =====================================================
# Sécurité d'accès
# =====================================================

def test_import_requires_auth(stub_fetch):
    assert do_import(headers={}).status_code == 401


def test_viewer_forbidden(stub_fetch):
    assert do_import(headers=get_headers("viewer")).status_code == 403


def test_api_key_and_guest_forbidden(stub_fetch):
    created = client.post(
        "/api/v1/admin/api-keys",
        json={"name": "cle", "kind": "dashboard",
              "permissions": [{"source_name": "*", "scopes": ["*"]}]},
        headers=get_headers(),
    ).json()
    r = do_import(headers={"X-API-Key": created["api_key"]})
    assert r.status_code == 403


# =====================================================
# Cas nominal
# =====================================================

def test_import_success_saves_raw_and_processes(stub_fetch):
    r = do_import()
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["message"] == "API source imported and processed successfully"
    assert body["raw_file"] == "competence/Polytech/IDU_curriculum_api.json"

    # fichier raw au bon endroit (9. et 10. : process_file a tourné dessus)
    raw = RAW / "competence" / "Polytech" / "IDU_curriculum_api.json"
    assert raw.exists()
    assert json.loads(raw.read_bytes())[2]["data"]  # contenu intact

    processed = (PROCESSED / "competence" / "Polytech"
                 / "IDU_curriculum_api_processed.json")
    analytics = (ANALYTICS / "competence" / "Polytech"
                 / "IDU_curriculum_api_flat.json")
    assert processed.exists()
    assert analytics.exists()
    assert stub_fetch["url"] == PUBLIC_URL


def test_auto_filename_when_absent(stub_fetch):
    r = do_import(output_filename=None)
    assert r.status_code == 200
    raw_file = r.json()["raw_file"]
    # {formation}_api_{YYYYMMDD_HHMMSS}.json
    assert raw_file.startswith("competence/Polytech/IDU_api_")
    assert raw_file.endswith(".json")


def test_output_filename_forced_to_json_and_sanitized(stub_fetch):
    r = do_import(output_filename="../../evil éxport.txt")
    assert r.status_code == 200
    # Path().stem neutralise les répertoires, la sanitisation le reste
    raw_file = r.json()["raw_file"]
    assert raw_file.startswith("competence/Polytech/IDU_")
    assert raw_file.endswith(".json")
    assert ".." not in raw_file and "/evil" not in raw_file.split("/")[-1]
    # rien n'a été écrit hors de raw/
    assert not (TEST_ROOT.parent / "evil").exists()


def test_duplicate_output_409(stub_fetch):
    assert do_import().status_code == 200
    r = do_import()
    assert r.status_code == 409
    assert "existe déjà" in r.json()["detail"]


# =====================================================
# Erreurs de contenu / pipeline
# =====================================================

def test_pipeline_failure_422_and_raw_cleaned(stub_fetch):
    stub_fetch["payload"] = json.dumps({"pas": "un export"}).encode()
    r = do_import(output_filename="mauvais.json")
    assert r.status_code == 422
    assert "pipeline" in r.json()["detail"].lower()
    assert not (RAW / "competence" / "Polytech"
                / "IDU_mauvais.json").exists()


def test_non_json_response_rejected(monkeypatch):
    """fetch réel avec un faux client httpx qui renvoie du HTML."""
    class FakeResponse:
        status_code = 200
        def iter_bytes(self):
            yield b"<html>pas du json</html>"
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class FakeClient:
        def __init__(self, **kw): pass
        def stream(self, method, url, headers=None): return FakeResponse()
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(service.httpx, "Client", FakeClient)
    with pytest.raises(ApiImportError) as exc:
        service.fetch_json_from_api("https://exemple.test/x")
    assert exc.value.status_code == 422


def test_oversized_response_rejected(monkeypatch):
    class FakeResponse:
        status_code = 200
        def iter_bytes(self):
            for _ in range(30):
                yield b"x" * (1024 * 1024)  # 30 Mo au total
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class FakeClient:
        def __init__(self, **kw): pass
        def stream(self, method, url, headers=None): return FakeResponse()
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(service.httpx, "Client", FakeClient)
    with pytest.raises(ApiImportError) as exc:
        service.fetch_json_from_api("https://exemple.test/gros")
    assert exc.value.status_code == 413


def test_method_post_rejected(stub_fetch):
    r = do_import(method="POST")
    assert r.status_code == 422  # Literal["GET"]


def test_sensitive_headers_never_in_safe_names():
    names = service.safe_header_names({
        "Authorization": "Bearer secret",
        "X-API-Key": "secret",
        "Cookie": "secret",
        "Accept": "application/json",
    })
    assert names == ["Accept"]


# =====================================================
# Non-régression : l'upload fichier fonctionne toujours
# =====================================================

def test_file_upload_still_works():
    r = client.post(
        "/api/v1/admin/sources/upload",
        data={"domain": "competence", "source_name": "Polytech",
              "formation_name": "SNI"},
        files={"file": ("ref.json", polytech_competence_json(),
                        "application/json")},
        headers=get_headers(),
    )
    assert r.status_code == 200, r.text
    assert (RAW / "competence" / "Polytech" / "SNI_ref.json").exists()