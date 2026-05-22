import json
import logging
from pathlib import Path

from app.etl.extract.json_extractor import (
    extract_json
)

from app.etl.load.json_loader import (
    load_json
)

from app.etl.transform.transformer_factory import (
    TransformerFactory
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

def process_file(domain, file_path):
    """Process a single JSON file through ETL pipeline.
    
    Args:
        domain: Domain name (e.g., 'competence', 'curriculum')
        file_path: Path object to JSON file
    """
    file_name = file_path.name
    source_name = file_name.split("_")[0]
    
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

        raw_data = extract_json(
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

        output_folder = (
            Path(PROCESSED_FOLDER) / domain
        )

        output_folder.mkdir(
            parents=True,
            exist_ok=True
        )

        # ==========================================
        # OUTPUT FILE
        # ==========================================

        output_file = (
            output_folder /
            f"{file_name.replace('.json', '_processed.json')}"
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

        analytics_folder = (
            Path(ANALYTICS_FOLDER) / domain
        )

        analytics_folder.mkdir(
            parents=True,
            exist_ok=True
        )

        # ==========================================
        # ANALYTICS FILE
        # ==========================================

        analytics_file = (
            analytics_folder /
            f"{file_name.replace('.json', '_flat.json')}"
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
    """Process all JSON files in a domain folder.
    
    Args:
        domain: Domain name (folder in RAW_FOLDER)
    """
    domain_path = Path(RAW_FOLDER) / domain
    
    if not domain_path.exists():
        logger.warning(f"Domain folder not found: {domain_path}")
        return

    logger.info(f"Starting pipeline for domain: {domain}")
    
    json_files = list(domain_path.glob("*.json"))
    
    if not json_files:
        logger.warning(f"No JSON files found in {domain_path}")
        return

    for file_path in json_files:
        try:
            process_file(domain, file_path)
        except Exception as e:
            logger.error(f"Failed to process {file_path}: {e}")
            continue


# ==========================================
# MAIN PIPELINE
# ==========================================

def run_pipeline():
    """Run the complete ETL pipeline for all domains."""
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