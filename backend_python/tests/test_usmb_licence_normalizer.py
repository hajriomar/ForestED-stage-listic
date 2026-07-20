# -*- coding: utf-8 -*-
"""
Tests Patch 2 (USMB v1) — USMBLicenceCompetenceNormalizer.

Chaque test construit un mini-xlsx reproduisant une variante réelle du
gabarit USMB, l'extrait avec extract_excel (enveloppe enrichie du Patch 1)
puis vérifie les records / le quality_report.

Lancer depuis backend_python :
    python -m pytest tests/test_usmb_licence_normalizer.py -v
"""

import shutil
from pathlib import Path

import pytest
from openpyxl import Workbook
from openpyxl.styles import PatternFill

from app.etl.extract.excel_extractor import extract_excel
from app.etl.normalize.usmb_licence_competence_normalizer import (
    USMBLicenceCompetenceNormalizer,
)

TEST_DIR = Path("./test_data_usmb_normalizer").resolve()


def setup_module(module):
    shutil.rmtree(TEST_DIR, ignore_errors=True)
    TEST_DIR.mkdir(parents=True, exist_ok=True)


def teardown_module(module):
    shutil.rmtree(TEST_DIR, ignore_errors=True)


# =====================================================
# Constructeur de feuille gabarit (position variable)
# =====================================================

def build_competence_sheet(ws, start_row=9, cross="x", bands=None,
                           ac_col_letter="B", niveau_merged=True):
    """Feuille au gabarit USMB. start_row = ligne de l'en-tête de bloc
    (Niveaux / Acquis / Ressources) — varie de 5 à 14 dans les vrais
    fichiers. bands : liste (colonne, libellé)."""
    ws["A1"] = "Titre de la compétence"
    ws["A2"] = "Résoudre un problème de test dans une situation donnée"
    ws["D1"] = "Composantes essentielles"
    ws["D2"] = "• en identifiant les données du problème"
    ws["D3"] = "• en mobilisant les règles appropriées"
    ws["G1"] = "N° Fiche RNCP"
    ws["H1"] = "RNCP12345"

    ac = ac_col_letter
    # colonnes de la matrice, décalées avec la colonne AC
    # (défaut B -> matrice C/D/E ; variante L1eg C -> matrice D/E/F)
    m1 = chr(ord(ac) + 1)   # EC 1 (code)
    m2 = chr(ord(ac) + 2)   # EC 2 (libellé sans code)
    m3 = chr(ord(ac) + 3)   # EC 3 (code, 2e période)

    ws[f"A{start_row}"] = "Niveaux de dévéloppement"
    ws[f"{ac}{start_row}"] = "Acquis d'apprentissage (ou apprentissages critiques)"

    bands = bands or [(m1, "période 1"), (m3, "période 2")]
    band_row = start_row + 1
    for col, label in bands:
        ws[f"{col}{band_row}"] = label

    # ligne UA + ligne EC
    ua_row, ec_row = band_row + 1, band_row + 2
    ws[f"{m1}{ua_row}"] = "UAF101"
    ws[f"{m3}{ua_row}"] = "UAF201"
    ws[f"{m1}{ec_row}"] = "TEST101_ABC"
    ws[f"{m2}{ec_row}"] = "Introduction au test logiciel"
    ws[f"{m3}{ec_row}"] = "TEST201_ABC"

    # données : Niveau 1 (2 AC) puis Niveau 2 (1 AC)
    d0 = ec_row + 1
    ws[f"A{d0}"] = "Niveau 1 : \nDécouvrir les tests"
    ws[f"{ac}{d0}"] = "• Comprendre un plan de test"
    ws[f"{m1}{d0}"] = cross
    ws[f"{m2}{d0}"] = cross
    ws[f"{ac}{d0+1}"] = "• Exécuter un cas de test simple"     # niveau hérité
    ws[f"{m1}{d0+1}"] = cross
    ws[f"A{d0+2}"] = "Niveau 2 : \nAutomatiser les tests"
    ws[f"{ac}{d0+2}"] = "• Écrire un script de test automatisé"
    ws[f"{m3}{d0+2}"] = cross
    return d0


def make_workbook(path, **kwargs):
    wb = Workbook()
    ws = wb.active
    ws.title = "Compétence 1"
    build_competence_sheet(ws, **kwargs)
    wb.save(path)
    return path


def run(path, config=None):
    return USMBLicenceCompetenceNormalizer(config).normalize(
        extract_excel(str(path)))


# =====================================================
# Marqueurs à positions variables
# =====================================================

