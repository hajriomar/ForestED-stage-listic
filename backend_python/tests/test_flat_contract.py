# -*- coding: utf-8 -*-
"""
Tests R4 — contrat des sorties des transformers (canonical + flat).

Chaque transformer existant est exécuté sur un échantillon minimal réaliste,
puis ses sorties sont validées contre app/etl/transform/flat_contract.py :
- canonical : structure exploitable par build_visualisation_rows ;
- flat      : clés obligatoires par domaine (+ dialecte d'identité de
  groupe pour le curriculum).

Volontairement NON rigide : seules les clés nécessaires sont exigées,
chaque source garde ses métadonnées propres.

Un transformer pour une NOUVELLE source (UNITA…) devra passer ces mêmes
validations.

Lancer depuis backend_python :
    python -m pytest tests/test_flat_contract.py -v
"""

from app.etl.transform.flat_contract import (
    validate_competence_canonical,
    validate_curriculum_canonical,
    validate_flat_rows,
)


# =====================================================
# Échantillons d'entrée minimaux (post-normalizer)
# =====================================================

def but_competence_records():
    """Records normalisés (sortie BUTCompetenceNormalizer) — tronc commun
    + un parcours, pour vérifier la convention COMP_n / COMP_<PARCOURS>_n."""
    base = {
        "competence_desc": "desc", "niveau_description": "Niveau d'entrée",
        "composantes": ["En autonomie"], "ressources": ["R1.01"],
        "saes": ["SAE1.01"], "ue": "UE 1.1",
    }
    return [
        {**base, "competence_nom": "Concevoir", "parcours": "COMMUN",
         "semestre": 1, "niveau": 1, "ac_id": "",
         "ac_description": "Analyser un besoin client"},
        {**base, "competence_nom": "Concevoir", "parcours": "COMMUN",
         "semestre": 1, "niveau": 1, "ac_id": "",
         "ac_description": "Modéliser une solution"},
        {**base, "competence_nom": "Superviser", "parcours": "ATN",
         "semestre": 3, "niveau": 2, "ac_id": "",
         "ac_description": "Piloter une chaîne automatisée"},
    ]


def polytech_competence_rows():
    """Rows normalisées (sortie PolytechCompetenceNormalizer, schéma stable)."""
    return [
        {"code_competence": "COMP_IDU1", "libelle_competence": "Concevoir des SI",
         "description": "desc", "id_composante_essentielle": "1",
         "libelle_composante_essentielle": "En autonomie",
         "niveau": "1", "libelle_niveau": "Débutant",
         "id_apprentissage_critique": "1",
         "libelle_apprentissage": "Concevoir une BD (INFO502)",
         "code_module": "INFO502"},
        {"code_competence": "COMP_IDU1", "libelle_competence": "Concevoir des SI",
         "description": "desc", "id_composante_essentielle": "1",
         "libelle_composante_essentielle": "En autonomie",
         "niveau": "2", "libelle_niveau": "Confirmé",
         "id_apprentissage_critique": "2",
         "libelle_apprentissage": "Optimiser des requêtes (INFO603)",
         "code_module": "INFO603"},
    ]


def but_curriculum_raw():
    """Feuille Excel BUT minimale (format Annexe) : header row 3,
    données détectées à la première ligne 'UE x.x', éléments à partir
    de la colonne 10, AC en colonne 9, ligne Coefficients."""
    empty = [""] * 12
    headers = [""] * 9 + ["Apprentissages critiques",
                          "SAÉ 1.01 Découverte", "R1.01 Initiation"]
    hours_cm = ["", "", "dont CM"] + [""] * 7 + ["10", "15"]
    data_1 = ["Tronc commun", "UE 1.1 Comprendre", "", "", "", "", "", "", "",
              "AC1 : analyser un besoin", "x", ""]
    data_2 = ["", "", "", "", "", "", "", "", "",
              "AC2 : utiliser un outil", "", "x"]
    coeffs = [""] * 9 + ["Coefficients", "10", "5"]
    # normalisation : la ligne Coefficients porte le label en col 9
    coeffs[9] = "Coefficients"
    return {
        "file_name": "QLIO_BUT_annexe.xlsx",
        "sheets": [{
            "sheet_name": "Semestre 1",
            "rows": [empty, empty, empty, headers, empty, hours_cm,
                     data_1, data_2, coeffs],
        }],
    }


