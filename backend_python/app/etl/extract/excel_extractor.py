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
            "sheet_name" : str,
            "rows"       : list[list]   # valeurs brutes
        }
    ]
}
"""

import logging
from pathlib import Path

from openpyxl import load_workbook

logger = logging.getLogger(__name__)


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
        if rows:
            sheets.append({"sheet_name": sheet.title, "rows": rows})

    logger.info(f"extract_excel : {len(sheets)} feuilles extraites depuis {path.name}")

    return {
        "file_name": path.name,
        "file_type": "excel",
        "sheets":    sheets,
    }