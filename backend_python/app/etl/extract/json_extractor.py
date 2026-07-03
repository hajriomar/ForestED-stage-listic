"""
json_extractor.py
=================
Extractor JSON du pipeline ETL ForestED.

Rôle : lire le fichier .json et retourner une enveloppe technique commune.
Ne contient aucune logique métier.

Enveloppe retournée
-------------------
{
    "file_name" : str,
    "file_type" : "json",
    "content"   : dict    # contenu JSON brut, intact
}

Pourquoi envelopper le contenu ?
---------------------------------
Sans enveloppe, le normalizer reçoit le contenu brut et doit deviner
qu'il s'agit d'un JSON.  Avec file_type="json", la détection est explicite
et ne repose pas sur la présence de certaines clés.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_json(file_path: str) -> dict:
    """
    Lit un fichier JSON et retourne son contenu dans une enveloppe commune.

    Args:
        file_path: chemin vers le fichier .json

    Returns:
        dict avec les clés file_name, file_type, content

    Raises:
        FileNotFoundError  : si le fichier n'existe pas
        json.JSONDecodeError : si le JSON est invalide
    """
    path = Path(file_path)

    if not path.exists():
        logger.error(f"Fichier introuvable : {path}")
        raise FileNotFoundError(f"Fichier introuvable : {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = json.load(f)

        logger.info(f"extract_json : données extraites depuis {path.name}")

        return {
            "file_name": path.name,
            "file_type": "json",
            "content":   content,       # contenu brut intact, sans transformation
        }

    except json.JSONDecodeError as e:
        logger.error(f"JSON invalide dans {path} : {e}")
        raise
    except Exception as e:
        logger.error(f"Erreur inattendue lors de l'extraction de {path} : {e}")
        raise