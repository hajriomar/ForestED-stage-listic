# -*- coding: utf-8 -*-
"""
Tests C2 (USMB v2) — USMBLicenceCurriculumTransformer + contrat R4.

Vérifie notamment le point de vigilance R4 : ac_id/ac_description
présents mais VIDES sont acceptés par le contrat (les liens AC↔EC
vivent côté competence), et la COHÉRENCE des module_code entre les
deux transformers (jointure frontend).

Lancer depuis backend_python :
    python -m pytest tests/test_usmb_licence_curriculum_transformer.py -v
"""

import pytest

from app.etl.transform.competence.USMB_licence_competence_transformer import (
    USMBLicenceCompetenceTransformer,
)
from app.etl.transform.curriculum.USMB_licence_curriculum_transformer import (
    USMBLicenceCurriculumTransformer,
)
from app.etl.transform.flat_contract import (
    validate_curriculum_canonical,
    validate_flat_rows,
)


# =====================================================
# Records d'exemple (sortie du normalizer, avec module_code C1)
# =====================================================

def lien(sem=1, ua_type="UA Maj", ua_code="UAF101",
         ec_code="DROIT101", ec_libelle="Introduction au droit privé",
         parcours=None):
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
           niveau=1, ac_ordre=1, ac_desc="Comprendre un énoncé",
           liens=None, parcours=None):
    return {
        "programme_id": "USMB_DROIT", "programme_nom": "Licence Droit",
        "source_name": "usmb_licence",
        "competence_ordre": ordre, "competence_nom": nom,
        "composantes": ["en identifiant les règles"],
        "rncp": "RNCP38186",
        "niveau": niveau, "niveau_description": "Identifier",
        "ac_ordre": ac_ordre, "ac_description": ac_desc,
        "liens": liens if liens is not None else [lien()],
        "parcours": parcours,
        "source_sheet": sheet, "source_row": 10 + ac_ordre,
    }


def sample_records():
    return [
        # 2 AC pointent le MÊME EC (dédup attendue) + un EC S2
        record(ac_ordre=1),
        record(ac_ordre=2, ac_desc="Qualifier une situation",
               liens=[lien(),
                      lien(sem=2, ua_code="UAF201", ec_code="DROIT201",
                           ec_libelle="Droit des personnes")]),
        # EC sans code réel -> module_code généré S1_...
        record(sheet="Compétence 2", ordre=2, nom="Communiquer",
               ac_ordre=1, ac_desc="Rédiger",
               liens=[lien(ec_code=None,
                           ec_libelle="Méthodologie du travail universitaire",
                           ua_code=None, ua_type="UA Transv.")]),
        # parcours (bande période 5 / Privé)
        record(sheet="Compétence 3", ordre=3, nom="Plaider",
               niveau=3, ac_ordre=1, ac_desc="Argumenter",
               liens=[lien(sem=5, ua_code="UAF503", ec_code="DROIT501",
                           ec_libelle="Procédure civile",
                           parcours="PRIVE")]),
        # AC sans lien : ignoré côté curriculum, conservé côté competence
        record(sheet="Compétence 2", ordre=2, nom="Communiquer",
               ac_ordre=2, ac_desc="Présenter", liens=[]),
    ]


def normalized(records=None):
    return {"records": records if records is not None else sample_records(),
            "quality_report": {"input_file": "DROIT_ref.xlsx",
                               "warnings": [], "errors": []}}


def run(records=None):
    return USMBLicenceCurriculumTransformer().transform(normalized(records))


# =====================================================
# Contrat R4 (dont le point de vigilance ac_* vides)
# =====================================================

def test_canonical_contrat_r4():
    problems = validate_curriculum_canonical(run()["canonical"])
    assert not problems, "\n".join(problems)


def test_flat_contrat_r4_avec_ac_vides():
    """Point de vigilance validé : ac_id/ac_description PRÉSENTS mais
    vides doivent passer le contrat (les liens AC↔EC sont côté competence)."""
    flat = run()["flat"]
    problems = validate_flat_rows(flat, "curriculum")
    assert not problems, "\n".join(problems)
    assert all(row["ac_id"] == "" and row["ac_description"] == ""
               for row in flat)