def polytech_curriculum_raw():
    """Fiches modules Polytech minimales (JSON déplié par le normalizer)."""
    return {
        "file_name": "IDU_maquette.json",
        "fiches": [
            {"code": "IDU301", "nom": "Bases de données", "semestre": "S3",
             "ects": "3", "CM": "10", "TD": "8", "TP": "12",
             "ue_code": "UE31", "ue_nom": "Informatique fondamentale",
             "objectifs": ["Concevoir un schéma relationnel",
                           "Écrire des requêtes SQL"]},
            {"code": "STAG501", "nom": "Stage en entreprise",
             "semestre": "S5", "ects": "10",
             "objectifs": ["Travailler en milieu professionnel"]},
        ],
    }


# =====================================================
# Helpers d'assertion
# =====================================================

def _assert_no_problems(problems, label):
    assert not problems, f"{label} : contrat violé :\n" + "\n".join(problems)


# =====================================================
# BUT competence
# =====================================================

def test_but_competence_contract():
    from app.etl.transform.competence.BUT_competence_transformer import (
        BUTCompetenceTransformer,
    )
    result = BUTCompetenceTransformer().transform(but_competence_records())

    _assert_no_problems(
        validate_competence_canonical(result["canonical"]), "BUT competence canonical")
    _assert_no_problems(
        validate_flat_rows(result["flat"], "competence"), "BUT competence flat")

    # Convention frontend : COMP_n (commun) / COMP_<PARCOURS>_n (parcours)
    codes = {r["competence_code"] for r in result["flat"]}
    assert "COMP_1" in codes
    assert "COMP_ATN_1" in codes


def test_but_competence_flat_recommended_fields():
    """Champs recommandés BUT : parcours / semestre / ue présents."""
    from app.etl.transform.competence.BUT_competence_transformer import (
        BUTCompetenceTransformer,
    )
    flat = BUTCompetenceTransformer().transform(but_competence_records())["flat"]
    for row in flat:
        assert "parcours" in row and "semestre" in row and "ue" in row


# =====================================================
# Polytech competence
# =====================================================

def test_polytech_competence_contract():
    from app.etl.transform.competence.Polytech_competence_transformer import (
        PolytechTransformer,
    )
    result = PolytechTransformer().transform(polytech_competence_rows())

    _assert_no_problems(
        validate_competence_canonical(result["canonical"]), "Polytech competence canonical")
    _assert_no_problems(
        validate_flat_rows(result["flat"], "competence"), "Polytech competence flat")

    # Lien AC -> module explicite conservé
    modules = {r["modules"] for r in result["flat"]}
    assert any("INFO502" in m for m in modules)


# =====================================================
# BUT curriculum
# =====================================================

def test_but_curriculum_contract():
    from app.etl.transform.curriculum.BUT_curriculum_transformer import (
        BUTCurriculumTransformer,
    )
    result = BUTCurriculumTransformer().transform(but_curriculum_raw())

    _assert_no_problems(
        validate_curriculum_canonical(result["canonical"]), "BUT curriculum canonical")
    _assert_no_problems(
        validate_flat_rows(result["flat"], "curriculum"), "BUT curriculum flat")

    # Identité programme résolue depuis le nom de fichier
    prog = result["canonical"]
    assert prog.id == "BUT_QLIO"

    # Dialecte "ue" (référence pour les nouvelles sources)
    for row in result["flat"]:
        assert "ue_code" in row and "parcours" in row


# =====================================================
# Polytech curriculum
# =====================================================

def test_polytech_curriculum_contract():
    from app.etl.transform.curriculum.Polytech_curriculum_transformer import (
        PolytechCurriculumTransformer,
    )
    result = PolytechCurriculumTransformer().transform(polytech_curriculum_raw())

    _assert_no_problems(
        validate_curriculum_canonical(result["canonical"]), "Polytech curriculum canonical")
    _assert_no_problems(
        validate_flat_rows(result["flat"], "curriculum"), "Polytech curriculum flat")

    prog = result["canonical"]
    assert prog.id == "POLYTECH_IDU"
    # S3 et S5 présents, stage classé STAGE
    numeros = {p.numero for p in prog.periodes}
    assert {3, 5} <= numeros
    types = {r["element_type"] for r in result["flat"]}
    assert "STAGE" in types


# =====================================================
# Garde-fou : le contrat détecte bien un flat invalide
# =====================================================

def test_contract_detects_missing_keys():
    bad = [{"competence_code": "C1"}]
    problems = validate_flat_rows(bad, "competence")
    assert problems and "absentes" in problems[0]

    problems_cur = validate_flat_rows(
        [{"programme_id": "X"}], "curriculum")
    assert problems_cur
    assert any("dialecte" in p for p in problems_cur)

    assert validate_flat_rows([], "competence") == ["flat vide : aucune ligne produite"]
