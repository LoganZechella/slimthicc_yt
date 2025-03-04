from abc import ABC, abstractmethod
from typing import Dict, Optional, Callable, AsyncGenerator, Any, Union
from pathlib import Path

class DownloadStrategy(ABC):
    """Base class for download strategies."""
    
    @abstractmethod
    async def download(self, url: str, output_path: Path, quality: str) -> AsyncGenerator[Dict[str, any], None]:
        """
        Download audio from the given URL.
        
        Args:
            url: The URL to download from
            output_path: Path to save the downloaded file
            quality: Audio quality setting
            
        Yields:
            Dict containing download progress information:
            {
                'status': str ('downloading', 'processing', 'error', 'complete'),
                'progress': float (0-100),
                'error': Optional[str]
            }
        """
        pass
    
    @abstractmethod
    async def validate_url(self, url: str) -> bool:
        """
        Validate if the URL can be handled by this strategy.
        
        Args:
            url: URL to validate
            
        Returns:
            bool: True if URL can be handled, False otherwise
        """
        pass
    
    @abstractmethod
    async def get_info(self, url: str) -> Dict[str, any]:
        """
        Get information about the video/audio.
        
        Args:
            url: URL to get info for
            
        Returns:
            Dict containing metadata like title, duration, etc.
        """
        pass
    
    @abstractmethod
    async def cleanup(self):
        """Cleanup any temporary files or resources."""
        pass
        
    @staticmethod
    @abstractmethod
    def can_handle(url: str) -> bool:
        """
        Determine if this strategy can handle the given URL.
        
        Args:
            url: The URL to check
            
        Returns:
            True if this strategy can handle the URL, False otherwise
        """
        pass
        
    @abstractmethod
    async def run(self, task) -> AsyncGenerator[dict, None]:
        """
        Run the download task with this strategy.
        
        Args:
            task: The download task to run
            
        Yields:
            Progress updates
        """
        pass 