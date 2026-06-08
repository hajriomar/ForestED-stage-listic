"""
Pipeline ETL principal du projet ForestED.

Ce module orchestre l'ensemble du processus ETL :

1. Parcours des données brutes organisées
   par domaine et par source.

2. Extraction des fichiers JSON.

3. Sélection automatique du transformer
   approprié via le Factory Pattern.

4. Transformation des données vers :
   - un modèle canonique respectant
     le méta-modèle métier,
   - un format flat destiné à l'analyse.

5. Sauvegarde des résultats dans :
   - data/processed
   - data/analytics

L'architecture du pipeline est conçue pour être
extensible afin d'ajouter facilement de nouvelles
sources de données ou de nouveaux transformers.
"""

import json
import logging
from pathlib import Path

from app.etl.extract.extractor_factory import ExtractorFactory

from app.etl.transform.transformer_factory import (
    TransformerFactory
)

from app.etl.load.json_loader import (
    load_json
)



# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

RAW_FOLDER = "app/data/raw"
PROCESSED_FOLDER = "app/data/processed"
ANALYTICS_FOLDER = "app/data/analytics"


# ==========================================
# PROCESS FILE
# ==========================================

def process_file(domain, source_name,file_path):
    """
    Traiter un fichier JSON unique via le pipeline ETL.

    Cette fonction :
    - extrait les données brutes,
    - sélectionne le transformer adapté,
    - transforme les données,
    - génère les sorties canonical et flat,
    - sauvegarde les résultats.

    Args:
        domain (str):
            Domaine des données :
            - competence
            - curriculum

        source_name (str):
            Source des données :
            - Polytech
            - autres futures sources

        file_path (Path):
            Chemin du fichier JSON brut.
    """
    file_name = file_path.name
    
    logger.info(f"Processing [{domain}] : {file_name}")

    try:
        # ==========================================
        # TRANSFORMER
        # ==========================================

        transformer = (
            TransformerFactory.get_transformer(
                domain,
                source_name
            )
        )

        # ==========================================
        # EXTRACT
        # ==========================================

        extractor = ExtractorFactory.get_extractor(file_path)

        raw_data = extractor(
            str(file_path)
            )

        # ==========================================
        # TRANSFORM
        # ==========================================

        result = transformer.transform(
            raw_data
        )

        # ==========================================
        # CANONICAL DATA
        # ==========================================

        canonical_data = result.get(
            "canonical"
        )

        # ==========================================
        # FLAT ANALYTICS DATA
        # ==========================================

        flat_data = result.get(
            "flat",
            []
        )

        # ==========================================
        # OUTPUT FOLDER
        # ==========================================

        output_folder = Path(PROCESSED_FOLDER) / domain / source_name

        output_folder.mkdir(
            parents=True,
            exist_ok=True
        )

        # ==========================================
        # OUTPUT FILE
        # ==========================================

        output_file = (
            output_folder /
            f"{file_path.stem}_processed.json"
         )

        # ==========================================
        # SAVE CANONICAL
        # ==========================================

        load_json(
            canonical_data,
            str(output_file)
        )

        logger.info(f"Generated canonical: {output_file}")

        # ==========================================
        # ANALYTICS FOLDER
        # ==========================================

        analytics_folder = Path(ANALYTICS_FOLDER) / domain / source_name

        analytics_folder.mkdir(
            parents=True,
            exist_ok=True
        )

        # ==========================================
        # ANALYTICS FILE
        # ==========================================

        analytics_file = (
        analytics_folder /
        f"{file_path.stem}_flat.json"
         )

        # ==========================================
        # SAVE FLAT DATA
        # ==========================================

        with open(
            analytics_file,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                flat_data,
                f,
                indent=4,
                ensure_ascii=False
            )

        logger.info(f"Generated analytics: {analytics_file}")
        
    except FileNotFoundError as e:
        logger.error(f"File not found: {file_path} - {e}")
        raise
    except ValueError as e:
        logger.error(f"Transformer error for {file_name}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error processing {file_name}: {e}")
        raise


# ==========================================
# RUN DOMAIN
# ==========================================

def run_domain_pipeline(domain):

    """
    Traiter tous les fichiers JSON d'un domaine.

    Cette fonction :
    - parcourt les dossiers sources,
    - détecte les fichiers JSON,
    - lance le traitement ETL de chaque fichier.

    Args:
        domain (str):
            Domaine des données :
            - competence
            - curriculum
    """
    domain_path = Path(RAW_FOLDER) / domain
    
    if not domain_path.exists():
        logger.warning(f"Domain folder not found: {domain_path}")
        return

    logger.info(f"Starting pipeline for domain: {domain}")
    
    source_folders = [
    path for path in domain_path.iterdir()
    if path.is_dir()
]

    if not source_folders:
        logger.warning(f"No source folders found in {domain_path}")
        return

    for source_path in source_folders:

        source_name = source_path.name

        files = []

        files.extend(source_path.glob("*.json"))
        files.extend(source_path.glob("*.xlsx"))
        files.extend(source_path.glob("*.xls"))
        files.extend(source_path.glob("*.csv"))
        files = [
        file_path
         for file_path in files
            if not file_path.name.startswith("~$")
          ]

        logger.info(
            f"{len(files)} files found for "
            f"{domain}/{source_name}"
        )

        for file_path in files:
            try:
                process_file(domain, source_name, file_path)
            except Exception as e:
                logger.error(f"Failed to process {file_path}: {e}")
                continue


# ==========================================
# MAIN PIPELINE
# ==========================================

def run_pipeline():
    """
    Exécuter le pipeline ETL complet.

    Cette fonction lance le traitement
    de tous les domaines supportés :
    - competence
    - curriculum
    """
    
    logger.info("Starting main pipeline")
    
    # ==========================================
    # COMPETENCE
    # ==========================================

    run_domain_pipeline(
        "competence"
    )

    # ==========================================
    # CURRICULUM
    # ==========================================

    run_domain_pipeline(
        "curriculum"
    )

    print(
        "Pipeline ETL complète terminée."
    )


if __name__ == "__main__":

    run_pipeline()