import asyncio
from pathlib import Path
from typing import Dict, Optional, AsyncGenerator, List
import aiohttp
import logging
import json
import tempfile
import random
from urllib.parse import quote
from .base import DownloadStrategy
from src.services.ffmpeg_manager import ffmpeg_manager
from src.config.settings import settings

logger = logging.getLogger(__name__)

class InvidiousStrategy(DownloadStrategy):
    """YouTube download strategy using Invidious API."""
    
    def __init__(self):
        self.temp_files = []
        self.instances = [
            "https://invidious.snopyta.org",
            "https://invidious.kavin.rocks",
            "https://invidious.namazso.eu",
            "https://inv.riverside.rocks",
            "https://yt.artemislena.eu",
            "https://invidious.flokinet.to",
            "https://invidious.projectsegfau.lt",
            "https://inv.vern.cc",
            "https://invidious.nerdvpn.de",
            "https://inv.bp.projectsegfau.lt",
            "https://invidious.lunar.icu"
        ]
        self.current_instance_index = 0
        self.session = None
        self.instance_health = {instance: True for instance in self.instances}
        self.last_request_time = {}
        self.min_request_interval = 2.0  # Minimum seconds between requests to same instance
        
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session
        
    async def _get_healthy_instance(self) -> Optional[str]:
        """Get a healthy Invidious instance."""
        # Shuffle instances to distribute load
        available_instances = [i for i, healthy in self.instance_health.items() if healthy]
        if not available_instances:
            # Reset health status if all instances are marked unhealthy
            self.instance_health = {instance: True for instance in self.instances}
            available_instances = self.instances
            
        # Try each instance
        for instance in available_instances:
            try:
                # Check if we need to wait before using this instance
                last_time = self.last_request_time.get(instance, 0)
                time_since_last = asyncio.get_event_loop().time() - last_time
                if time_since_last < self.min_request_interval:
                    await asyncio.sleep(self.min_request_interval - time_since_last)
                    
                # Test instance health
                session = await self._get_session()
                async with session.get(f"{instance}/api/v1/stats", timeout=5) as response:
                    if response.status == 200:
                        self.last_request_time[instance] = asyncio.get_event_loop().time()
                        return instance
                    else:
                        self.instance_health[instance] = False
            except Exception as e:
                logger.error(f"Instance {instance} health check failed: {e}")
                self.instance_health[instance] = False
                continue
                
        logger.error("No healthy Invidious instances available")
        return None
        
    async def _make_api_request(self, endpoint: str, method: str = "GET", **kwargs) -> Optional[Dict]:
        """Make an API request to a healthy Invidious instance."""
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            instance = await self._get_healthy_instance()
            if not instance:
                logger.error("No healthy Invidious instances available")
                return None
                
            try:
                session = await self._get_session()
                url = f"{instance}/api/v1/{endpoint}"
                
                async with getattr(session, method.lower())(url, **kwargs) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 429:  # Rate limit
                        retry_delay = float(response.headers.get('Retry-After', 5))
                        await asyncio.sleep(retry_delay)
                    elif response.status >= 500:  # Server error
                        self.instance_health[instance] = False
                    else:
                        logger.error(f"API request failed with status {response.status}")
                        return None
            except Exception as e:
                logger.error(f"API request to {instance} failed: {e}")
                self.instance_health[instance] = False
                
            retry_count += 1
            await asyncio.sleep(1)
            
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
        import re
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
        """Get video information from Invidious API."""
        try:
            video_id = self._extract_video_id(url)
            if not video_id:
                return {}
                
            data = await self._make_api_request(f"videos/{video_id}")
            if data:
                return {
                    'title': data.get('title'),
                    'author': data.get('author'),
                    'length': data.get('lengthSeconds'),
                    'views': data.get('viewCount'),
                    'thumbnail_url': data.get('videoThumbnails', [{}])[0].get('url'),
                    'age_restricted': data.get('age_restricted', False)
                }
            return {}
        except Exception as e:
            logger.error(f"Error getting video info from Invidious: {e}")
            return {}
            
    async def download(self, url: str, output_path: Path, quality: str) -> AsyncGenerator[Dict[str, any], None]:
        """Download audio using Invidious API."""
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
            
            # Create temp directory
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir) / f"{video_id}.{best_audio['container']}"
                self.temp_files.append(temp_path)
                
                # Start download
                yield {'status': 'downloading', 'progress': 0}
                
                try:
                    # Download audio file
                    session = await self._get_session()
                    total_size = 0
                    downloaded = 0
                    
                    async with session.get(best_audio['url']) as response:
                        if response.status != 200:
                            yield {'status': 'error', 'error': f'Download failed with status {response.status}', 'progress': 0}
                            return
                            
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
                                    
                except Exception as e:
                    logger.error(f"Error downloading audio: {e}")
                    yield {'status': 'error', 'error': f'Download failed: {str(e)}', 'progress': 0}
                    return
                    
                # Convert to desired format
                yield {'status': 'processing', 'progress': 95}
                
                try:
                    await ffmpeg_manager.convert_audio(
                        input_path=str(temp_path),
                        output_path=str(output_path),
                        bitrate=quality
                    )
                except Exception as e:
                    logger.error(f"Error during conversion: {e}")
                    yield {'status': 'error', 'error': f'Conversion failed: {str(e)}', 'progress': 0}
                    return
                    
                yield {'status': 'complete', 'progress': 100}
                
        except Exception as e:
            logger.error(f"Error downloading with Invidious: {e}")
            yield {'status': 'error', 'error': str(e), 'progress': 0}
            
    async def cleanup(self):
        """Clean up temporary files."""
        for temp_file in self.temp_files:
            try:
                if temp_file.exists():
                    temp_file.unlink()
            except Exception as e:
                logger.error(f"Error cleaning up temp file {temp_file}: {e}")
        self.temp_files.clear()
        
        if self.session and not self.session.closed:
            await self.session.close() 