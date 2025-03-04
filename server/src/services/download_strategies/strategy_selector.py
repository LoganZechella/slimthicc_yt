import re
from typing import List, Optional, Dict, Type, Tuple
import logging
import asyncio
import time
from src.services.download_strategies.base_strategy import DownloadStrategy
from src.services.download_strategies.pytube_strategy import PytubeStrategy
from src.services.download_strategies.invidious_strategy import InvidiousStrategy
from src.services.download_strategies.ytdlp_strategy import YtdlpStrategy
from src.services.download_strategies.spotify_strategy import SpotifyStrategy
from src.models.download import DownloadError

logger = logging.getLogger(__name__)

class StrategySelector:
    """Selects and manages download strategies."""
    
    def __init__(self):
        logger.info("Initializing StrategySelector with available strategies")
        self.strategies: List[DownloadStrategy] = []
        
        # Initialize strategies with error handling
        try:
            self.strategies.append(SpotifyStrategy())
            logger.info("Added SpotifyStrategy")
        except Exception as e:
            logger.error(f"Failed to initialize SpotifyStrategy: {e}")
            
        try:
            self.strategies.append(YtdlpStrategy())
            logger.info("Added YtdlpStrategy")
        except Exception as e:
            logger.error(f"Failed to initialize YtdlpStrategy: {e}")
            
        try:
            self.strategies.append(InvidiousStrategy())
            logger.info("Added InvidiousStrategy")
        except Exception as e:
            logger.error(f"Failed to initialize InvidiousStrategy: {e}")
            
        try:
            self.strategies.append(PytubeStrategy())
            logger.info("Added PytubeStrategy")
        except Exception as e:
            logger.error(f"Failed to initialize PytubeStrategy: {e}")
        
        self.strategy_failures: Dict[int, int] = {}
        self.strategy_health: Dict[int, bool] = {i: True for i in range(len(self.strategies))}  # Initialize health status
        self.max_failures = 3  # Max failures before marking strategy as unhealthy
        self.failure_reset_time = 300  # Seconds before resetting failure count
        self.last_failure_time = {i: 0 for i in range(len(self.strategies))}
        
        # Store recent error messages to detect patterns
        self.recent_errors: Dict[int, List[str]] = {i: [] for i in range(len(self.strategies))}
        
        # Critical error patterns that should trigger strategy failover
        self.critical_error_patterns = [
            r"signature extraction failed",
            r"Unable to extract signature",
            r"Unsupported URL",
            r"Precondition check failed",
            r"Not a YouTube URL",
            r"This video is unavailable",
            r"YouTube said: This video is unavailable",
            r"Unable to extract initial player response",
            r"Spotify API credentials are not set",
            r"Failed to initialize Spotify client"
        ]
        
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
                self.recent_errors[index] = []
                return True
            return False
        return True
        
    async def _mark_strategy_failure(self, index: int, error_message: str = None):
        """Mark a strategy failure and update health status."""
        now = asyncio.get_event_loop().time()
        self.strategy_failures[index] += 1
        self.last_failure_time[index] = now
        
        # Store recent error for pattern analysis
        if error_message:
            self.recent_errors[index].append(error_message)
            # Keep only last 5 errors
            if len(self.recent_errors[index]) > 5:
                self.recent_errors[index].pop(0)
                
            # Check for critical error patterns that should trigger immediate failover
            for pattern in self.critical_error_patterns:
                if re.search(pattern, error_message, re.IGNORECASE):
                    logger.warning(f"Critical error detected in strategy {index}: {pattern} in '{error_message}'")
                    self.strategy_health[index] = False
                    return
        
        if self.strategy_failures[index] >= self.max_failures:
            logger.warning(f"Strategy {index} marked as unhealthy after {self.max_failures} failures")
            self.strategy_health[index] = False
        
    async def get_strategy(self, url: str) -> Optional[Tuple[DownloadStrategy, int]]:
        """Get the first working strategy for a URL."""
        logger.info(f"Finding strategy for URL: {url}")
        
        # First check if this is a Spotify URL - these should be handled by the Spotify strategy
        if 'spotify.com' in url or 'spotify:' in url:
            logger.info("URL appears to be Spotify, checking Spotify strategy first")
            spotify_strategy = self.strategies[0]
            
            try:
                # Validate with Spotify strategy
                if await spotify_strategy.validate_url(url):
                    logger.info("Spotify strategy validated URL, using Spotify strategy")
                    return spotify_strategy, 0
                else:
                    logger.warning("URL looks like Spotify but Spotify strategy could not validate it")
            except Exception as e:
                logger.error(f"Error validating Spotify URL: {e}")
        
        # Fallback to checking all strategies
        for index, strategy in enumerate(self.strategies):
            # Skip unhealthy strategies
            if not await self._check_strategy_health(index):
                logger.info(f"Skipping unhealthy strategy {index} ({strategy.__class__.__name__})")
                continue
                
            try:
                logger.debug(f"Trying strategy {index} ({strategy.__class__.__name__})")
                if await strategy.validate_url(url):
                    logger.info(f"URL validated by strategy {index} ({strategy.__class__.__name__})")
                    return strategy, index
            except Exception as e:
                logger.error(f"Error validating URL with strategy {index} ({strategy.__class__.__name__}): {e}")
                await self._mark_strategy_failure(index, str(e))
            
        logger.warning(f"No suitable strategy found for URL: {url}")
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
            # Add timeout mechanism for info retrieval
            start_time = time.time()
            info = await asyncio.wait_for(strategy.get_info(url), timeout=15.0)
            elapsed = time.time() - start_time
            
            if not info:
                await self._mark_strategy_failure(index, "Empty info returned")
                # Try next strategy
                return await self.get_info_with_next_strategy(url, "Empty info returned")
                
            logger.info(f"Successfully got info using {strategy.__class__.__name__} in {elapsed:.2f} seconds")
            return info
        except asyncio.TimeoutError:
            logger.error(f"Timeout getting info with strategy {strategy.__class__.__name__}")
            await self._mark_strategy_failure(index, "Timeout error")
            return await self.get_info_with_next_strategy(url, "Timeout error")
        except Exception as e:
            logger.error(f"Error getting info with strategy {strategy.__class__.__name__}: {e}")
            await self._mark_strategy_failure(index, str(e))
            # Try next strategy
            return await self.get_info_with_next_strategy(url, str(e))
            
    async def get_info_with_next_strategy(self, url: str, error_reason: str = "") -> Dict[str, any]:
        """Try getting info with next available strategy."""
        logger.info(f"Trying next strategy due to: {error_reason}")
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
        self.recent_errors[index] = []
        
    async def try_next_strategy(self, url: str) -> Optional[Tuple[DownloadStrategy, int]]:
        """Try the next available strategy."""
        current = await self.get_strategy(url)
        if not current:
            return None
            
        current_strategy, current_index = current
        
        # Try remaining strategies
        for index in range(current_index + 1, len(self.strategies)):
            # Skip unhealthy strategies
            if not await self._check_strategy_health(index):
                logger.info(f"Skipping unhealthy next strategy {index}")
                continue
                
            strategy = self.strategies[index]
            try:
                if await strategy.validate_url(url):
                    logger.info(f"Switching to strategy {index}: {strategy.__class__.__name__}")
                    return strategy, index
            except Exception as e:
                logger.error(f"Error validating URL with strategy {strategy.__class__.__name__}: {e}")
                await self._mark_strategy_failure(index, str(e))
                continue
                
        return None 