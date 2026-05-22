import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_json(data, output_path):
    """Save data to JSON file with error handling.
    
    Args:
        data: Pydantic model instance to serialize
        output_path: Path where JSON will be saved
        
    Raises:
        ValueError: If data is not a valid Pydantic model
        IOError: If file cannot be written
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