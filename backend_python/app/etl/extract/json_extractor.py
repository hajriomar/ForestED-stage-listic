import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_json(file_path: str):
    """Extract JSON data from file with error handling.
    
    Args:
        file_path: Path to the JSON file
        
    Returns:
        dict: Parsed JSON data
        
    Raises:
        FileNotFoundError: If file does not exist
        json.JSONDecodeError: If file is not valid JSON
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