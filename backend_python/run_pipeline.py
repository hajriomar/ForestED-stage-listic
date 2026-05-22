#!/usr/bin/env python3
"""
ForestED ETL Pipeline Runner
"""
import sys
import logging
import argparse
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from app.etl.pipeline import (
    run_pipeline,
    run_domain_pipeline,
    process_file
)


def main():
    """Main entry point for pipeline runner."""
    parser = argparse.ArgumentParser(
        description="ForestED ETL Pipeline Runner"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Full pipeline command
    subparsers.add_parser(
        "run",
        help="Run full ETL pipeline for all domains"
    )
    
    # Domain pipeline command
    domain_parser = subparsers.add_parser(
        "domain",
        help="Run ETL pipeline for a specific domain"
    )
    domain_parser.add_argument(
        "domain",
        choices=["competence", "curriculum"],
        help="Domain to process"
    )
    
    # File pipeline command
    file_parser = subparsers.add_parser(
        "file",
        help="Process a single JSON file"
    )
    file_parser.add_argument(
        "domain",
        choices=["competence", "curriculum"],
        help="Domain of the file"
    )
    file_parser.add_argument(
        "file_path",
        type=str,
        help="Path to the JSON file"
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    try:
        if args.command == "run":
            logger.info("Starting full ETL pipeline")
            run_pipeline()
            logger.info("Pipeline completed successfully")
            
        elif args.command == "domain":
            logger.info(f"Starting ETL pipeline for domain: {args.domain}")
            run_domain_pipeline(args.domain)
            logger.info(f"Pipeline for domain '{args.domain}' completed successfully")
            
        elif args.command == "file":
            file_path = Path(args.file_path)
            if not file_path.exists():
                logger.error(f"File not found: {file_path}")
                return 1
            
            logger.info(f"Processing file: {file_path}")
            process_file(args.domain, file_path)
            logger.info("File processed successfully")
        
        return 0
        
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
