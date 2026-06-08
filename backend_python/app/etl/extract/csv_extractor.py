"""
CSV extractor du pipeline ETL.

Ce module lit les fichiers CSV
et retourne une structure Python
normalisée pour les transformers.
"""

import csv
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_csv(file_path: str):
    """
    Extraire les données d'un fichier CSV.

    Returns:
        dict:
            {
                "file_name": "...",
                "rows": [...]
            }
    """

    file_path = Path(file_path)

    if not file_path.exists():
        logger.error(f"File not found: {file_path}")
        raise FileNotFoundError(
            f"File not found: {file_path}"
        )

    try:

        rows = []

        with open(
            file_path,
            "r",
            encoding="utf-8"
        ) as csv_file:

            reader = csv.DictReader(
                csv_file
            )

            for row in reader:
                rows.append(
                    dict(row)
                )

        logger.info(
            f"Successfully extracted CSV data from {file_path}"
        )

        return {
            "file_name": file_path.name,
            "rows": rows
        }

    except Exception as e:

        logger.error(
            f"Unexpected error extracting CSV {file_path}: {e}"
        )

        raise