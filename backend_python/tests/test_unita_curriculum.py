# -*- coding: utf-8 -*-
"""
Tests U3 — pipeline curriculum UNITA (extractor -> normalizer -> transformer).

Deux chemins :
- JSON générique (`JB_SCRL_curriculum_generic.json`) : parsing COMPLET,
  Programme canonique, MLO en acquis, ZÉRO PLO, sortie prête à l'upsert.
- Excel USMB (`MAQUETTE JD ...xlsx`) : parsing MINIMAL (routage + squelette
  années, aucun module inventé, TODO tracés).

Lancer depuis backend_python :
    python -m pytest tests/test_unita_curriculum.py -v
"""

import json
import os
from pathlib import Path

import pytest

from app.etl.extract.json_extractor import extract_json
from app.etl.extract.excel_extractor import extract_excel
from app.etl.normalize.normalizer_factory import NormalizerFactory
from app.etl.transform.transformer_factory import TransformerFactory
from app.etl.transform.flat_contract import (
    validate_curriculum_canonical,
    validate_flat_rows,
)

_FIX = Path(__file__).parent / "fixtures"
_GENERIC = os.getenv("UNITA_CURRICULUM_JSON") or str(_FIX / "JB_SCRL_curriculum_generic.json")
_EXCEL = os.getenv("UNITA_USMB_XLSX") or str(_FIX / "MAQUETTE_JD_JUILLET_26.xlsx")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def gen_norm():
    if not os.path.exists(_GENERIC):
        pytest.skip(f"Fixture absente : {_GENERIC}")
    env = extract_json(_GENERIC)
    return NormalizerFactory.get_normalizer("curriculum", "unita").normalize(env)


@pytest.fixture(scope="module")
def gen_res(gen_norm):
    return TransformerFactory.get_transformer("curriculum", "unita").transform(gen_norm)


@pytest.fixture(scope="module")
def xls_norm():
    if not os.path.exists(_EXCEL):
        pytest.skip(f"Fixture Excel absente : {_EXCEL}")
    env = extract_excel(_EXCEL)
    return NormalizerFactory.get_normalizer("curriculum", "unita").normalize(env)


@pytest.fixture(scope="module")
def xls_res(xls_norm):
    return TransformerFactory.get_transformer("curriculum", "unita").transform(xls_norm)


# ---------------------------------------------------------------------------
# Helpers de descente canonique
# ---------------------------------------------------------------------------

def _leaf_groups(groupes):
    for g in groupes:
        sous = getattr(g, "groupes_elements_pedagogiques", None)
        if sous:
            yield from _leaf_groups(sous)
        else:
            yield g


def _all_elements(programme):
    for per in programme.periodes:
        for g in _leaf_groups(per.groupes_elements_pedagogiques):
            for el in g.elements_pedagogiques:
                yield el


def _all_acquis_ids(programme):
    ids = []
    for el in _all_elements(programme):
        ids.extend(a.id for a in el.acquis_apprentissage)
    return ids


# ---------------------------------------------------------------------------
# 0. Intégration factories
# ---------------------------------------------------------------------------

def test_curriculum_unita_registered():
    norm = NormalizerFactory.get_normalizer("curriculum", "unita")
    transf = TransformerFactory.get_transformer("curriculum", "unita")
    assert type(norm).__name__ == "UNITACurriculumNormalizer"
    assert type(transf).__name__ == "UNITACurriculumTransformer"
    assert "curriculum/unita" in TransformerFactory.known_sources()
    # competence/unita ne doit PAS avoir été touché.
    assert "competence/unita" in TransformerFactory.known_sources()


# ---------------------------------------------------------------------------
# 1-8. Chemin JSON générique
# ---------------------------------------------------------------------------

def test_generic_programme_built(gen_res):
    prog = gen_res["canonical"]
    assert type(prog).__name__ == "Programme"
    assert prog.id == "JB_SCRL"
    assert len(prog.periodes) == 4
    assert prog.duree == 3   # A1/A2/A3 (numero > 0), COMMON transverse exclu


def test_generic_periode_numeros(gen_res):
    prog = gen_res["canonical"]
    by_id = {p.id: p.numero for p in prog.periodes}
    assert by_id == {"A1": 1, "A2": 2, "A3": 3, "COMMON": -1}


def test_generic_groups_and_element_counts(gen_res):
    prog = gen_res["canonical"]
    counts = {g.code: len(g.elements_pedagogiques)
              for per in prog.periodes for g in _leaf_groups(per.groupes_elements_pedagogiques)}
    assert counts == {
        "LANG_A1": 2, "LANG_A2": 2, "LANG_A3": 1, "BUSINESS_COMMON": 5,
    }


def test_generic_total_elements_and_acquis(gen_res):
    prog = gen_res["canonical"]
    assert sum(1 for _ in _all_elements(prog)) == 10
    assert len(_all_acquis_ids(prog)) == 70


def test_generic_acquis_are_mlo(gen_res):
    ids = _all_acquis_ids(prog := gen_res["canonical"])
    # Tous les acquis sont des MLO (jamais des PLO).
    assert all("_MLO" in aid for aid in ids)
    assert "UNITA_M1_MLO01" in ids
    assert "UNITA_M5_MLO10" in ids           # typo MLO010 corrigé en amont
    assert "UNITA_BUSINESS_MLO01" in ids


