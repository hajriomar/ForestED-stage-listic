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

def _safe_storage_key(value):
    """Nettoie une clé de stockage issue du formulaire admin."""
    if value is None:
        return None

    key = str(value).strip()
    if not key:
        return None

    key = key.replace(" ", "_")

    if "/" in key or "\\" in key or ".." in key:
        raise ValueError("Nom de formation invalide.")

    return key
# ==========================================
# PROCESS FILE
# ==========================================

def process_file(domain, source_name, file_path, institution=None, formation=None):
    """
    Traiter un fichier unique via le pipeline ETL.

    Flux :
        Extract → Normalize → Transform → Load

    Args:
        domain      : "competence" | "curriculum"
        source_name : "but" | "polytech" | …
        file_path   : chemin du fichier source
        institution : code institution optionnel (formulaire admin). Utilisé
                      uniquement par les sources qui le comprennent (ex.
                      curriculum/unita, chemin Excel institution-specific).
                      Ignoré ailleurs -> comportement historique inchangé.
    """
    file_name = file_path.name
    logger.info(f"Processing [{domain}/{source_name}] : {file_name}")

    try:
        # ==========================================
        # EXTRACT
        # ==========================================

        extractor = ExtractorFactory.get_extractor(file_path)
        extracted = extractor(str(file_path))

        # Indice d'institution transmis au normalizer via l'enveloppe (les
        # autres normalizers ignorent cette clé -> aucun impact).
        if institution and isinstance(extracted, dict):
            extracted["institution_hint"] = institution

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
        # SAVE CANONICAL / PROCESSED
        # ==========================================

        output_folder = Path(PROCESSED_FOLDER) / domain / source_name
        output_folder.mkdir(parents=True, exist_ok=True)

        summary = {
            "success": True,
            "domain": domain,
            "source": source_name,
            "programme_id": getattr(canonical_data, "id", None),
        }

        if (domain, source_name) == ("curriculum", "unita"):
            # Multi-scope / multi-institution : on N'ÉCRASE PAS un fichier par
            # upload. On UPSERT le result dans un processed PARTAGÉ au niveau
            # programme (générique + institutions), sans toucher les autres
            # institutions. L'ancien json_loader n'est PAS utilisé ici (il
            # écraserait le fichier). Les autres sources gardent leur
            # comportement historique.
            from app.etl.load.curriculum_upsert_service import (
                CurriculumUpsertService,
            )
            programme_key = (
                _safe_storage_key(formation)
                or _safe_storage_key(file_path.stem)
                or summary["programme_id"]
            )

            output_file = output_folder / f"{programme_key}_processed.json"

            up = CurriculumUpsertService().upsert_result(
                result,
                str(output_file),
                programme_key=programme_key,
            )
            summary.update({
                "programme_id": programme_key,
                "output_path": str(output_file),
                "added": up["added"],
                "updated": up["updated"],
                "total_elements": up["total_elements"],
                "scopes": up["scopes"],
                "institutions": up["institutions"],
            })
            logger.info(
                "Upsert curriculum/unita -> %s (+%d / ~%d, total %d)",
                output_file, up["added"], up["updated"], up["total_elements"],
            )
        else:
            # Comportement historique : sauvegarde simple du canonique.
            output_file = output_folder / f"{file_path.stem}_processed.json"
            load_json(canonical_data, str(output_file))
            summary["output_path"] = str(output_file)
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

        # ==========================================
        # SAVE QUALITY REPORT (optionnel, non bloquant)
        # ==========================================
        # Certains transformers (usmb_licence) fournissent un rapport
        # qualité ; s'il est absent, comportement strictement inchangé.

        quality_report = result.get("quality_report")
        if quality_report:
            quality_file = analytics_folder / f"{file_path.stem}_quality.json"
            with open(quality_file, "w", encoding="utf-8") as f:
                json.dump(quality_report, f, indent=4, ensure_ascii=False)
            logger.info(f"Generated quality report: {quality_file}")
            summary["quality_summary"] = {
                "input_kind": quality_report.get("input_kind"),
                "warnings": len(quality_report.get("warnings", []) or []),
                "ambiguities": len(quality_report.get("ambiguities", []) or []),
            }

        summary["analytics_file"] = str(analytics_file)
        return summary

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