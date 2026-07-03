#!/usr/bin/env python3
"""
ForestED ETL Pipeline Runner.

CLI pour lancer le pipeline ETL :
- complet
- par domaine
- par fichier
"""

import sys
import logging
import argparse
from pathlib import Path

from app.etl.pipeline import (
    run_pipeline,
    run_domain_pipeline,
    process_file,
)

DOMAINS = ["competence", "curriculum"]


def setup_logging(verbose: bool = False) -> None:
    """Configure les logs du pipeline."""
    level = logging.DEBUG if verbose else logging.INFO

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )


def build_parser() -> argparse.ArgumentParser:
    """Construit le CLI du pipeline."""
    parser = argparse.ArgumentParser(
        prog="run_pipeline.py",
        description="ForestED ETL Pipeline Runner",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Afficher les logs détaillés",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        help="Commande à exécuter",
    )

    subparsers.add_parser(
        "run",
        help="Lancer le pipeline complet",
    )

    domain_parser = subparsers.add_parser(
        "run-domain",
        help="Lancer le pipeline pour un domaine spécifique",
    )
    domain_parser.add_argument(
        "domain",
        choices=DOMAINS,
        help="Domaine à traiter",
    )

    file_parser = subparsers.add_parser(
        "run-file",
        help="Traiter un seul fichier JSON",
    )
    file_parser.add_argument(
        "domain",
        choices=DOMAINS,
        help="Domaine du fichier",
    )
    file_parser.add_argument(
        "file_path",
        type=Path,
        help="Chemin vers le fichier JSON",
    )

    return parser


def validate_file(file_path: Path) -> None:
    """Vérifie que le fichier existe et qu'il est bien un JSON."""
    if not file_path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {file_path}")

    if not file_path.is_file():
        raise ValueError(f"Le chemin n'est pas un fichier : {file_path}")

    if file_path.suffix.lower() != ".json":
        raise ValueError(f"Le fichier doit être au format JSON : {file_path}")


def main() -> int:
    """Point d'entrée principal du CLI."""
    parser = build_parser()
    args = parser.parse_args()

    setup_logging(args.verbose)
    logger = logging.getLogger("forested.cli")

    try:
        if args.command == "run":
            logger.info("Lancement du pipeline ETL complet")
            run_pipeline()
            logger.info("Pipeline ETL complet terminé avec succès")

        elif args.command == "run-domain":
            logger.info("Lancement du pipeline pour le domaine : %s", args.domain)
            run_domain_pipeline(args.domain)
            logger.info("Pipeline du domaine '%s' terminé avec succès", args.domain)

        elif args.command == "run-file":
            validate_file(args.file_path)
            logger.info("Traitement du fichier : %s", args.file_path)
            process_file(args.domain, args.file_path)
            logger.info("Fichier traité avec succès")

        return 0

    except Exception as exc:
        logger.exception("Échec du pipeline : %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())