"""
JSON loader du pipeline ETL.

Ce module est responsable de la sauvegarde
des données transformées au format JSON.

Le loader sérialise les modèles Pydantic
vers des fichiers JSON lisibles et structurés.

Fonctionnalités :
- création automatique des dossiers,
- sérialisation des modèles Pydantic,
- gestion des erreurs d’écriture,
- logging des opérations de sauvegarde.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_json(data, output_path):
    """
    Sauvegarder des données transformées
    dans un fichier JSON.

    Cette fonction :
    - crée automatiquement les dossiers nécessaires,
    - convertit les modèles Pydantic en dictionnaire,
    - écrit le JSON formaté sur disque.

    Args:
        data:
            Instance d’un modèle Pydantic
            à sérialiser.

        output_path (str):
            Chemin du fichier JSON de sortie.

    Raises:
        ValueError:
            Si l’objet fourni n’est pas
            un modèle Pydantic valide.

        IOError:
            Si le fichier ne peut pas
            être écrit sur disque.
    """
    output_path = Path(output_path)
    
    # Create parent directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        with open(
            output_path,
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                data.model_dump(),
                f,
                indent=4,
                ensure_ascii=False
            )
        logger.info(f"Successfully saved data to {output_path}")
    except AttributeError:
        logger.error(f"Data is not a Pydantic model: {type(data)}")
        raise ValueError(f"Expected Pydantic model, got {type(data)}")
    except IOError as e:
        logger.error(f"Failed to write file {output_path}: {e}")
        raise