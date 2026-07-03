"""
Pipeline ETL principal du projet ForestED.

Ce module orchestre l'ensemble du processus ETL :

1. Parcours des données brutes organisées
   par domaine et par source.

2. Extraction des fichiers (JSON, Excel, CSV).

3. Normalisation vers des records métier communs
   via NormalizerFactory.

4. Sélection automatique du transformer
   approprié via TransformerFactory.

5. Transformation des données vers :
   - un modèle canonique respectant
     le méta-modèle métier,
   - un format flat destiné à l'analyse.

6. Sauvegarde des résultats dans :
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
from app.etl.normalize.normalizer_factory import NormalizerFactory   # ← ajout
from app.etl.transform.transformer_factory import TransformerFactory
from app.etl.load.json_loader import load_json


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

RAW_FOLDER       = "app/data/raw"
PROCESSED_FOLDER = "app/data/processed"
ANALYTICS_FOLDER = "app/data/analytics"


# ==========================================
# PROCESS FILE
# ==========================================

def process_file(domain, source_name, file_path):
    """
    Traiter un fichier unique via le pipeline ETL.

    Flux :
        Extract → Normalize → Transform → Load

    Args:
        domain      : "competence" | "curriculum"
        source_name : "but" | "polytech" | …
        file_path   : chemin du fichier source
    """
    file_name = file_path.name
    logger.info(f"Processing [{domain}/{source_name}] : {file_name}")

    try:
        # ==========================================
        # EXTRACT
        # ==========================================

        extractor = ExtractorFactory.get_extractor(file_path)
        extracted = extractor(str(file_path))

        # ==========================================
        # NORMALIZE                                 ← ajout
        # ==========================================

        normalizer = NormalizerFactory.get_normalizer(domain, source_name)
        records    = normalizer.normalize(extracted)

        # ==========================================
        # TRANSFORM
        # ==========================================

        transformer = TransformerFactory.get_transformer(domain, source_name)
        result      = transformer.transform(records)

        # ==========================================
        # CANONICAL DATA
        # ==========================================

        canonical_data = result.get("canonical")
        flat_data      = result.get("flat", [])

        # ==========================================
        # SAVE CANONICAL
        # ==========================================

        output_folder = Path(PROCESSED_FOLDER) / domain / source_name
        output_folder.mkdir(parents=True, exist_ok=True)

        output_file = output_folder / f"{file_path.stem}_processed.json"
        load_json(canonical_data, str(output_file))

        logger.info(f"Generated canonical: {output_file}")

        # ==========================================
        # SAVE FLAT / ANALYTICS
        # ==========================================

        analytics_folder = Path(ANALYTICS_FOLDER) / domain / source_name
        analytics_folder.mkdir(parents=True, exist_ok=True)

        analytics_file = analytics_folder / f"{file_path.stem}_flat.json"

        with open(analytics_file, "w", encoding="utf-8") as f:
            json.dump(flat_data, f, indent=4, ensure_ascii=False)

        logger.info(f"Generated analytics: {analytics_file}")

    except FileNotFoundError as e:
        logger.error(f"File not found: {file_path} - {e}")
        raise
    except ValueError as e:
        logger.error(f"Normalizer/Transformer error for {file_name}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error processing {file_name}: {e}")
        raise


# ==========================================
# RUN DOMAIN
# ==========================================

def run_domain_pipeline(domain):
    """
    Traiter tous les fichiers d'un domaine.

    Args:
        domain : "competence" | "curriculum"
    """
    domain_path = Path(RAW_FOLDER) / domain

    if not domain_path.exists():
        logger.warning(f"Domain folder not found: {domain_path}")
        return

    logger.info(f"Starting pipeline for domain: {domain}")

    source_folders = [p for p in domain_path.iterdir() if p.is_dir()]

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
        files = [f for f in files if not f.name.startswith("~$")]

        logger.info(f"{len(files)} files found for {domain}/{source_name}")

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
    """Exécuter le pipeline ETL complet (tous les domaines)."""
    run_domain_pipeline("competence")
    run_domain_pipeline("curriculum")
    print("Pipeline ETL complète terminée.")


def main():
    import sys

    logger.info("Starting main pipeline")

    if len(sys.argv) == 5 and sys.argv[1] == "file":
        domain      = sys.argv[2]
        source_name = sys.argv[3]
        file_path   = Path(sys.argv[4])
        process_file(domain, source_name, file_path)
        print("Traitement du fichier terminé.")
        return

    run_pipeline()


if __name__ == "__main__":
    main()