def test_generic_no_plo_anywhere(gen_res):
    # Aucun acquis ne porte d'attribut PLO.
    for el in _all_elements(gen_res["canonical"]):
        for a in el.acquis_apprentissage:
            assert not hasattr(a, "aligned_plos")
    # Ni dans les lignes flat, ni dans le quality_report.
    blob = json.dumps(gen_res["flat"]) + json.dumps(gen_res["quality_report"])
    assert "aligned_plos" not in blob
    assert "PLO" not in blob
    assert gen_res["quality_report"]["plo_free"] is True


def test_generic_scope_and_institution(gen_res):
    qr = gen_res["quality_report"]
    assert qr["scope"] == "generic"
    assert qr["institution_code"] is None                 # pas d'institution réelle
    assert qr["upsert_institution_key"] == "__GENERIC__"  # clé technique seulement
    assert qr["institutions"] == []
    assert gen_res["institutions"] == []                  # Programme générique : institutions=[]
    assert all(r["scope"] == "generic" for r in gen_res["flat"])
    # flat : institution_code vide (ni "__GENERIC__", ni une institution)
    assert all(r["institution_code"] == "" for r in gen_res["flat"])


def test_generic_programme_institutions_empty(gen_res):
    # Le modèle Programme porte un champ `institutions` : en générique il est [].
    assert gen_res["canonical"].institutions == []
    assert gen_res["institutions"] == []
    # le champ s'appelle institutions (pas institution_code)
    assert not hasattr(gen_res["canonical"], "institution_code")


def test_generic_element_credits(gen_res):
    creds = {el.id: el.credits for el in _all_elements(gen_res["canonical"])}
    assert creds["UNITA_M1"] == 15.0
    assert creds["UNITA_BUSINESS"] == 6.0


# ---------------------------------------------------------------------------
# 9-11. Sortie prête à l'upsert + contrat + non-merge
# ---------------------------------------------------------------------------

def test_generic_upsert_output_ready(gen_res):
    up = gen_res["upsert"]
    assert up["scope"] == "generic"
    assert up["institution_code"] is None                 # vraie institution : aucune
    assert up["upsert_institution_key"] == "__GENERIC__"  # composant technique de la clé
    assert len(up["elements"]) == 10                      # une entrée par élément
    keys = [e["upsert_key"] for e in up["elements"]]
    assert len(set(keys)) == 10                           # clés uniques
    # format : programme_id::scope::upsert_institution_key::periode::groupe::element
    sample = up["elements"][0]["upsert_key"].split("::")
    assert len(sample) == 6
    # la clé continue d'utiliser "__GENERIC__" (jamais un composant vide)
    assert sample[0] == "JB_SCRL" and sample[1] == "generic" and sample[2] == "__GENERIC__"
    assert all(e["institution_code"] is None for e in up["elements"])


def test_transformer_does_not_merge(gen_res):
    assert gen_res["quality_report"]["merge_done_by_transformer"] is False
    assert gen_res["upsert"]["merge_strategy"] == "handled_by_loader"


def test_generic_flat_and_canonical_contract(gen_res):
    assert validate_curriculum_canonical(gen_res["canonical"]) == []
    assert validate_flat_rows(gen_res["flat"], "curriculum") == []


# ---------------------------------------------------------------------------
# 12-14. Chemin Excel USMB (parsing MINIMAL)
# ---------------------------------------------------------------------------

def test_excel_routed_minimal(xls_norm):
    assert xls_norm["input_kind"] == "usmb_excel"
    assert xls_norm["scope"] == "institution_specific"
    assert xls_norm["institution_code"] == "USMB"
    assert xls_norm["upsert_institution_key"] == "USMB"
    assert xls_norm["institutions"] == ["USMB"]
    # 3 feuilles JD L1/L2/L3 -> 3 années squelette, aucun module.
    assert len(xls_norm["periodes"]) == 3
    assert xls_norm["quality_report"]["element_count"] == 0
    assert xls_norm["quality_report"]["todo"]           # TODO explicites


def test_excel_no_invented_modules(xls_res):
    prog = xls_res["canonical"]
    assert len(prog.periodes) == 3
    assert sum(1 for _ in _all_elements(prog)) == 0
    assert xls_res["upsert"]["counts"]["elements"] == 0


def test_excel_scope_institution(xls_res):
    qr = xls_res["quality_report"]
    assert qr["scope"] == "institution_specific"
    assert qr["institution_code"] == "USMB"
    assert qr["institutions"] == ["USMB"]
    assert xls_res["institutions"] == ["USMB"]
    assert qr["plo_free"] is True
    # clé technique d'upsert = "USMB" (une vraie institution), jamais "__GENERIC__"
    assert xls_res["upsert"]["upsert_institution_key"] == "USMB"
    assert xls_res["upsert"]["institution_code"] == "USMB"
    # canonical : Programme.institutions renseigné avec l'institution USMB
    assert len(xls_res["canonical"].institutions) == 1
    assert xls_res["canonical"].institutions[0].nom == "USMB"
