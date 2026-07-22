# -*- coding: utf-8 -*-
"""
Tests AES-A1 (USMB Licence) — mapping des groupes UA/UAF/UAI/UAM +
regle metier generique UAI (individualisation / choix).

Deux niveaux :

1. Tests AES sur fixture REELLE (le classeur AES est le cas qui a revele
   le bug d'extraction des en-tetes de groupe). Ils prouvent :
   - plus aucun module dans un groupe generique « UA » ;
   - les modules-cles confirmes par l'audit sont dans le bon groupe ;
   - aucun groupe vide (ex. l'ex-« S6_UAI_UAM » aberrant) ;
   - les sous-groupes UAI de specialisation existent (S5/S6).
   Ils sont SKIPPES si la fixture n'est pas presente.

2. Tests GENERIQUES de la regle UAI (records synthetiques nourris
   directement au transformer, sans fichier) : quand un semestre contient
   >= 2 groupes UAI ils sont regroupes sous un composite « choix » ; UAF,
   UAM et UA n'y entrent jamais ; un seul UAI reste direct. La regle vaut
   pour TOUTE licence USMB, AES n'est qu'un exemple.

Lancer depuis backend_python :
    python -m pytest tests/test_usmb_licence_aes_group_mapping.py -v
"""

import os
import re
import unicodedata
from pathlib import Path

import pytest

from app.etl.transform.curriculum.USMB_licence_curriculum_transformer import (
    USMBLicenceCurriculumTransformer,
)

_AES_XLSX = os.getenv("AES_XLSX") or str(
    Path(__file__).parent / "fixtures"
    / "AES_Re_fe_rentiel_compe_tences_Licence_AES_v2.xlsx"
)


def _iter_all_groups(periode):
    """Descend les composites : yield chaque groupe (composite + feuilles)."""
    for g in periode.groupes_elements_pedagogiques:
        sub = getattr(g, "groupes_elements_pedagogiques", None)
        if sub is not None:
            yield g
            for child in sub:
                yield child
        else:
            yield g


def _module_group(programme, sem, module_nom):
    for periode in programme.periodes:
        if periode.numero != sem:
            continue
        for g in _iter_all_groups(periode):
            if getattr(g, "elements_pedagogiques", None) is None:
                continue
            for e in g.elements_pedagogiques:
                if e.nom == module_nom:
                    return g.code
    return None


@pytest.fixture(scope="module")
def aes_programme():
    if not os.path.exists(_AES_XLSX):
        pytest.skip("Fixture AES absente : %s" % _AES_XLSX)
    from app.etl.extract.excel_extractor import extract_excel
    from app.etl.normalize.usmb_licence_competence_normalizer import (
        USMBLicenceCompetenceNormalizer,
    )
    env = extract_excel(_AES_XLSX)
    normalized = USMBLicenceCompetenceNormalizer().normalize(env)
    result = USMBLicenceCurriculumTransformer().transform(normalized)
    return result["canonical"]


# --- 1. Tests AES (fixture reelle) ----------------------------------------

def test_aes_no_generic_ua_group(aes_programme):
    offenders = []
    for periode in aes_programme.periodes:
        for g in _iter_all_groups(periode):
            elems = getattr(g, "elements_pedagogiques", None)
            if elems and (g.code == "UA" or getattr(g, "type", None) == "UA"):
                offenders.append((periode.id, g.code, len(elems)))
    assert offenders == [], "Groupes UA generiques peuples : %s" % offenders


