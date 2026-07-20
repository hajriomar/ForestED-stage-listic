"""
excel_extractor.py
==================
Extractor Excel du pipeline ETL ForestED.

Rôle : lire le fichier .xlsx et retourner une enveloppe technique commune.
Ne contient aucune logique métier (pas de compétence, pas de niveau).

Enveloppe retournée
-------------------
{
    "file_name" : str,
    "file_type" : "excel",
    "sheets"    : [
        {
            "sheet_name"   : str,
            "rows"         : list[list],   # valeurs brutes (INCHANGÉ)
            "visible"      : bool,         # False si la feuille est cachée
            "filled_cells" : list[str],    # coordonnées ("D14") des cellules
                                           # à remplissage SOLIDE non blanc
        }
    ]
}

Notes sur les clés ajoutées (source USMB Licence)
-------------------------------------------------
- L'extractor ne FILTRE rien et n'INTERPRÈTE rien : les feuilles cachées
  restent dans l'enveloppe (visible=False) et filled_cells est une simple
  liste de coordonnées. C'est le normalizer de la source (ex.
  USMBLicenceCompetenceNormalizer) qui décide quoi en faire — certains
  référentiels (STAPS) marquent les liens AC x EC par la COULEUR des
  cellules plutôt que par des croix.
- Les transformers existants (BUT, Polytech) n'accèdent qu'à "sheet_name"
  et "rows" : les clés supplémentaires sont sans effet pour eux.
"""

import logging
from pathlib import Path

from openpyxl import load_workbook

logger = logging.getLogger(__name__)

# Remplissages considérés comme "pas une marque" : blanc et non-couleur.
_WHITE_RGB_SUFFIX = "FFFFFF"
_NO_COLOR_RGB = "00000000"


def _is_marked_fill(cell) -> bool:
    """
    True si la cellule porte un remplissage SOLIDE non vide et non blanc.

    Aucune interprétation de la couleur : on signale seulement que la
    cellule est visuellement marquée. Les couleurs de thème/indexées sont
    considérées comme des marques (les gabarits USMB utilisent la palette
    de thème) ; seuls le blanc explicite et l'absence de couleur sont
    exclus. Toute erreur de lecture de style est ignorée (jamais bloquant).
    """
    try:
        fill = cell.fill
        if fill is None or fill.fill_type != "solid":
            return False

        color = fill.start_color
        if color is None:
            return False

        ctype = getattr(color, "type", None)

        if ctype == "rgb":
            rgb = color.rgb
            if not isinstance(rgb, str):
                return False
            rgb = rgb.upper()
            if rgb == _NO_COLOR_RGB or rgb.endswith(_WHITE_RGB_SUFFIX):
                return False
            return True

        if ctype == "theme":
            # Thème 0 = fond clair (blanc) dans les palettes Office.
            theme = getattr(color, "theme", None)
            return isinstance(theme, int) and theme != 0

        if ctype == "indexed":
            # 64/65 = couleurs "système" (aucune couleur réelle).
            idx = getattr(color, "indexed", None)
            return isinstance(idx, int) and idx not in (64, 65)

        return False
    except Exception:  # pragma: no cover - défensif : jamais bloquant
        return False


def extract_excel(file_path: str) -> dict:
    """
    Lit un fichier Excel et retourne toutes ses feuilles.

    Args:
        file_path: chemin vers le fichier .xlsx / .xls

    Returns:
        dict avec les clés file_name, file_type, sheets

    Raises:
        FileNotFoundError: si le fichier n'existe pas
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {path}")

    workbook = load_workbook(filename=path, data_only=True)

    sheets = []
    for sheet in workbook.worksheets:
        rows = [list(row) for row in sheet.iter_rows(values_only=True)]
        if not rows:
            continue

        filled_cells = []
        try:
            for row in sheet.iter_rows():
                for cell in row:
                    if _is_marked_fill(cell):
                        filled_cells.append(cell.coordinate)
        except Exception:  # pragma: no cover - défensif : jamais bloquant
            logger.warning(
                "extract_excel : lecture des styles impossible sur '%s' "
                "(filled_cells partiel/vide).", sheet.title,
            )

        sheets.append({
            "sheet_name": sheet.title,
            "rows": rows,
            "visible": sheet.sheet_state == "visible",
            "filled_cells": filled_cells,
        })

    logger.info(f"extract_excel : {len(sheets)} feuilles extraites depuis {path.name}")

    return {
        "file_name": path.name,
        "file_type": "excel",
        "sheets":    sheets,
    }