@pytest.mark.parametrize("start_row", [5, 9, 14])
def test_marqueurs_positions_variables(start_row):
    path = make_workbook(TEST_DIR / f"POS{start_row}_ref.xlsx",
                         start_row=start_row)
    out = run(path)
    q = out["quality_report"]
    assert q["competences"] == 1
    assert q["acs"] == 3
    assert q["liens_ac_module"] == 4
    rec = out["records"][0]
    assert rec["competence_nom"].startswith("Résoudre un problème de test")
    assert rec["rncp"] == "RNCP12345"
    assert len(rec["composantes"]) == 2


# =====================================================
# Feuilles ignorées
# =====================================================

def test_feuille_cachee_ignoree():
    path = TEST_DIR / "CACHEE_ref.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Compétence 1"
    build_competence_sheet(ws)
    old = wb.create_sheet("Compétence 2")
    build_competence_sheet(old)
    old.sheet_state = "hidden"
    wb.save(path)

    out = run(path)
    q = out["quality_report"]
    assert q["competences"] == 1
    assert {"sheet": "Compétence 2", "raison": "feuille cachée"} \
        in q["sheets_ignored"]


def test_feuilles_regles_rncp_profil_ignorees():
    path = TEST_DIR / "IGNORE_ref.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Compétence 1"
    build_competence_sheet(ws)
    for name in ("Règles et exemples", "RNCP", "Blocs RNCP",
                 "Profil du diplômé"):
        extra = wb.create_sheet(name)
        extra["A1"] = "contenu quelconque"
    wb.save(path)

    out = run(path)
    q = out["quality_report"]
    assert q["competences"] == 1
    ignored = {s["sheet"] for s in q["sheets_ignored"]}
    assert ignored == {"Règles et exemples", "RNCP", "Blocs RNCP",
                       "Profil du diplômé"}


# =====================================================
# Croix et couleurs
# =====================================================

@pytest.mark.parametrize("cross", ["x", "X", "×", "✓"])
def test_croix_variantes(cross):
    path = make_workbook(TEST_DIR / f"CROIX{ord(cross[0])}_ref.xlsx",
                         cross=cross)
    assert run(path)["quality_report"]["liens_ac_module"] == 4


def test_liens_par_couleur_staps():
    """Aucune croix textuelle : les cellules COLORÉES de la matrice
    deviennent les liens (cas STAPS)."""
    path = TEST_DIR / "STAPS_ref.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "CompA"
    d0 = build_competence_sheet(ws, cross="")   # aucune croix
    fill = PatternFill(fill_type="solid", start_color="FF92D050")
    ws[f"C{d0}"].fill = fill
    ws[f"E{d0+2}"].fill = fill
    wb.save(path)

    out = run(path)
    q = out["quality_report"]
    assert q["liens_ac_module"] == 2
    assert any("COLORÉES" in w for w in q["warnings"])
    # AC 1 lié à TEST101_ABC (S1), AC 3 lié à TEST201_ABC (S2)
    ac1 = out["records"][0]
    assert ac1["liens"][0]["ec_code"] == "TEST101_ABC"
    assert ac1["liens"][0]["semestre"] == 1


# =====================================================
# Propagation du niveau + périodes + parcours
# =====================================================

def test_propagation_niveau_fusionne():
    out = run(make_workbook(TEST_DIR / "NIV_ref.xlsx"))
    recs = out["records"]
    assert [r["niveau"] for r in recs] == [1, 1, 2]     # AC2 hérite N1
    assert recs[0]["niveau_description"].startswith("Découvrir")
    assert recs[2]["niveau_description"].startswith("Automatiser")


def test_semestres_detectes():
    out = run(make_workbook(TEST_DIR / "SEM_ref.xlsx"))
    assert out["quality_report"]["semestres_detected"] == [1, 2]
    sems = {l["semestre"] for r in out["records"] for l in r["liens"]}
    assert sems == {1, 2}


def test_parcours_dans_bande_periode():
    """Cas Droit : « période 5 / Privé » -> parcours porté par le lien."""
    path = make_workbook(
        TEST_DIR / "PARC_ref.xlsx",
        bands=[("C", "période 5 / Privé"), ("E", "période 5 / Public")])
    out = run(path)
    q = out["quality_report"]
    assert sorted(q["parcours_detected"]) == ["PRIVE", "PUBLIC"]
    liens_ac1 = out["records"][0]["liens"]
    assert {l["parcours"] for l in liens_ac1} == {"PRIVE"}