def test_aes_key_modules_are_in_expected_groups(aes_programme):
    expected = {
        (1, "Anglais"): "UAM",
        (1, "LV2"): "UAM",
        (1, "MTU"): "UAM",
        (1, "SPORT"): "UAM",
        (5, "Ateliers BoxIpro"): "UAI_PRO",
        (5, "Comptabilite approfondie".replace("Comptabilite", "Comptabilité")): "UAI_ECOENTREPRISE",
        (5, "GRH2"): "UAI_ECOENTREPRISE",
        (5, "Strategie de communication".replace("Strategie", "Stratégie")): "UAI_ECOENTREPRISE",
        (5, "Culture administrative"): "UAI_CONCOURS",
        (5, "Note de synthese".replace("synthese", "synthèse")): "UAI_CONCOURS",
        (5, "Preparation orale".replace("Preparation", "Préparation")): "UAI_CONCOURS",
        (6, "Analyse financiere".replace("financiere", "financière")): "UAI_ECOENTREPRISE",
        (6, "Ateliers pro"): "UAI_PRO",
        (6, "Droit des collectivites territoriales".replace("collectivites", "collectivités")): "UAF_DROIT",
        (6, "Droit general des societes".replace("general", "général").replace("societes", "sociétés")): "UAF_DROIT",
        (6, "Initiative etudiante".replace("etudiante", "étudiante")): "UAM",
        (6, "LV2"): "UAM",
        (6, "SPORT"): "UAM",
    }
    wrong = {}
    for (sem, nom), want in expected.items():
        got = _module_group(aes_programme, sem, nom)
        if got != want:
            wrong[(sem, nom)] = "attendu %s, obtenu %s" % (want, got)
    assert wrong == {}, "Modules mal classes : %s" % wrong


def test_aes_no_empty_groups(aes_programme):
    empties = []
    for periode in aes_programme.periodes:
        for g in _iter_all_groups(periode):
            elems = getattr(g, "elements_pedagogiques", None)
            if elems is not None and len(elems) == 0:
                empties.append("%s_%s" % (periode.id, g.code))
    assert empties == [], "Groupes vides trouves : %s" % empties
    all_codes = {g.code for p in aes_programme.periodes
                 for g in _iter_all_groups(p)}
    assert "UAI_UAM" not in all_codes


def test_aes_source_groups_present(aes_programme):
    codes_by_sem = {}
    for periode in aes_programme.periodes:
        codes_by_sem[periode.numero] = {
            g.code for g in _iter_all_groups(periode)
        }
    assert {"UAI_ECOENTREPRISE", "UAI_PRO", "UAI_CONCOURS"} <= codes_by_sem[5]
    assert {"UAF_DROIT", "UAI_ECOENTREPRISE"} <= codes_by_sem[6]


# --- 2. Tests GENERIQUES de la regle UAI (records synthetiques) ------------

def _slug(text, sem):
    t = unicodedata.normalize("NFKD", text)
    t = "".join(c for c in t if not unicodedata.combining(c))
    s = re.sub(r"[^A-Za-z0-9]+", "_", t.upper()).strip("_")[:40].rstrip("_")
    return "S%s_%s" % (sem, s)


def _lien(sem, ua_type, ec_libelle):
    return {"semestre": sem, "ua_type": ua_type, "ua_code": None,
            "ec_code": None, "ec_libelle": ec_libelle,
            "module_code": _slug(ec_libelle, sem), "parcours": None}


def _record(liens, ordre=1, ac_ordre=1):
    return {
        "programme_id": "USMB_TESTLIC", "programme_nom": "Licence Test",
        "source_name": "usmb_licence",
        "competence_ordre": ordre, "competence_nom": "Competence test",
        "composantes": [], "rncp": None,
        "niveau": 1, "niveau_description": None,
        "ac_ordre": ac_ordre, "ac_description": "AC test",
        "liens": liens, "parcours": None,
        "source_sheet": "Competence 1", "source_row": 10 + ac_ordre,
    }


def _transform(records):
    return USMBLicenceCurriculumTransformer().transform(
        {"records": records, "quality_report": {"warnings": []}}
    )["canonical"]


def _find_periode(programme, sem):
    return next(p for p in programme.periodes if p.numero == sem)


def test_usmb_uai_groups_are_composited_when_multiple():
    programme = _transform([_record([
        _lien(5, "UAF Eco", "Economie monetaire"),
        _lien(5, "UAM", "Anglais"),
        _lien(5, "UAI Eco Entreprise", "Comptabilite approfondie"),
        _lien(5, "UAI Pro", "Ateliers BoxIpro"),
        _lien(5, "UAI concours", "Note de synthese"),
    ])])
    periode = _find_periode(programme, 5)
    composites = [g for g in periode.groupes_elements_pedagogiques
                  if getattr(g, "groupes_elements_pedagogiques", None)
                  is not None]
    assert len(composites) == 1
    comp = composites[0]
    assert comp.code == "UAI"
    assert comp.type == "UAI"
    assert comp.contrainte
    child_codes = {g.code for g in comp.groupes_elements_pedagogiques}
    assert child_codes == {"UAI_ECOENTREPRISE", "UAI_PRO", "UAI_CONCOURS"}


