# -*- coding: utf-8 -*-
"""
Tests Patch 3 (USMB v1) — USMBLicenceCompetenceTransformer + contrat R4.

Le transformer reçoit des records déjà normalisés (aucun Excel ici) et
doit produire un canonique/flat conformes à flat_contract.py (R4).

Lancer depuis backend_python :
    python -m pytest tests/test_usmb_licence_transformer.py -v
"""

import pytest

from app.etl.transform.competence.USMB_licence_competence_transformer import (
    USMBLicenceCompetenceTransformer,
)
from app.etl.transform.flat_contract import (
    validate_competence_canonical,
    validate_flat_rows,
)


# =====================================================
# Records d'exemple (sortie du normalizer)
# =====================================================

def lien(sem=1, ua_type="UA Maj", ua_code="UAF101",
         ec_code="DROIT101", ec_libelle="Introduction au droit privé",
         parcours=None, module_code="__auto__"):
    if module_code == "__auto__":
        # même règle que le normalizer (C1) : réel sinon S<sem>_<slug>
        if ec_code:
            module_code = ec_code
        elif ec_libelle:
            import re, unicodedata
            t = unicodedata.normalize("NFKD", ec_libelle)
            t = "".join(c for c in t if not unicodedata.combining(c))
            slug = re.sub(r"[^A-Za-z0-9]+", "_", t.upper()).strip("_")[:40].rstrip("_")
            module_code = (f"S{sem}_" if sem else "SX_") + slug
        else:
            module_code = None
    return {"semestre": sem, "ua_type": ua_type, "ua_code": ua_code,
            "ec_code": ec_code, "ec_libelle": ec_libelle,
            "module_code": module_code, "parcours": parcours}


def record(sheet="Compétence 1", ordre=1, nom="Résoudre un problème",
           niveau=1, niveau_desc="Identifier les concepts", ac_ordre=1,
           ac_desc="Comprendre le sens d'un énoncé", liens=None,
           parcours=None, composantes=None):
    return {
        "programme_id": "USMB_DROIT", "programme_nom": "Licence Droit",
        "source_name": "usmb_licence",
        "competence_ordre": ordre, "competence_nom": nom,
        "composantes": composantes if composantes is not None
        else ["en identifiant les problèmes", "en mobilisant les règles"],
        "rncp": "RNCP38186",
        "niveau": niveau, "niveau_description": niveau_desc,
        "ac_ordre": ac_ordre, "ac_description": ac_desc,
        "liens": liens if liens is not None else [lien()],
        "parcours": parcours,
        "source_sheet": sheet, "source_row": 10 + ac_ordre,
    }


def normalized(records):
    return {"records": records,
            "quality_report": {"input_file": "DROIT_ref.xlsx",
                               "sheets_read": ["Compétence 1"],
                               "sheets_ignored": [], "warnings": [],
                               "errors": [], "ec_without_code": [],
                               "semestres_detected": [1]}}


def sample_records():
    return [
        # COMP_1 : N1 x2 AC, N2 x1 AC
        record(ac_ordre=1),
        record(ac_ordre=2, ac_desc="Restituer les éléments d'un contexte",
               liens=[lien(), lien(sem=2, ua_code="UAF201",
                                   ec_code="DROIT201",
                                   ec_libelle="Droit des personnes")]),
        record(ac_ordre=3, niveau=2, niveau_desc="Articuler les concepts",
               ac_desc="Saisir l'esprit de la règle",
               liens=[lien(sem=3, ec_code="DROIT301",
                           ec_libelle="Droit privé des contrats")]),
        # COMP_2 : EC SANS code -> code généré S1_<slug>
        record(sheet="Compétence 2", ordre=2, nom="Communiquer",
               ac_ordre=1, ac_desc="Rédiger de façon structurée",
               liens=[lien(ec_code=None,
                           ec_libelle="Méthodologie du travail universitaire")]),
        # COMP_ERGO_PM_1 : compétence de parcours (feuille L3)
        record(sheet="ERGO PM L3", ordre=3, nom="Encadrer une activité",
               niveau=3, niveau_desc=None, ac_ordre=1,
               ac_desc="Concevoir une séance adaptée",
               liens=[lien(sem=5, ua_code="UAF503", ec_code="ERGO501",
                           ec_libelle="Ergonomie avancée",
                           parcours="ERGO_PM")],
               parcours="ERGO_PM"),
        # AC sans lien (conservé, modules vides)
        record(sheet="Compétence 2", ordre=2, nom="Communiquer",
               ac_ordre=2, ac_desc="Présenter à l'oral", liens=[]),
    ]


def run(records=None):
    return USMBLicenceCompetenceTransformer().transform(
        normalized(records if records is not None else sample_records()))


# =====================================================
# Contrat R4
# =====================================================

def test_canonical_contrat_r4():
    result = run()
    problems = validate_competence_canonical(result["canonical"])
    assert not problems, "\n".join(problems)


def test_flat_contrat_r4():
    result = run()
    problems = validate_flat_rows(result["flat"], "competence")
    assert not problems, "\n".join(problems)


