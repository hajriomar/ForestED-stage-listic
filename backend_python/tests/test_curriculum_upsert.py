# -*- coding: utf-8 -*-
"""
Tests U4 — CurriculumUpsertService (upsert curriculum multi-scope /
multi-institution dans un même fichier processed).

Vérifie :
- générique seul -> aucune institution ;
- ajout USMB -> le générique reste intact ;
- rechargement USMB -> idempotent (aucun ajout, total stable) ;
- le générique n'est jamais écrasé par USMB ;
- une 3e institution (HES-SO) préserve générique + USMB.

Lancer depuis backend_python :
    python -m pytest tests/test_curriculum_upsert.py -v
"""

import json
import os
import tempfile
from collections import Counter
from pathlib import Path

import pytest

from app.etl.extract.json_extractor import extract_json
from app.etl.extract.excel_extractor import extract_excel
from app.etl.normalize.normalizer_factory import NormalizerFactory
from app.etl.transform.transformer_factory import TransformerFactory
from app.etl.load.curriculum_upsert_service import CurriculumUpsertService

_FIX = Path(__file__).parent / "fixtures"
_GENERIC = os.getenv("UNITA_CURRICULUM_JSON") or str(_FIX / "JB_SCRL_curriculum_generic.json")
_EXCEL = os.getenv("UNITA_USMB_XLSX") or str(_FIX / "MAQUETTE_JD_JUILLET_26.xlsx")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pipeline(extracted):
    norm = NormalizerFactory.get_normalizer("curriculum", "unita").normalize(extracted)
    return TransformerFactory.get_transformer("curriculum", "unita").transform(norm)


def _svc():
    return CurriculumUpsertService()


def _tmp_out():
    d = tempfile.mkdtemp(prefix="unita_upsert_")
    return os.path.join(d, "data", "processed", "curriculum", "unita",
                        "JB_SCRL_processed.json")


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _scope_counts(processed):
    return Counter(r["scope"] for r in processed["elements"].values())


def _fake_institution_result(inst, n=3):
    """Fabrique un result minimal institution-specific (ex. HES-SO)."""
    flat, ups = [], []
    for i in range(1, n + 1):
        key = f"JB_SCRL::institution_specific::{inst}::S1::UE_{inst}::{inst}_E{i:02d}"
        flat.append({
            "programme_id": "JB_SCRL", "programme_nom": "JB_SCRL",
            "scope": "institution_specific", "institution_code": inst,
            "upsert_institution_key": inst, "periode_id": "S1", "semestre": 1,
            "groupe_id": f"UE_{inst}", "groupe_code": f"UE_{inst}",
            "groupe_intitule": "UE test", "groupe_type": "UE",
            "element_id": f"{inst}_E{i:02d}", "element_nom": f"Module {inst} {i}",
            "element_type": "management_module", "element_credits": 3.0,
            "cm": 0.0, "td": 0.0, "tp": 0.0, "projet": 0.0,
            "ac_id": "", "ac_description": "",
            "generic_module_code": "", "match_status": "",
            "source_sheet": "", "source_cell": "",
            "upsert_key": key,
        })
        ups.append({"upsert_key": key})
    return {"flat": flat, "upsert": {"elements": ups},
            "quality_report": {"input_kind": "fake_" + inst},
            "institutions": [inst]}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def gen_result():
    if not os.path.exists(_GENERIC):
        pytest.skip(f"Fixture générique absente : {_GENERIC}")
    return _pipeline(extract_json(_GENERIC))


@pytest.fixture(scope="module")
def usmb_result():
    if not os.path.exists(_EXCEL):
        pytest.skip(f"Fixture Excel absente : {_EXCEL}")
    return _pipeline(extract_excel(_EXCEL))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_generic_only_no_institution(gen_result):
    out = _tmp_out()
    summary = _svc().upsert_result(gen_result, out)
    p = _load(out)
    assert summary["scopes"] == ["generic"]
    assert summary["institutions"] == []            # générique = aucune institution
    counts = _scope_counts(p)
    assert counts["generic"] == 10 and set(counts) == {"generic"}
    assert p["programme_id"] == "JB_SCRL"


def test_add_usmb_keeps_generic(gen_result, usmb_result):
    out = _tmp_out()
    _svc().upsert_result(gen_result, out)
    _svc().upsert_result(usmb_result, out)
    p = _load(out)
    counts = _scope_counts(p)
    assert counts["generic"] == 10                  # générique intact
    assert counts["institution_specific"] > 20      # modules USMB ajoutés
    assert p["institutions"] == ["USMB"]
    assert set(p["scopes"]) == {"generic", "institution_specific"}


def test_reload_usmb_is_idempotent(gen_result, usmb_result):
    out = _tmp_out()
    _svc().upsert_result(gen_result, out)
    first = _svc().upsert_result(usmb_result, out)["total_elements"]
    again = _svc().upsert_result(usmb_result, out)     # rechargement
    assert again["added"] == 0                          # que des updates
    assert again["total_elements"] == first             # total stable
    assert _scope_counts(_load(out))["generic"] == 10   # générique intact


def test_generic_not_overwritten_by_usmb(gen_result, usmb_result):
    out = _tmp_out()
    _svc().upsert_result(gen_result, out)
    p0 = _load(out)
    gkey = next(k for k, r in p0["elements"].items() if r["scope"] == "generic")
    gnom = p0["elements"][gkey]["element_nom"]
    _svc().upsert_result(usmb_result, out)
    p1 = _load(out)
    assert gkey in p1["elements"]                       # toujours présent
    assert p1["elements"][gkey]["scope"] == "generic"
    assert p1["elements"][gkey]["element_nom"] == gnom  # inchangé


def test_second_institution_preserves_others(gen_result, usmb_result):
    out = _tmp_out()
    _svc().upsert_result(gen_result, out)
    _svc().upsert_result(usmb_result, out)
    before = _load(out)
    n_gen = _scope_counts(before)["generic"]
    n_usmb = sum(1 for r in before["elements"].values()
                 if r["institution_code"] == "USMB")

    # 3e source : HES-SO (institution-specific)
    _svc().upsert_result(_fake_institution_result("HESSO", n=3), out)
    after = _load(out)

    assert _scope_counts(after)["generic"] == n_gen     # générique préservé
    assert sum(1 for r in after["elements"].values()
               if r["institution_code"] == "USMB") == n_usmb   # USMB préservé
    assert sum(1 for r in after["elements"].values()
               if r["institution_code"] == "HESSO") == 3       # HES-SO ajouté
    assert set(after["institutions"]) == {"HESSO", "USMB"}


def test_usmb_reload_after_hesso_keeps_hesso(gen_result, usmb_result):
    out = _tmp_out()
    _svc().upsert_result(gen_result, out)
    _svc().upsert_result(usmb_result, out)
    _svc().upsert_result(_fake_institution_result("HESSO", n=2), out)
    # recharger USMB ne doit pas toucher HES-SO ni le générique
    _svc().upsert_result(usmb_result, out)
    after = _load(out)
    assert sum(1 for r in after["elements"].values()
               if r["institution_code"] == "HESSO") == 2
    assert _scope_counts(after)["generic"] == 10
    assert set(after["institutions"]) == {"HESSO", "USMB"}
