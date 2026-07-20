# -*- coding: utf-8 -*-
"""
Tests Patch 1 (USMB v1) — enrichissement additif d'extract_excel :
clés "visible" et "filled_cells" par feuille.

Vérifie :
1. feuille visible  -> visible=True
2. feuille cachée   -> visible=False (mais toujours PRÉSENTE dans l'enveloppe)
3. cellule colorée (rgb + theme) -> dans filled_cells
4. cellule blanche  -> absente de filled_cells
5. cellule sans remplissage -> absente de filled_cells
6. rows strictement inchangé vs comportement historique
7. les transformers existants ignorent les nouvelles clés (BUT / Polytech)

Lancer depuis backend_python :
    python -m pytest tests/test_excel_extractor_enriched.py -v
"""

import shutil
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import PatternFill
from openpyxl.styles.colors import Color

from app.etl.extract.excel_extractor import extract_excel

TEST_DIR = Path("./test_data_extractor_enriched").resolve()
XLSX = TEST_DIR / "sample.xlsx"


def setup_module(module):
    shutil.rmtree(TEST_DIR, ignore_errors=True)
    TEST_DIR.mkdir(parents=True, exist_ok=True)

    wb = Workbook()

    ws = wb.active
    ws.title = "Visible"
    ws["A1"] = "titre"
    ws["B2"] = "x"
    # cellule colorée (rgb jaune)
    ws["D14"] = None
    ws["D14"].fill = PatternFill(fill_type="solid", start_color="FFFFFF00")
    # cellule colorée (couleur de THÈME, cas STAPS)
    ws["E15"].fill = PatternFill(fill_type="solid",
                                 fgColor=Color(theme=5, tint=0.0))
    # cellule blanche explicite -> ne doit PAS être marquée
    ws["F16"] = "blanc"
    ws["F16"].fill = PatternFill(fill_type="solid", start_color="FFFFFFFF")
    # cellule avec valeur mais sans remplissage
    ws["G17"] = "sans fill"

    hidden = wb.create_sheet("Cachee")
    hidden["A1"] = "obsolete"
    hidden.sheet_state = "hidden"

    wb.save(XLSX)


def teardown_module(module):
    shutil.rmtree(TEST_DIR, ignore_errors=True)


def _sheet(env, name):
    return next(s for s in env["sheets"] if s["sheet_name"] == name)


def test_enveloppe_structure_et_cles():
    env = extract_excel(str(XLSX))
    assert env["file_type"] == "excel"
    assert env["file_name"] == "sample.xlsx"
    for s in env["sheets"]:
        assert set(s.keys()) == {"sheet_name", "rows", "visible", "filled_cells"}


def test_feuille_visible_true():
    assert _sheet(extract_excel(str(XLSX)), "Visible")["visible"] is True


def test_feuille_cachee_presente_et_false():
    """La feuille cachée reste dans l'enveloppe (pas de filtrage à
    l'extractor) mais est marquée visible=False."""
    env = extract_excel(str(XLSX))
    hidden = _sheet(env, "Cachee")
    assert hidden["visible"] is False
    assert hidden["rows"][0][0] == "obsolete"


def test_cellule_coloree_rgb_dans_filled_cells():
    assert "D14" in _sheet(extract_excel(str(XLSX)), "Visible")["filled_cells"]


def test_cellule_coloree_theme_dans_filled_cells():
    """Cas STAPS : les liens AC x EC sont des remplissages de THÈME."""
    assert "E15" in _sheet(extract_excel(str(XLSX)), "Visible")["filled_cells"]


def test_cellule_blanche_absente():
    assert "F16" not in _sheet(extract_excel(str(XLSX)), "Visible")["filled_cells"]


def test_cellule_sans_remplissage_absente():
    filled = _sheet(extract_excel(str(XLSX)), "Visible")["filled_cells"]
    assert "G17" not in filled
    assert "A1" not in filled and "B2" not in filled


def test_rows_strictement_inchange():
    """rows doit être identique à une lecture values_only directe
    (comportement historique de l'extractor)."""
    env = extract_excel(str(XLSX))
    wb = load_workbook(XLSX, data_only=True)
    for s in env["sheets"]:
        expected = [list(r) for r in wb[s["sheet_name"]].iter_rows(values_only=True)]
        assert s["rows"] == expected


def test_transformers_existants_ignorent_les_nouvelles_cles():
    """7. Non-régression structurelle : BUT et Polytech ne lisent que
    sheet_name/rows — l'enveloppe enrichie ne doit rien changer.
    (La non-régression complète est couverte par la suite pytest globale.)"""
    env = extract_excel(str(XLSX))

    # Polytech competence : normalize_excel concatène les rows des sheets.
    from app.etl.transform.competence.Polytech_competence_transformer import (
        PolytechTransformer,
    )
    rows = PolytechTransformer().normalize_excel(env)
    assert rows == [r for s in env["sheets"] for r in s["rows"]]

    # BUT curriculum : une feuille sans "Semestre n" est simplement ignorée,
    # clés supplémentaires ou pas — aucune exception, programme vide.
    from app.etl.transform.curriculum.BUT_curriculum_transformer import (
        BUTCurriculumTransformer,
    )
    result = BUTCurriculumTransformer().transform(
        {"file_name": "QLIO_BUT_test.xlsx", "sheets": env["sheets"]}
    )
    assert result["canonical"].periodes == []
    assert result["flat"] == []