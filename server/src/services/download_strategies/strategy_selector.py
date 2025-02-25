from typing import List, Optional, Dict, Type, Tuple
import logging
import asyncio
from .base import DownloadStrategy
from .pytube_strategy import PytubeStrategy
from .invidious_strategy import InvidiousStrategy
from .ytdlp_strategy import YtdlpStrategy
from src.models.download import DownloadError

logger = logging.getLogger(__name__)

class StrategySelector:
    """Selects and manages download strategies."""
    
    def __init__(self):
        logger.info("Initializing StrategySelector with available strategies")
        self.strategies: List[DownloadStrategy] = [
            YtdlpStrategy(),      # Try yt-dlp first (matches desktop app approach)
            InvidiousStrategy(),  # Then Invidious as backup
            PytubeStrategy()      # Finally pytube as last resort
        ]
        self.strategy_failures: Dict[int, int] = {}
        self.strategy_health: Dict[int, bool] = {i: True for i in range(3)}  # Initialize health status
        self.max_failures = 3  # Max failures before marking strategy as unhealthy
        self.failure_reset_time = 300  # Seconds before resetting failure count
        self.last_failure_time = {i: 0 for i in range(len(self.strategies))}
        logger.info(f"Initialized {len(self.strategies)} strategies")
        
    async def _check_strategy_health(self, index: int) -> bool:
        """Check if a strategy is healthy and reset failure count if needed."""
        now = asyncio.get_event_loop().time()
        if not self.strategy_health[index]:
            # Check if enough time has passed to retry
            if now - self.last_failure_time[index] > self.failure_reset_time:
                logger.info(f"Resetting health for strategy {index}")
                self.strategy_health[index] = True
                self.strategy_failures[index] = 0
                return True
            return False
        return True
        
    async def _mark_strategy_failure(self, index: int):
        """Mark a strategy failure and update health status."""
        now = asyncio.get_event_loop().time()
        self.strategy_failures[index] += 1
        self.last_failure_time[index] = now
        
        if self.strategy_failures[index] >= self.max_failures:
            logger.warning(f"Strategy {index} marked as unhealthy after {self.max_failures} failures")
            self.strategy_health[index] = False
        
    async def get_strategy(self, url: str) -> Optional[Tuple[DownloadStrategy, int]]:
        """Get the first working strategy for a URL."""
        for index, strategy in enumerate(self.strategies):
            try:
                if await strategy.validate_url(url):
                    return strategy, index
            except Exception as e:
                logger.error(f"Error validating URL with strategy {strategy.__class__.__name__}: {e}")
                continue
        return None
        
    async def get_info(self, url: str) -> Dict[str, any]:
        """
        Get information about the media at the URL using appropriate strategy.
        
        Args:
            url: URL to get info for
            
        Returns:
            Dict containing media information
            
        Raises:
            DownloadError if no strategy can handle the URL
        """
        logger.info(f"Getting info for URL: {url}")
        result = await self.get_strategy(url)
        if not result:
            logger.error("No suitable strategy found for getting info")
            raise DownloadError("No suitable download strategy found for URL")
            
        strategy, index = result
        try:
            info = await strategy.get_info(url)
            if not info:
                await self._mark_strategy_failure(index)
                # Try next strategy
                return await self.get_info_with_next_strategy(url)
            logger.info(f"Successfully got info using {strategy.__class__.__name__}")
            return info
        except Exception as e:
            logger.error(f"Error getting info with strategy {strategy.__class__.__name__}: {e}")
            await self._mark_strategy_failure(index)
            # Try next strategy
            return await self.get_info_with_next_strategy(url)
            
    async def get_info_with_next_strategy(self, url: str) -> Dict[str, any]:
        """Try getting info with next available strategy."""
        next_strategy = await self.try_next_strategy(url)
        if next_strategy:
            strategy, _ = next_strategy
            try:
                return await strategy.get_info(url)
            except Exception as e:
                logger.error(f"Error getting info with next strategy: {e}")
        raise DownloadError("Failed to get media info with all available strategies")
        
    async def cleanup(self):
        """Clean up all strategies."""
        for strategy in self.strategies:
            try:
                await strategy.cleanup()
            except Exception as e:
                logger.error(f"Error cleaning up strategy {strategy.__class__.__name__}: {e}")
                
    def register_strategy(self, strategy: DownloadStrategy):
        """Register a new download strategy."""
        logger.info(f"Registering new strategy: {strategy.__class__.__name__}")
        index = len(self.strategies)
        self.strategies.append(strategy)
        self.strategy_health[index] = True
        self.strategy_failures[index] = 0
        self.last_failure_time[index] = 0
        
    async def try_next_strategy(self, url: str) -> Optional[Tuple[DownloadStrategy, int]]:
        """Try the next available strategy."""
        current = await self.get_strategy(url)
        if not current:
            return None
            
        current_strategy, current_index = current
        
        # Try remaining strategies
        for index in range(current_index + 1, len(self.strategies)):
            strategy = self.strategies[index]
            try:
                if await strategy.validate_url(url):
                    return strategy, index
            except Exception as e:
                logger.error(f"Error validating URL with strategy {strategy.__class__.__name__}: {e}")
                continue
                
        return None 