# =====================================================
# Codes compétences et AC
# =====================================================

def test_codes_competences_commun_et_parcours():
    flat = run()["flat"]
    codes = {r["competence_code"] for r in flat}
    assert codes == {"COMP_1", "COMP_2", "COMP_ERGO_PM_1"}


def test_codes_ac_sequentiels_par_niveau():
    flat = run()["flat"]
    ac_codes = [r["ac_code"] for r in flat]
    assert "COMP_1_N1_AC1" in ac_codes
    assert "COMP_1_N1_AC2" in ac_codes
    assert "COMP_1_N2_AC1" in ac_codes
    assert "COMP_ERGO_PM_1_N3_AC1" in ac_codes


def test_description_ac_jamais_reformulee():
    flat = run()["flat"]
    descs = {r["ac_description"] for r in flat}
    assert "Comprendre le sens d'un énoncé" in descs        # égalité stricte
    assert "Concevoir une séance adaptée" in descs


# =====================================================
# Modules liés
# =====================================================

def test_modules_code_reel():
    flat = run()["flat"]
    row = next(r for r in flat if r["ac_code"] == "COMP_1_N1_AC2")
    assert row["modules"] == "DROIT101, DROIT201"
    assert "Introduction au droit privé" in row["modules_libelles"]
    assert row["semestre"] == 1          # plus petit semestre lié


def test_modules_code_genere_si_absent():
    result = run()
    row = next(r for r in result["flat"]
               if r["ac_code"] == "COMP_2_N1_AC1")
    assert row["modules"] == "S1_METHODOLOGIE_DU_TRAVAIL_UNIVERSITAIRE"
    assert row["modules_libelles"] == "Méthodologie du travail universitaire"
    assert any("code stable généré" in w
               for w in result["quality_report"]["warnings"])


def test_ac_sans_lien_conserve():
    flat = run()["flat"]
    row = next(r for r in flat if r["ac_description"] == "Présenter à l'oral")
    assert row["modules"] == ""
    assert row["semestre"] is None


# =====================================================
# Canonique : structure
# =====================================================

def test_canonical_structure():
    ref = run()["canonical"]
    assert ref.intitule == "Référentiel de compétences Licence Droit — USMB"
    assert len(ref.sous_classifications) == 1
    sc = ref.sous_classifications[0]
    assert sc.code == "USMB_DROIT" and sc.nom == "Licence Droit"
    assert len(sc.competences) == 3

    comp1 = next(c for c in sc.competences if c.code == "COMP_1")
    assert [ce.code for ce in comp1.composantes_essentielles] == \
        ["COMP_1_CE1", "COMP_1_CE2"]
    assert sorted(n.niveau for n in comp1.niveaux_developpement) == [1, 2]
    n1 = next(n for n in comp1.niveaux_developpement if n.niveau == 1)
    assert n1.description == "Identifier les concepts"
    assert len(n1.apprentissages_critiques) == 2
    assert n1.apprentissages_critiques[0].modules == ["DROIT101"]


def test_ac_sans_niveau_rattache_niveau_1_avec_warning():
    recs = [record(ac_ordre=1, niveau=None, niveau_desc=None)]
    result = run(recs)
    assert result["flat"][0]["niveau"] == 1
    assert any("NIVEAU 1" in w for w in result["quality_report"]["warnings"])


# =====================================================
# Entrées invalides + rapport
# =====================================================

def test_type_error_si_entree_non_normalisee():
    with pytest.raises(TypeError) as exc:
        USMBLicenceCompetenceTransformer().transform([{"pas": "normalisé"}])
    assert "normalizer" in str(exc.value).lower()


def test_records_vides_refuses():
    with pytest.raises(ValueError):
        USMBLicenceCompetenceTransformer().transform(
            {"records": [], "quality_report": {}})


def test_quality_report_fusionne():
    result = run()
    q = result["quality_report"]
    assert q["input_file"] == "DROIT_ref.xlsx"       # hérité du normalizer
    assert q["competences"] == 3                     # recalculé ici
    assert q["acs"] == len(result["flat"])
    assert q["errors"] == []


# =====================================================
# C1 : module_code du normalizer = source de vérité
# =====================================================

def test_module_code_normalizer_prioritaire():
    """Le transformer suit lien["module_code"] même si ec_code diffère
    (source de vérité unique — partagée avec le transformer curriculum)."""
    recs = [record(liens=[lien(module_code="CODE_NORMALIZER",
                               ec_code="AUTRE")])]
    flat = run(recs)["flat"]
    assert flat[0]["modules"] == "CODE_NORMALIZER"


def test_retro_compat_records_sans_module_code():
    """Records pré-C1 (sans clé module_code) : fallback local identique."""
    l = lien(ec_code=None)
    del l["module_code"]
    recs = [record(liens=[l])]
    flat = run(recs)["flat"]
    assert flat[0]["modules"] == "S1_INTRODUCTION_AU_DROIT_PRIVE"