# =====================================================
# Canonique
# =====================================================

def test_programme_conventions_licence():
    prog = run()["canonical"]
    assert prog.id == "USMB_DROIT"
    assert prog.type == "Licence" and prog.niveau == "Bac+3"
    assert prog.ects_total == 180.0 and prog.duree == 3


def test_periodes_ects_zero():
    prog = run()["canonical"]
    assert [p.numero for p in prog.periodes] == [1, 2, 5]
    assert all(p.ects == 0.0 for p in prog.periodes)
    assert all(p.id == f"S{p.numero}" for p in prog.periodes)


def test_ua_groupes_et_parcours_en_contrainte():
    prog = run()["canonical"]
    s1 = next(p for p in prog.periodes if p.numero == 1)
    codes = {g.code for g in s1.groupes_elements_pedagogiques}
    assert "UAF101" in codes
    s5 = next(p for p in prog.periodes if p.numero == 5)
    g_prive = next(g for g in s5.groupes_elements_pedagogiques
                   if g.contrainte == "PRIVE")
    assert g_prive.code == "UAF503_PRIVE"
    assert g_prive.type == "UAF"


def test_ec_zero_et_dedupliques():
    prog = run()["canonical"]
    s1 = next(p for p in prog.periodes if p.numero == 1)
    uaf101 = next(g for g in s1.groupes_elements_pedagogiques
                  if g.code == "UAF101")
    # DROIT101 coché par 2 AC -> UN seul élément
    assert [e.id for e in uaf101.elements_pedagogiques] == ["S1_DROIT101"]
    e = uaf101.elements_pedagogiques[0]
    assert e.credits == 0.0 and e.cm == 0.0 and e.td == 0.0 \
        and e.tp == 0.0 and e.projet == 0.0 and e.volume_total == 0.0
    assert e.nom == "Introduction au droit privé"
    assert e.acquis_apprentissage == []      # séparation des domaines


def test_module_code_genere_prefixe_non_double():
    """Les codes générés S1_... ne doivent pas devenir S1_S1_..."""
    prog = run()["canonical"]
    s1 = next(p for p in prog.periodes if p.numero == 1)
    ids = [e.id for g in s1.groupes_elements_pedagogiques
           for e in g.elements_pedagogiques]
    assert "S1_METHODOLOGIE_DU_TRAVAIL_UNIVERSITAIRE" in ids
    assert not any(i.startswith("S1_S1_") for i in ids)


# =====================================================
# Cohérence inter-domaines (la jointure frontend)
# =====================================================

def test_coherence_module_codes_avec_competence():
    """Chaque référence ac.modules (competence) doit correspondre à un
    élément du curriculum (id se terminant par le même module_code)."""
    records = sample_records()
    comp = USMBLicenceCompetenceTransformer().transform(normalized(records))
    curr = USMBLicenceCurriculumTransformer().transform(normalized(records))

    element_ids = {e.id for p in curr["canonical"].periodes
                   for g in p.groupes_elements_pedagogiques
                   for e in g.elements_pedagogiques}
    refs = {m for row in comp["flat"] if row["modules"]
            for m in row["modules"].split(", ")}
    for ref in refs:
        assert ref in element_ids or any(
            eid.endswith(f"_{ref}") for eid in element_ids), \
            f"référence {ref} sans entité curriculum"


# =====================================================
# Quality report + erreurs
# =====================================================

def test_quality_report_lite():
    q = run()["quality_report"]
    assert q["curriculum_type"] == "lite"
    assert q["data_origin"] == "reconstructed_from_competence_matrix"
    assert q["ects_renseignes"] is False
    assert q["heures_renseignees"] is False
    assert q["periodes"] == 3 and q["ecs"] == 4
    assert any("Squelette curriculaire" in w for w in q["warnings"])
    assert q["input_file"] == "DROIT_ref.xlsx"     # hérité du normalizer


def test_type_error_entree_non_normalisee():
    with pytest.raises(TypeError):
        USMBLicenceCurriculumTransformer().transform([{"pas": "normalisé"}])


def test_records_sans_aucun_lien_refuses():
    with pytest.raises(ValueError) as exc:
        run([record(liens=[])])
    assert "aucun EC exploitable" in str(exc.value)
    