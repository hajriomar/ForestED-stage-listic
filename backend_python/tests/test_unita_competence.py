# -*- coding: utf-8 -*-
"""
Tests U2A — pipeline competence UNITA (extractor JSON -> normalizer ->
transformer). Vérifie l'intégration dans les factories, la fidélité à la
source PLO/MLO et la conformité au modèle canonique competence + contrat R4.

Lancer depuis backend_python :
    python -m pytest tests/test_unita_competence.py -v
"""

import os
from pathlib import Path

import pytest

from app.etl.extract.json_extractor import extract_json
from app.etl.normalize.normalizer_factory import NormalizerFactory
from app.etl.transform.transformer_factory import TransformerFactory
from app.etl.transform.flat_contract import (
    validate_competence_canonical,
    validate_flat_rows,
)

_FIXTURE = os.getenv("UNITA_PLO_MLO_JSON") or str(
    Path(__file__).parent / "fixtures" / "JB_SCRL_plo_mlo_source.json"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def normalized():
    if not os.path.exists(_FIXTURE):
        pytest.skip(f"Fixture absente : {_FIXTURE}")
    env = extract_json(_FIXTURE)
    norm = NormalizerFactory.get_normalizer("competence", "unita")
    return norm.normalize(env)


@pytest.fixture(scope="module")
def result(normalized):
    transformer = TransformerFactory.get_transformer("competence", "unita")
    return transformer.transform(normalized)


def _modules(normalized):
    return {m["module_code"]: m for m in normalized["modules"]}


def _acs_for_module(referentiel, module_code):
    out = []
    for sous in referentiel.sous_classifications:
        for comp in sous.competences:
            for niv in comp.niveaux_developpement:
                for ac in niv.apprentissages_critiques:
                    if module_code in ac.modules:
                        out.append(ac)
    return out


# ---------------------------------------------------------------------------
# 0. Intégration factories
# ---------------------------------------------------------------------------

def test_unita_competence_registered_in_factories():
    norm = NormalizerFactory.get_normalizer("competence", "unita")
    transf = TransformerFactory.get_transformer("competence", "unita")
    assert type(norm).__name__ == "UNITACompetenceNormalizer"
    assert type(transf).__name__ == "UNITACompetenceTransformer"
    assert "competence/unita" in TransformerFactory.known_sources()


# ---------------------------------------------------------------------------
# 1-3. Chargement + PLO + modules
# ---------------------------------------------------------------------------

def test_json_loaded_without_error(normalized):
    assert normalized["source_name"] == "unita"
    assert normalized["programme_id"] == "JB_SCRL"


def test_twelve_plos(normalized):
    codes = [p["code"] for p in normalized["plos"]]
    assert codes == [f"PLO{i}" for i in range(1, 13)]


def test_ten_generic_modules(normalized):
    codes = [m["module_code"] for m in normalized["modules"]]
    assert len(codes) == 10
    assert set(codes) == {
        "UNITA_M1", "UNITA_M2", "UNITA_M3", "UNITA_M4", "UNITA_M5",
        "UNITA_BUSINESS", "UNITA_ECONOMICS", "UNITA_FINANCE",
        "UNITA_HR", "UNITA_MARKETING",
    }


# ---------------------------------------------------------------------------
# 4-8. MLO langue (fidélité à la preuve verbatim)
# ---------------------------------------------------------------------------

def test_m1_has_9_mlo(normalized):
    assert len(_modules(normalized)["UNITA_M1"]["module_learning_outcomes"]) == 9


def test_m2_has_9_mlo_all_linked(normalized):
    mlos = _modules(normalized)["UNITA_M2"]["module_learning_outcomes"]
    assert len(mlos) == 9
    assert all(m["aligned_plos"] for m in mlos)


def test_m3_has_8_mlo_all_linked(normalized, result):
    m3 = _modules(normalized)["UNITA_M3"]
    # M3 est désormais renseigné et validé (plus de table cassée).
    assert m3.get("mlo_status") == "complete"
    mlos = m3["module_learning_outcomes"]
    assert len(mlos) == 8
    assert all(m["aligned_plos"] for m in mlos)
    # 8 MLO -> 18 liens (somme des aligned_plos) développés en AC.
    assert len(_acs_for_module(result["canonical"], "UNITA_M3")) == 18
    # plus aucun module à revalider.
    assert "UNITA_M3" not in result["quality_report"]["modules_to_validate"]
    assert result["quality_report"]["modules_to_validate"] == []


def test_m4_has_9_mlo_all_linked(normalized):
    mlos = _modules(normalized)["UNITA_M4"]["module_learning_outcomes"]
    assert len(mlos) == 9
    assert all(m["aligned_plos"] for m in mlos)


def test_m5_has_10_mlo_all_linked(normalized, result):
    mlos = _modules(normalized)["UNITA_M5"]["module_learning_outcomes"]
    assert len(mlos) == 10
    assert all(m["aligned_plos"] for m in mlos)
    # 10 MLO -> 21 liens (somme des aligned_plos) développés en AC.
    assert len(_acs_for_module(result["canonical"], "UNITA_M5")) == 21


# ---------------------------------------------------------------------------
# 9-11. Modules métier (projection) + rien inventé
# ---------------------------------------------------------------------------

def test_business_mlo_inherit_module_level_plos(normalized):
    mods = _modules(normalized)
    for code in ("UNITA_BUSINESS", "UNITA_ECONOMICS", "UNITA_FINANCE",
                 "UNITA_HR", "UNITA_MARKETING"):
        mlp = mods[code]["module_level_plos"]
        assert mlp, f"{code} sans module_level_plos"
        for mlo in mods[code]["module_learning_outcomes"]:
            assert mlo["aligned_plos"] == mlp


def test_no_unchecked_plo_added(result):
    # Business : ACs uniquement sous les PLO cochés {2,7,8,9,10}
    plos = {a.code.split("__")[0]
            for a in _acs_for_module(result["canonical"], "UNITA_BUSINESS")}
    assert plos == {"PLO2", "PLO7", "PLO8", "PLO9", "PLO10"}


def test_all_mlo_linked(result):
    # 70 MLO désormais renseignés avec >=1 PLO -> aucun MLO non rattaché.
    assert result["quality_report"]["mlo_unlinked_count"] == 0


# ---------------------------------------------------------------------------
# 12-13. quality_notes + conformité modèle canonique
# ---------------------------------------------------------------------------

def test_source_quality_notes_is_list(result):
    # Les fichiers input ne stockent plus de quality_notes : le quality_report
    # est produit par l'ETL (normalizer/transformer). On vérifie seulement que
    # la clé existe et que c'est une liste ; source_quality_notes=[] est accepté.
    qr = result["quality_report"]
    assert "source_quality_notes" in qr
    assert isinstance(qr["source_quality_notes"], list)


def test_canonical_and_flat_contract_ok(result):
    assert validate_competence_canonical(result["canonical"]) == []
    assert validate_flat_rows(result["flat"], "competence") == []


def test_link_provenance_traced(result):
    qr = result["quality_report"]
    by = qr["ac_links_by_alignment_level"]
    # langue M1..M5 (18+13+18+15+21) = 85 liens source_declared
    assert by.get("source_declared") == 85
    # métier : 5 modules projetés = 130 liens module_projected
    assert by.get("module_projected") == 130
    assert qr["ac_links_created"] == 215


# ---------------------------------------------------------------------------
# Corrections U2A : validation catalogue, cohérence métier, plos_without_ac
# ---------------------------------------------------------------------------

def test_expected_modules_no_missing_or_unknown_warning(result):
    # La fixture contient exactement les 10 modules attendus -> aucun
    # warning de module manquant/inconnu.
    warns = result["quality_report"].get("warnings", [])
    assert not any("attendus manquants" in w or "hors catalogue" in w
                   for w in warns)


def test_business_projection_consistency_no_warning(result):
    # Chaque MLO métier a aligned_plos == module_level_plos -> aucun
    # warning de divergence de projection.
    warns = result["quality_report"].get("warnings", [])
    assert not any("module_projected attendue" in w for w in warns)


def test_plos_without_ac_reported(result):
    # PLO3 (SDGs) n'est coché par aucun module -> aucun AC canonique.
    # Information tracée, sans AC inventé.
    assert result["quality_report"]["plos_without_ac"] == ["PLO3"]