def test_parcours_feuille_l3_staps():
    path = TEST_DIR / "L3_ref.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "ERGO PM L3"
    build_competence_sheet(ws)
    wb.save(path)
    out = run(path)
    rec = out["records"][0]
    assert rec["parcours"] == "ERGO_PM"
    assert any("ERGO_PM" in w and "niveau 3" in w
               for w in out["quality_report"]["warnings"])


# =====================================================
# Robustesse
# =====================================================

def test_colonne_ac_decalee():
    """Variante L1eg : AC en colonne C au lieu de B."""
    path = make_workbook(TEST_DIR / "DECAL_ref.xlsx", ac_col_letter="C",
                         bands=[("D", "Semestre 1"), ("E", "Semestre 2")])
    out = run(path)
    assert out["quality_report"]["acs"] == 3


def test_bornage_lignes_fantomes():
    """~1000 lignes déclarées ne doivent pas produire 1000 AC."""
    path = TEST_DIR / "FANTOME_ref.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Compétence 1"
    build_competence_sheet(ws)
    ws["Z1000"] = " "          # force max_row ~1000
    wb.save(path)
    out = run(path)
    assert out["quality_report"]["acs"] == 3


def test_hors_gabarit_math_erreur_claire():
    """Classeur sans aucune feuille gabarit (cas MATH) -> ValueError."""
    path = TEST_DIR / "MATH_ref.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Compétences MATH"
    ws["A2"] = "Produire un raisonnement mathématique"
    ws["G2"] = "Modéliser pour résoudre des problèmes"
    ws["A9"] = "Composantes essentielles"
    ws["A18"] = "Produire un raisonnement élémentaire"
    wb.save(path)

    with pytest.raises(ValueError) as exc:
        run(path)
    msg = str(exc.value)
    assert "hors gabarit" in msg
    assert "MATH" in msg


def test_non_excel_refuse():
    with pytest.raises(ValueError):
        USMBLicenceCompetenceNormalizer().normalize(
            {"file_type": "json", "content": {}})


# =====================================================
# Records homogènes + quality_report
# =====================================================

def test_records_homogenes_et_quality_report():
    out = run(make_workbook(TEST_DIR / "DROIT_ref.xlsx"))
    recs = out["records"]
    q = out["quality_report"]

    expected_keys = {"programme_id", "programme_nom", "source_name",
                     "competence_ordre", "competence_nom", "composantes",
                     "rncp", "niveau", "niveau_description", "ac_ordre",
                     "ac_description", "liens", "parcours",
                     "source_sheet", "source_row"}
    for rec in recs:
        assert set(rec.keys()) == expected_keys
        assert rec["source_name"] == "usmb_licence"
        assert rec["programme_id"] == "USMB_DROIT"
        for lien in rec["liens"]:
            assert set(lien.keys()) == {"semestre", "ua_type", "ua_code",
                                        "ec_code", "ec_libelle",
                                        "module_code", "parcours"}

    # descriptions AC brutes (jamais reformulées), puce retirée
    assert recs[0]["ac_description"] == "Comprendre un plan de test"

    for key in ("input_file", "sheets_read", "sheets_ignored", "competences",
                "niveaux", "acs", "liens_ac_module", "ec_columns_detected",
                "ec_without_code", "ua_without_code", "acs_without_lien",
                "semestres_detected", "parcours_detected",
                "warnings", "errors"):
        assert key in q
    assert q["competences"] == 1 and q["niveaux"] == 2 and q["acs"] == 3
    assert q["errors"] == []


def test_ec_sans_code_signale():
    """La colonne libellé sans code doit remonter dans ec_without_code."""
    out = run(make_workbook(TEST_DIR / "SANSCODE_ref.xlsx"))
    assert "Introduction au test logiciel" \
        in out["quality_report"]["ec_without_code"]


# =====================================================
# C1 : module_code définitif (source de vérité unique)
# =====================================================

def test_module_code_reel_prioritaire():
    """EC avec code réel -> module_code = code réel."""
    out = run(make_workbook(TEST_DIR / "MC1_ref.xlsx"))
    liens_ac1 = out["records"][0]["liens"]
    codes = {l["module_code"] for l in liens_ac1}
    assert "TEST101_ABC" in codes                # code réel conservé


def test_module_code_genere_si_libelle_seul():
    """EC sans code (libellé seul) -> module_code = S<sem>_<SLUG>."""
    out = run(make_workbook(TEST_DIR / "MC2_ref.xlsx"))
    liens_ac1 = out["records"][0]["liens"]
    genere = next(l for l in liens_ac1 if not l["ec_code"])
    assert genere["module_code"] == "S1_INTRODUCTION_AU_TEST_LOGICIEL"
    assert genere["ec_libelle"] == "Introduction au test logiciel"