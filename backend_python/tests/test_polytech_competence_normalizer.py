"""
Tests du normalizer Polytech compétences (ancien + nouveau format phpMyAdmin)
et du dépliage d'enveloppe JSON du PassthroughNormalizer.

Lancer depuis backend_python :
    python -m pytest tests/test_polytech_competence_normalizer.py -v
"""

import pytest

from app.etl.normalize.normalizer_factory import (
    NormalizerFactory,
    PassthroughNormalizer,
)
from app.etl.normalize.polytech_competence_normalizer import (
    PolytechCompetenceNormalizer,
)
from app.etl.transform.competence.Polytech_competence_transformer import (
    PolytechTransformer,
)


def phpmyadmin(rows, table="APC_competence"):
    """Enveloppe export phpMyAdmin minimale."""
    return [
        {"type": "header", "version": "5", "comment": ""},
        {"type": "database", "name": "test"},
        {"type": "table", "name": table, "database": "test", "data": rows},
    ]


def json_envelope(content, file_name="test.json"):
    """Enveloppe de extract_json."""
    return {"file_name": file_name, "file_type": "json", "content": content}


OLD_ROW = {
    "id_competence": "1",
    "libelle_competence": "Concevoir des systèmes",
    "code_competence": "COMP_IDU1",
    "description": None,
    "id_composante_essentielle": "1",
    "libelle_composante_essentielle": "En adaptant la solution",
    "id_niveau": "1",
    "niveau": "1",
    "libelle_niveau": "Pour une application simple",
    "id_apprentissage_critique": "1",
    "libelle_apprentissage": "Concevoir une base de données (INFO502 BD)",
}

NEW_ROW = {
    "code_competence": "COMP_IDU1",
    "id_competence": "1",
    "libelle_competence": "Concevoir des systèmes",
    "code_ce": "COMP_IDU1_CE1",
    "libelle_composante_essentielle": "En adaptant la solution",
    "code_niveau": "COMP_IDU1_N1",
    "niveau": "1",
    "code_ac": "COMP_IDU1_N1_AC1",
    "libelle_apprentissage": "Concevoir une base de données (INFO502 BD)",
    "code_module": "INFO502_PACY",
    "nom": "Initiation aux BD",
    "ects": "2",
    "hCM": "6", "hTD": "4.5", "hTP": "12",
    "IFNULL(MAQUETTE_module.hPROJ,0)": "0",
    "learning_unit_code": "UE502",
    "learning_unit_name": "Sciences et outils",
    "nom_filiere": "IDU",
    "nom_statut": "FISE",
    "annee": "3",
}


# =====================================================
# Factory
# =====================================================

def test_factory_returns_dedicated_normalizer_case_insensitive():
    for source in ("polytech", "Polytech", "POLYTECH"):
        norm = NormalizerFactory.get_normalizer("competence", source)
        assert isinstance(norm, PolytechCompetenceNormalizer)


def test_factory_but_unchanged():
    from app.etl.normalize.but_competence_normalizer import (
        BUTCompetenceNormalizer,
    )
    norm = NormalizerFactory.get_normalizer("competence", "but")
    assert isinstance(norm, BUTCompetenceNormalizer)


def test_factory_passthrough_for_curriculum():
    norm = NormalizerFactory.get_normalizer("curriculum", "polytech")
    assert isinstance(norm, PassthroughNormalizer)


# =====================================================
# Normalizer Polytech — détection des formats
# =====================================================

def test_old_format_detected_and_passed_through():
    norm = PolytechCompetenceNormalizer()
    rows = norm.normalize(json_envelope(phpmyadmin([OLD_ROW])))
    assert len(rows) == 1
    assert rows[0]["id_apprentissage_critique"] == "1"
    assert rows[0]["libelle_niveau"] == "Pour une application simple"


def test_new_format_detected_and_mapped():
    norm = PolytechCompetenceNormalizer()
    rows = norm.normalize(json_envelope(phpmyadmin([NEW_ROW])))
    assert len(rows) == 1
    row = rows[0]
    # ids extraits des codes complets
    assert row["id_apprentissage_critique"] == "1"
    assert row["id_composante_essentielle"] == "1"
    # champs absents du nouveau format : valeurs neutres
    assert row["libelle_niveau"] == ""
    assert row["description"] is None
    # lien module explicite conservé
    assert row["code_module"] == "INFO502_PACY"


def test_non_json_envelope_passes_through():
    norm = PolytechCompetenceNormalizer()
    excel = {"file_name": "x.xlsx", "file_type": "excel", "sheets": []}
    assert norm.normalize(excel) is excel


def test_unknown_row_format_raises():
    norm = PolytechCompetenceNormalizer()
    with pytest.raises(ValueError):
        norm.normalize(json_envelope(phpmyadmin([{"colonne": "inconnue"}])))


def test_unknown_json_structure_raises():
    norm = PolytechCompetenceNormalizer()
    with pytest.raises(ValueError):
        norm.normalize(json_envelope({"pas": "phpmyadmin"}))


# =====================================================
# Bout en bout : normalizer -> transformer
# =====================================================

def _build(rows_source):
    norm = PolytechCompetenceNormalizer()
    transformer = PolytechTransformer()
    rows = norm.normalize(json_envelope(phpmyadmin(rows_source)))
    return transformer.transform(rows)


def test_e2e_new_format_builds_canonical_with_explicit_modules():
    # 2 rows = même AC lié à 2 modules (jointure maquette)
    row2 = dict(NEW_ROW, code_module="PROJ531_IDU")
    result = _build([NEW_ROW, row2])

    ref = result["canonical"]
    comps = ref.sous_classifications[0].competences
    assert len(comps) == 1

    acs = comps[0].niveaux_developpement[0].apprentissages_critiques
    assert len(acs) == 1  # dédupliqué
    assert acs[0].code == "COMP_IDU1_N1_AC1"  # identique au code_ac source
    # modules explicites agrégés (+ INFO502 par regex depuis le libellé)
    assert "INFO502_PACY" in acs[0].modules
    assert "PROJ531_IDU" in acs[0].modules

    assert len(result["flat"]) == 1


def test_e2e_old_format_regression():
    result = _build([OLD_ROW])
    ref = result["canonical"]
    comps = ref.sous_classifications[0].competences
    assert len(comps) == 1
    acs = comps[0].niveaux_developpement[0].apprentissages_critiques
    assert acs[0].code == "COMP_IDU1_N1_AC1"
    assert "INFO502" in acs[0].modules  # regex sur le libellé, comme avant
    assert comps[0].niveaux_developpement[0].description == \
        "Pour une application simple"


# =====================================================
# PassthroughNormalizer — dépliage enveloppe JSON
# =====================================================

def test_passthrough_unwraps_json_dict_and_keeps_file_name():
    pt = PassthroughNormalizer()
    out = pt.normalize(json_envelope(
        {"fiches": [{"id": 1}]}, file_name="IDU_curriculum.json"
    ))
    assert out["fiches"] == [{"id": 1}]
    assert out["file_name"] == "IDU_curriculum.json"


def test_passthrough_unwraps_json_list():
    pt = PassthroughNormalizer()
    out = pt.normalize(json_envelope([1, 2, 3]))
    assert out == [1, 2, 3]


def test_passthrough_leaves_excel_envelope_untouched():
    pt = PassthroughNormalizer()
    excel = {"file_name": "x.xlsx", "file_type": "excel", "sheets": []}
    assert pt.normalize(excel) is excel