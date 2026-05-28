"""
JSON extractor du pipeline ETL.

Ce module est responsable de l’extraction
et du chargement des fichiers JSON bruts.

Le rôle principal de l’extractor est :
- lire les fichiers JSON source,
- valider leur existence,
- parser le contenu JSON,
- gérer les erreurs de lecture,
- centraliser les logs d’extraction.

Ce composant représente l’étape Extract
du pipeline ETL.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_json(file_path: str):
    """
    Extraire des données depuis un fichier JSON.

    Cette fonction :
    - vérifie l’existence du fichier,
    - ouvre le fichier JSON,
    - parse son contenu,
    - retourne les données Python correspondantes.

    Args:
        file_path (str):
            Chemin du fichier JSON à charger.

    Returns:
        dict:
            Données JSON parsées.

    Raises:
        FileNotFoundError:
            Si le fichier n’existe pas.

        json.JSONDecodeError:
            Si le fichier contient
            un JSON invalide.

        Exception:
            Toute autre erreur inattendue
            pendant l’extraction.
    """
    
    file_path = Path(file_path)
    
    if not file_path.exists():
        logger.error(f"File not found: {file_path}")
        raise FileNotFoundError(f"File not found: {file_path}")
    
    try:
        with open(
            file_path,
            "r",
            encoding="utf-8"
        ) as f:
            data = json.load(f)
        logger.info(f"Successfully extracted data from {file_path}")
        return data
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {file_path}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error extracting {file_path}: {e}")
        raise