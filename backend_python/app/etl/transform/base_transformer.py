from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


class BaseTransformer(ABC):
    """Abstract base class for data transformers.
    
    All transformers must inherit from this class and implement the transform method.
    """

    @abstractmethod
    def transform(self, raw_data: dict) -> dict:
        """Transform raw data into canonical and flat formats.
        
        Args:
            raw_data: Raw input data (typically dict from JSON)
            
        Returns:
            dict with keys 'canonical' (structured data) and 'flat' (flattened rows)
            
        Raises:
            NotImplementedError: If subclass does not implement this method
        """
        pass