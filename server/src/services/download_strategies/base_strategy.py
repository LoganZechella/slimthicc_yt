from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, AsyncGenerator, Union
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class DownloadStrategy(ABC):
    """
    Base class for all download strategies
    """
    
    @abstractmethod
    async def get_info(self, url: str) -> Dict[str, Any]:
        """
        Get information about the media at the URL
        
        Args:
            url: The URL to get information about
            
        Returns:
            A dictionary of information about the media
        """
        pass
    
    @abstractmethod
    async def download(self, url: str, output_path: Union[str, Path]) -> Optional[str]:
        """
        Download media from the URL to the output path
        
        Args:
            url: The URL to download from
            output_path: The path to save the file to
            
        Returns:
            The path to the downloaded file if successful, None otherwise
        """
        pass
    
    @abstractmethod
    async def validate_url(self, url: str) -> bool:
        """
        Check if this strategy can handle the given URL
        
        Args:
            url: The URL to check
            
        Returns:
            True if this strategy can handle the URL, False otherwise
        """
        pass
    
    @abstractmethod
    async def cleanup(self):
        """
        Clean up any resources used by this strategy
        """
        pass 