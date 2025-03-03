from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, AsyncGenerator, Union
import logging
from pathlib import Path

from ....models.download import DownloadTask

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
            A dictionary containing information about the media
        """
        pass
    
    @abstractmethod
    async def download(self, task: DownloadTask, options: Optional[dict] = None) -> AsyncGenerator[dict, None]:
        """
        Download the media at the specified URL
        
        Args:
            task: The download task containing URL and metadata
            options: Optional parameters for the download
            
        Yields:
            Progress updates as dictionaries
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
    
    @abstractmethod
    async def run(self, task: DownloadTask) -> AsyncGenerator[dict, None]:
        """
        Run the download strategy for a task
        
        Args:
            task: The download task to process
            
        Yields:
            Progress updates as dictionaries
        """
        pass
    
    @staticmethod
    @abstractmethod
    def can_handle(url: str) -> bool:
        """
        Check if this strategy can handle the given URL (static method)
        
        Args:
            url: The URL to check
            
        Returns:
            True if this strategy can handle the URL, False otherwise
        """
        pass 