def test_usmb_uai_composite_excludes_uaf_uam_ua():
    programme = _transform([_record([
        _lien(5, "UAF Eco", "Economie monetaire"),
        _lien(5, "UAF Droit", "Droit du travail"),
        _lien(5, "UAM", "Anglais"),
        _lien(5, "UAI Eco Entreprise", "Comptabilite approfondie"),
        _lien(5, "UAI Pro", "Ateliers BoxIpro"),
    ])])
    periode = _find_periode(programme, 5)
    comp = next(g for g in periode.groupes_elements_pedagogiques
                if getattr(g, "groupes_elements_pedagogiques", None)
                is not None)
    for child in comp.groupes_elements_pedagogiques:
        assert child.code.startswith("UAI")
        assert child.type == "UAI"
    top_codes = {g.code for g in periode.groupes_elements_pedagogiques}
    assert "UAF_ECO" in top_codes and "UAF_DROIT" in top_codes
    assert "UAM" in top_codes


def test_usmb_single_uai_not_composited():
    programme = _transform([_record([
        _lien(1, "UAF Eco", "Intro economie"),
        _lien(1, "UAM", "Anglais"),
        _lien(1, "UAI", "Intro a l'anthropologie"),
    ])])
    periode = _find_periode(programme, 1)
    composites = [g for g in periode.groupes_elements_pedagogiques
                  if getattr(g, "groupes_elements_pedagogiques", None)
                  is not None]
    assert composites == []
    top_codes = {g.code for g in periode.groupes_elements_pedagogiques}
    assert "UAI" in top_codes


def test_usmb_no_empty_group_and_aberrant_header_reported():
    result = USMBLicenceCurriculumTransformer().transform({
        "records": [_record([
            _lien(6, "UAF Eco", "Economie industrielle"),
            _lien(6, "UAI Eco Entreprise", "Analyse financiere"),
            _lien(6, "UAI Pro", "Ateliers pro"),
            _lien(6, "UAM", "Anglais"),
            _lien(6, "UAI UAM", "Anglais"),
        ])],
        "quality_report": {"warnings": []},
    })
    programme = result["canonical"]
    report = result["quality_report"]
    all_codes = {g.code for p in programme.periodes
                 for g in _iter_all_groups(p)}
    assert "UAI_UAM" not in all_codes
    assert report.get("aberrant_headers")
    for periode in programme.periodes:
        for g in _iter_all_groups(periode):
            elems = getattr(g, "elements_pedagogiques", None)
            if elems is not None:
                assert len(elems) > 0


def test_usmb_uai_variants_merge_to_same_code():
    programme = _transform([
        _record([
            _lien(5, "UAI Eco Entreprise", "Comptabilite approfondie"),
            _lien(5, "UAI Pro", "Ateliers BoxIpro"),
        ], ac_ordre=1),
        _record([
            _lien(5, "UAI EcoEntreprise", "GRH2"),
            _lien(5, "UAI Pro", "Portfolio"),
        ], ordre=2, ac_ordre=1),
    ])
    periode = _find_periode(programme, 5)
    comp = next(g for g in periode.groupes_elements_pedagogiques
                if getattr(g, "groupes_elements_pedagogiques", None)
                is not None)
    codes = [g.code for g in comp.groupes_elements_pedagogiques]
    assert codes.count("UAI_ECOENTREPRISE") == 1
    ecoent = next(g for g in comp.groupes_elements_pedagogiques
                  if g.code == "UAI_ECOENTREPRISE")
    noms = {e.nom for e in ecoent.elements_pedagogiques}
    assert {"Comptabilite approfondie", "GRH2"} <= noms