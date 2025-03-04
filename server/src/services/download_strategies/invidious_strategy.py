import asyncio
from pathlib import Path
from typing import Dict, Optional, AsyncGenerator, List, Tuple
import aiohttp
import logging
import json
import tempfile
import random
import time
import shutil
from urllib.parse import quote, urlparse
from src.services.download_strategies.base_strategy import DownloadStrategy
from src.services.ffmpeg_manager import ffmpeg_manager
from src.config.settings import settings
from src.models.download import DownloadTask
import re
import os
from urllib.parse import parse_qs

logger = logging.getLogger(__name__)

class InvidiousStrategy(DownloadStrategy):
    """YouTube download strategy using Invidious API."""
    
    def __init__(self):
        """Initialize the Invidious strategy."""
        super().__init__()
        self.temp_files = []
        self.session = None
        self._instances = None  # Lazy load instances
        self._instances_initialized = False
        self._default_instances = [
            "https://invidious.snopyta.org",
            "https://invidious.kavin.rocks",
            "https://vid.puffyan.us",
            "https://yt.artemislena.eu",
            "https://invidious.nerdvpn.de",
            "https://inv.riverside.rocks",
            "https://invidious.protokolla.fi"
        ]
        
        # Add additional instances from settings
        additional_instances = getattr(settings, "INVIDIOUS_FALLBACK_INSTANCES", [])
        if additional_instances:
            logger.info(f"Loaded {len(additional_instances)} additional Invidious instances from settings")
        
        # Don't initialize instances immediately to avoid startup errors
        logger.info("Initialized InvidiousStrategy with lazy loading")
        
    async def _initialize_instances(self):
        """Lazy initialize instances when needed."""
        if self._instances_initialized:
            return
            
        try:
            self._instances = self._default_instances.copy()
            
            # Add additional instances from settings
            additional_instances = getattr(settings, "INVIDIOUS_FALLBACK_INSTANCES", [])
            if additional_instances:
                self._instances.extend(additional_instances)
                
            # Remove duplicates while preserving order
            self._instances = list(dict.fromkeys(self._instances))
            
            logger.info(f"Initialized InvidiousStrategy with {len(self._instances)} instances")
            self._instances_initialized = True
        except Exception as e:
            logger.error(f"Error initializing Invidious instances: {e}")
            # Fallback to default instances
            self._instances = self._default_instances.copy()
            self._instances_initialized = True
        
    async def _get_session(self):
        """Get or create aiohttp session."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                }
            )
        return self.session
        
    async def _get_random_instance(self):
        """Get a random Invidious instance."""
        await self._initialize_instances()
        return random.choice(self._instances)
        
    async def _periodic_health_check(self):
        """Periodically check health of all instances."""
        while True:
            try:
                logger.info("Running periodic health check of Invidious instances")
                now = time.time()
                
                # Check instances that haven't been used in a while
                for instance in self._instances:
                    last_success = self.instance_stats[instance]['last_success']
                    if now - last_success > self.health_check_interval:
                        await self._check_instance_health(instance)
                        
                # Update last health check time
                self.last_health_check = now
                
                # Wait before next check
                await asyncio.sleep(self.health_check_interval)
            except Exception as e:
                logger.error(f"Error in periodic health check: {e}")
                await asyncio.sleep(60)  # Wait a minute and try again
                
    async def _check_instance_health(self, instance: str) -> bool:
        """Check health of a specific instance."""
        try:
            session = await self._get_session()
            async with session.get(f"{instance}/api/v1/stats", timeout=5) as response:
                if response.status == 200:
                    self.instance_health[instance] = True
                    self.instance_stats[instance]['success'] += 1
                    self.instance_stats[instance]['last_success'] = time.time()
                    logger.debug(f"Instance {instance} is healthy")
                    return True
                else:
                    self.instance_health[instance] = False
                    self.instance_stats[instance]['failure'] += 1
                    logger.warning(f"Instance {instance} returned status {response.status}")
                    return False
        except Exception as e:
            self.instance_health[instance] = False
            self.instance_stats[instance]['failure'] += 1
            logger.warning(f"Instance {instance} health check failed: {e}")
            return False
        
    async def _get_best_instance(self) -> Tuple[Optional[str], bool]:
        """Get the best Invidious instance based on health and performance."""
        # First refresh health status if needed
        current_time = time.time()
        if current_time - self.last_health_check > self.health_check_interval:
            await self._periodic_health_check()
            
        # Filter healthy instances
        healthy_instances = [i for i, healthy in self.instance_health.items() if healthy]
        
        if not healthy_instances:
            # If all instances are unhealthy, try checking a random subset
            logger.warning("All instances marked unhealthy, checking a random subset")
            sample_size = min(3, len(self._instances))
            for instance in random.sample(self._instances, sample_size):
                is_healthy = await self._check_instance_health(instance)
                if is_healthy:
                    healthy_instances.append(instance)
                    
            # If still no healthy instances, reset all to healthy and try again
            if not healthy_instances:
                logger.warning("Resetting all instances to healthy as last resort")
                self.instance_health = {instance: True for instance in self._instances}
                healthy_instances = self._instances
                return random.choice(healthy_instances), False
                
        # Sort by success rate and recency of last success
        def instance_score(instance):
            stats = self.instance_stats[instance]
            total = stats['success'] + stats['failure']
            success_rate = stats['success'] / max(total, 1)
            recency = max(0, min(1, (current_time - stats['last_success']) / 3600))  # Weight recent successes higher
            return success_rate * (1 - recency * 0.5)  # Scale recency impact
            
        sorted_instances = sorted(healthy_instances, key=instance_score, reverse=True)
        
        # Get the best instance that respects rate limiting
        for instance in sorted_instances:
            # Check if we need to wait before using this instance
            last_time = self.last_request_time.get(instance, 0)
            time_since_last = current_time - last_time
            
            if time_since_last < self.min_request_interval:
                # If top instance requires waiting but others don't, consider alternatives
                continue
                
            # Found a good instance
            return instance, True
            
        # If all good instances need waiting, use the best one with a delay
        if sorted_instances:
            best_instance = sorted_instances[0]
            last_time = self.last_request_time.get(best_instance, 0)
            time_since_last = current_time - last_time
            
            # Need to delay
            if time_since_last < self.min_request_interval:
                return best_instance, False
            return best_instance, True
            
        return None, False
        
    async def _make_api_request(self, endpoint: str, method: str = "GET", **kwargs) -> Optional[Dict]:
        """Make an API request to a healthy Invidious instance."""
        retry_count = 0
        last_error = None
        used_instances = set()
        
        while retry_count < self.max_retries:
            # Get the best available instance
            instance, ready = await self._get_best_instance()
            
            if not instance:
                logger.error("No healthy Invidious instances available")
                return None
                
            # Skip instances we've already tried in this request
            if instance in used_instances and len(used_instances) < len(self._instances):
                retry_count += 0.5  # Partial retry count for duplicate instances
                continue
                
            used_instances.add(instance)
                
            # If the instance needs a delay, wait
            if not ready:
                last_time = self.last_request_time.get(instance, 0)
                time_since_last = asyncio.get_event_loop().time() - last_time
                if time_since_last < self.min_request_interval:
                    wait_time = self.min_request_interval - time_since_last
                    logger.debug(f"Waiting {wait_time:.2f}s before using instance {instance}")
                    await asyncio.sleep(wait_time)
                    
            try:
                session = await self._get_session()
                url = f"{instance}/api/v1/{endpoint}"
                
                # Add instance domain as referer to reduce chance of being blocked
                instance_domain = urlparse(instance).netloc
                headers = kwargs.pop('headers', {})
                headers['Referer'] = f"https://{instance_domain}/"
                
                async with getattr(session, method.lower())(url, headers=headers, **kwargs) as response:
                    if response.status == 200:
                        # Update instance stats
                        self.instance_stats[instance]['success'] += 1
                        self.instance_stats[instance]['last_success'] = time.time()
                        self.last_request_time[instance] = time.time()
                        
                        try:
                            return await response.json()
                        except json.JSONDecodeError:
                            # If not valid JSON, try to get text
                            text = await response.text()
                            logger.error(f"Invalid JSON response from {instance}: {text[:100]}...")
                            self.instance_stats[instance]['failure'] += 1
                            retry_count += 1
                            continue
                            
                    elif response.status == 429:  # Rate limit
                        retry_delay = float(response.headers.get('Retry-After', 5))
                        logger.warning(f"Rate limited by {instance}, waiting {retry_delay}s")
                        await asyncio.sleep(retry_delay)
                        retry_count += 0.5  # Only count rate limits as partial retries
                        
                    elif response.status >= 500:  # Server error
                        logger.warning(f"Server error {response.status} from {instance}")
                        self.instance_health[instance] = False
                        self.instance_stats[instance]['failure'] += 1
                        retry_count += 1
                        
                    else:
                        logger.error(f"API request to {instance} failed with status {response.status}")
                        self.instance_stats[instance]['failure'] += 1
                        retry_count += 1
                        
                        # Try to get error response
                        try:
                            error_text = await response.text()
                            logger.debug(f"Error response: {error_text[:200]}...")
                        except:
                            pass
                            
            except asyncio.TimeoutError:
                logger.warning(f"Request to {instance} timed out")
                self.instance_stats[instance]['failure'] += 1
                last_error = "Request timed out"
                retry_count += 1
                
            except Exception as e:
                logger.error(f"API request to {instance} failed: {e}")
                self.instance_health[instance] = False
                self.instance_stats[instance]['failure'] += 1
                last_error = str(e)
                retry_count += 1
                
            # Small delay between retries
            await asyncio.sleep(0.5)
            
        if last_error:
            logger.error(f"All retries failed for API request: {last_error}")
        else:
            logger.error("All retries failed for API request")
            
        return None
        
    async def validate_url(self, url: str) -> bool:
        """Validate if URL is a YouTube URL."""
        try:
            # Convert URL to string if needed
            url_str = str(url)
            video_id = self._extract_video_id(url_str)
            if not video_id:
                return False
                
            # Try to get video info to validate
            data = await self._make_api_request(f"videos/{video_id}")
            return data is not None
        except Exception as e:
            logger.error(f"Error validating URL with Invidious: {e}")
            return False
            
    def _extract_video_id(self, url: str) -> Optional[str]:
        """Extract video ID from YouTube URL."""
        patterns = [
            r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
            r'(?:embed\/)([0-9A-Za-z_-]{11})',
            r'(?:youtu\.be\/)([0-9A-Za-z_-]{11})'
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
        
    async def get_info(self, url: str) -> Dict[str, any]:
        """
        Get information about a video from Invidious.
        
        Args:
            url: URL to get info for
            
        Returns:
            Dict with video information
        """
        try:
            video_id = self._extract_video_id(url)
            if not video_id:
                return {}
                
            data = await self._make_api_request(f"videos/{video_id}")
            if data:
                return {
                    'title': data.get('title', 'Unknown'),
                    'author': data.get('author', 'Unknown'),
                    'length': data.get('lengthSeconds', 0),
                    'views': data.get('viewCount', 0),
                    'thumbnail_url': data.get('videoThumbnails', [{}])[0].get('url', ''),
                    'age_restricted': data.get('age_restricted', False)
                }
            return {}
        except Exception as e:
            logger.error(f"Error getting video info from Invidious: {e}")
            return {}
            
    async def download(self, task: DownloadTask, options: Optional[dict] = None) -> AsyncGenerator[Dict[str, any], None]:
        """
        Download a video from YouTube via Invidious.
        
        Args:
            task: The download task containing URL and output information
            options: Additional options for the download
            
        Yields:
            Progress updates
        """
        # Extract values from task
        url = task.url
        output_dir = Path(task.output_dir)
        output_filename = task.output_filename
        
        # Create full output path
        output_path = output_dir / output_filename
        
        # Set default quality if not specified in options
        options = options or {}
        quality = options.get("quality", "medium")
        
        try:
            video_id = self._extract_video_id(url)
            if not video_id:
                yield {'status': 'error', 'error': 'Invalid YouTube URL', 'progress': 0}
                return
                
            # Get video info
            data = await self._make_api_request(f"videos/{video_id}")
            if not data:
                yield {'status': 'error', 'error': 'Failed to get video info', 'progress': 0}
                return
                
            # Get audio formats
            audio_formats = [f for f in data.get('adaptiveFormats', []) if f.get('type', '').startswith('audio/')]
            if not audio_formats:
                yield {'status': 'error', 'error': 'No audio formats available', 'progress': 0}
                return
                
            # Sort by bitrate and get best quality
            audio_formats.sort(key=lambda x: x.get('bitrate', 0), reverse=True)
            best_audio = audio_formats[0]
            logger.info(f"Selected audio format: {best_audio.get('type')} at {best_audio.get('bitrate', 0)//1000}kbps")
            
            # Create temp directory
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir) / f"{video_id}.{best_audio.get('container', 'webm')}"
                self.temp_files.append(temp_path)
                
                # Start download
                yield {'status': 'downloading', 'progress': 0}
                
                try:
                    # Download audio file
                    session = await self._get_session()
                    total_size = 0
                    downloaded = 0
                    
                    # Maximum retries for download
                    max_dl_retries = 3
                    dl_retry = 0
                    
                    while dl_retry < max_dl_retries:
                        try:
                            # Report retry attempt if not first try
                            if dl_retry > 0:
                                logger.info(f"Retry {dl_retry}/{max_dl_retries} for downloading audio")
                                yield {'status': 'downloading', 'progress': 0, 'message': f"Retry {dl_retry}/{max_dl_retries}"}
                                
                            audio_url = best_audio.get('url')
                            if not audio_url:
                                logger.error("No URL found in audio format data")
                                yield {'status': 'error', 'error': 'No download URL available', 'progress': 0}
                                return
                                
                            # Replace hostname for proxied content if needed
                            instance, _ = await self._get_best_instance()
                            if instance:
                                instance_domain = urlparse(instance).netloc
                                # If URL is relative, make it absolute using instance domain
                                if audio_url.startswith('/'):
                                    audio_url = f"{instance}{audio_url}"
                                    
                            headers = {
                                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
                                'Referer': f"https://{urlparse(instance).netloc if instance else 'youtube.com'}/watch?v={video_id}",
                                'Accept': '*/*',
                                'Accept-Language': 'en-US,en;q=0.9',
                                'Accept-Encoding': 'gzip, deflate, br',
                                'Range': 'bytes=0-'
                            }
                            
                            async with session.get(audio_url, headers=headers) as response:
                                if response.status not in (200, 206):
                                    logger.warning(f"Download failed with status {response.status}, trying again")
                                    dl_retry += 1
                                    await asyncio.sleep(1)
                                    continue
                                    
                                total_size = int(response.headers.get('content-length', 0))
                                
                                with open(temp_path, 'wb') as f:
                                    async for chunk in response.content.iter_chunked(8192):
                                        if not chunk:
                                            break
                                        f.write(chunk)
                                        downloaded += len(chunk)
                                        if total_size:
                                            progress = (downloaded / total_size) * 90
                                            yield {'status': 'downloading', 'progress': progress}
                                
                                # Check if the file was downloaded completely
                                if total_size > 0 and downloaded < total_size * 0.95:
                                    logger.warning(f"Incomplete download: {downloaded}/{total_size} bytes")
                                    dl_retry += 1
                                    await asyncio.sleep(1)
                                    continue
                                    
                                # Successfully downloaded
                                break
                                
                        except Exception as e:
                            logger.error(f"Error during download attempt {dl_retry + 1}: {e}")
                            dl_retry += 1
                            await asyncio.sleep(1)
                    
                    # Check if all retries were exhausted        
                    if dl_retry >= max_dl_retries:
                        logger.error(f"All download retries failed")
                        yield {'status': 'error', 'error': 'Download failed after multiple retries', 'progress': 0}
                        return
                        
                    # Check if file exists and has content
                    if not temp_path.exists() or temp_path.stat().st_size == 0:
                        logger.error("Downloaded file is empty or missing")
                        yield {'status': 'error', 'error': 'Downloaded file is empty', 'progress': 0}
                        return
                        
                    # Convert to desired format
                    yield {'status': 'processing', 'progress': 95}
                    
                    try:
                        # Ensure output directory exists
                        output_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        await ffmpeg_manager.convert_audio(
                            input_path=str(temp_path),
                            output_path=str(output_path),
                            bitrate=quality
                        )
                        
                        # Verify output file exists and has content
                        if not output_path.exists() or output_path.stat().st_size == 0:
                            logger.error("Converted file is empty or missing")
                            yield {'status': 'error', 'error': 'Conversion failed - output file is empty', 'progress': 0}
                            return
                            
                    except Exception as e:
                        logger.error(f"Error during conversion: {e}")
                        yield {'status': 'error', 'error': f'Conversion failed: {str(e)}', 'progress': 0}
                        return
                        
                    # Successfully completed
                    yield {'status': 'complete', 'progress': 100}
                    
                except Exception as e:
                    logger.error(f"Error downloading audio: {e}")
                    yield {'status': 'error', 'error': f'Download failed: {str(e)}', 'progress': 0}
                    
        except Exception as e:
            logger.error(f"Error downloading with Invidious: {e}")
            yield {'status': 'error', 'error': str(e), 'progress': 0}
            
    async def cleanup(self):
        """Clean up temporary files."""
        if self.session:
            try:
                if not self.session.closed:
                    await self.session.close()
            except Exception as e:
                logger.error(f"Error closing session in InvidiousStrategy: {e}")
                
        for temp_file in self.temp_files:
            try:
                if temp_file.exists():
                    temp_file.unlink()
            except Exception as e:
                logger.error(f"Error cleaning up temp file {temp_file}: {e}")
        self.temp_files.clear()
        
    @staticmethod
    def can_handle(url: str) -> bool:
        """
        Determine if this strategy can handle the given URL.
        
        Args:
            url: The URL to check
            
        Returns:
            True if this strategy can handle the URL, False otherwise
        """
        # Handle YouTube URLs via Invidious
        youtube_pattern = r'(?:https?://)?(?:www\.)?(?:youtube\.com|youtu\.be)/.+'
        return bool(re.match(youtube_pattern, url))
        
    async def run(self, task: DownloadTask) -> AsyncGenerator[dict, None]:
        """
        Run the download task with this strategy.
        
        Args:
            task: The download task to run
            
        Yields:
            Progress updates
        """
        try:
            url = task.url
            output_dir = Path(task.output_dir)
            output_filename = task.output_filename
            options = task.options or {}
            
            # Set quality from options or use default
            quality = options.get("quality", "medium")
            
            # Create full output path
            output_path = output_dir / output_filename
            
            # Use the download method to handle the actual download
            async for progress in self.download(task, options):
                yield progress
                
        except Exception as e:
            logger.error(f"Error running InvidiousStrategy: {e}")
            yield {
                "status": "error",
                "error": str(e),
                "progress": 0
            } 