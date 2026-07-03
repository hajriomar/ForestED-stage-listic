"""
csv_extractor.py
================
Extractor CSV du pipeline ETL ForestED.

Rôle : lire le fichier .csv et retourner une enveloppe technique commune.
Ne contient aucune logique métier.

Enveloppe retournée
-------------------
{
    "file_name" : str,
    "file_type" : "csv",
    "rows"      : list[dict]   # une ligne = un dict {colonne: valeur}
}
"""

import csv
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_csv(file_path: str) -> dict:
    """
    Lit un fichier CSV et retourne ses lignes sous forme de dicts.

    Args:
        file_path: chemin vers le fichier .csv

    Returns:
        dict avec les clés file_name, file_type, rows

    Raises:
        FileNotFoundError : si le fichier n'existe pas
    """
    path = Path(file_path)

    if not path.exists():
        logger.error(f"Fichier introuvable : {path}")
        raise FileNotFoundError(f"Fichier introuvable : {path}")

    try:
        rows = []
        with open(path, "r", encoding="utf-8") as csv_file:
            reader = csv.DictReader(csv_file)
            for row in reader:
                rows.append(dict(row))

        logger.info(f"extract_csv : {len(rows)} lignes extraites depuis {path.name}")

        return {
            "file_name": path.name,
            "file_type": "csv",
            "rows":      rows,
        }

    except Exception as e:
        logger.error(f"Erreur inattendue lors de l'extraction de {path} : {e}")
        raise