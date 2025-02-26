import asyncio
from pathlib import Path
from typing import Dict, Optional, AsyncGenerator, List, Union, Any
import tempfile
import logging
import re
import os
import yt_dlp
from .base import DownloadStrategy
from src.services.ffmpeg_manager import ffmpeg_manager
from src.config.settings import settings
import shutil
import random
import json
import time
from datetime import datetime
import subprocess
import requests
from urllib.parse import urlparse
import socket

logger = logging.getLogger(__name__)

class YtdlpStrategy(DownloadStrategy):
    """YouTube download strategy using yt-dlp."""
    
    def __init__(self):
        """Initialize the YtdlpStrategy."""
        super().__init__()
        self.temp_files = []
        self.current_progress = {'status': 'idle', 'progress': 0}
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/112.0'
        ]
        self.headers = self._get_headers()
        
        # Set up environment variables
        self.cookie_file_path = os.environ.get('YOUTUBE_COOKIE_FILE', 'youtube.cookies')
        self.cookie_file = self.cookie_file_path  # For compatibility with get_ydl_opts
        if not os.path.isabs(self.cookie_file_path):
            # Try multiple locations for the cookie file
            possible_paths = [
                os.path.join(os.getcwd(), self.cookie_file_path),
                f"/app/{self.cookie_file_path}",
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), self.cookie_file_path)
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    self.cookie_file_path = path
                    self.cookie_file = path
                    logger.info(f"Found cookie file at {path}")
                    break
                    
        if not os.path.exists(self.cookie_file_path):
            logger.warning(f"Cookie file not found at {self.cookie_file_path}")
        else:
            logger.info(f"Will use cookie file at {self.cookie_file_path}")
        
        # Configure temp directory
        self.app_temp_dir = getattr(settings, 'APP_TEMP_DIR', 'tmp')
        if not os.path.exists(self.app_temp_dir):
            try:
                os.makedirs(self.app_temp_dir, exist_ok=True)
                logger.info(f"Created app temp directory at {self.app_temp_dir}")
            except Exception as e:
                logger.error(f"Failed to create temp directory at {self.app_temp_dir}: {e}")
                self.app_temp_dir = 'tmp'
                os.makedirs(self.app_temp_dir, exist_ok=True)
                
        # Configure direct connection option
        self.use_direct_connection = True  # Allow direct connections without proxy
        
        # Initialize proxies after setting use_direct_connection
        self.proxies = self._initialize_proxy_list()
        self.current_proxy = None
        self.proxy_failures = {}
        self.max_proxy_failures = 3
        
        # Get YouTube PO token from environment
        self.youtube_po_token = os.getenv('YOUTUBE_PO_TOKEN', '')
        self.po_token = self.youtube_po_token  # For compatibility with get_ydl_opts
        if not self.youtube_po_token:
            logger.warning("YouTube PO token not found in environment")
        else:
            logger.info("YouTube PO token found in environment")
            
        # Get YouTube session token from environment    
        self.youtube_session_token = os.getenv('YOUTUBE_SESSION_TOKEN', '')
        self.session_token = self.youtube_session_token  # For compatibility with get_ydl_opts
        if not self.youtube_session_token:
            logger.warning("YouTube session token not found in environment")
        else:
            logger.info("YouTube session token found in environment")
            
        # Set up additional YouTube options
        self.yt_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        # Add tokens to headers if available
        if self.youtube_po_token:
            self.yt_headers['X-YouTube-Client-Name'] = '1'
            self.yt_headers['X-YouTube-Client-Version'] = '2.20230602.01.00'
            # Add SAPISIDHASH if available (improves age-restricted content access)
            # This would ideally be generated from SAPISID cookie
            
        logger.info("Initialized YtdlpStrategy with enhanced YouTube protection handling")
        
    def _initialize_proxy_list(self):
        """Initialize proxy list from settings"""
        proxy_list = []
        
        # Add default None (direct connection) if enabled
        if self.use_direct_connection:
            proxy_list.append(None)
        
        # Add proxies from settings
        if hasattr(settings, 'DEFAULT_PROXIES') and settings.DEFAULT_PROXIES:
            if isinstance(settings.DEFAULT_PROXIES, dict):
                # Handle dict format
                for protocol, proxy in settings.DEFAULT_PROXIES.items():
                    if proxy:
                        proxy_list.append(proxy)
                        logger.info(f"Added proxy for {protocol}: {proxy}")
            elif isinstance(settings.DEFAULT_PROXIES, list):
                # Handle list format
                for proxy in settings.DEFAULT_PROXIES:
                    if proxy:
                        proxy_list.append(proxy)
                        logger.info(f"Added proxy: {proxy}")
        
        logger.info(f"Loaded {len(proxy_list)} proxies from settings")
        return proxy_list
        
    def _get_next_proxy(self) -> Optional[str]:
        """Get the next healthy proxy to use."""
        if not self.proxies or len(self.proxies) <= 1:
            return None
            
        # Filter out proxies that have failed too many times
        healthy_proxies = [p for p in self.proxies if p is None or 
                           self.proxy_failures.get(p, 0) < self.max_proxy_failures]
                           
        if not healthy_proxies:
            # If all proxies have failed, reset failures and try again
            logger.warning("All proxies have failed, resetting failure counts")
            self.proxy_failures = {}
            healthy_proxies = self.proxies
            
        # Don't choose the current proxy if possible
        if len(healthy_proxies) > 1 and self.current_proxy in healthy_proxies:
            healthy_proxies.remove(self.current_proxy)
            
        # Select a random proxy
        chosen_proxy = random.choice(healthy_proxies)
        self.current_proxy = chosen_proxy
        
        if chosen_proxy:
            logger.info(f"Using proxy: {chosen_proxy}")
        else:
            logger.info("Using direct connection (no proxy)")
            
        return chosen_proxy
        
    def _mark_proxy_failure(self, proxy: Optional[str]):
        """Mark a proxy as failed."""
        if proxy is None:
            return
            
        if proxy not in self.proxy_failures:
            self.proxy_failures[proxy] = 0
            
        self.proxy_failures[proxy] += 1
        logger.warning(f"Proxy {proxy} marked with failure count: {self.proxy_failures[proxy]}")
        
    def _get_headers(self):
        """Get request headers to mimic browser."""
        return {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Origin': 'https://www.youtube.com',
            'Referer': 'https://www.youtube.com/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'X-Youtube-Client-Name': '1',
            'X-Youtube-Client-Version': '2.20240221.08.00'
        }
        
    def _get_extractor_args(self) -> dict:
        """Get YouTube extractor arguments to improve success rate."""
        # Use latest extractor args to improve success rate
        extractor_args = {
            'youtube': {
                'player_client': ['android', 'web', 'tv_embedded'],  # Try multiple clients
                'player_skip': [],
                'innertube_key': settings.YOUTUBE_INNERTUBE_KEY if hasattr(settings, 'YOUTUBE_INNERTUBE_KEY') else 'AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8',
                'innertube_context': {
                    'client': {
                        'clientName': 'ANDROID',
                        'clientVersion': '18.11.34',
                        'androidSdkVersion': 30,
                        'osName': 'Android',
                        'osVersion': '11.0',
                        'platform': 'MOBILE'
                    }
                }
            }
        }
        
        # Add device ID if available
        device_id = os.getenv('YOUTUBE_DEVICE_ID', '')
        if device_id:
            extractor_args['youtube']['innertube_context']['client']['deviceId'] = device_id
            logger.info(f"Using device ID for yt-dlp: {device_id[:5]}...")
            
        # Add YouTube PO token if available
        if self.youtube_po_token:
            extractor_args['youtube']['innertube_context']['context'] = {
                'user': {'onBehalfOfUser': self.youtube_po_token}
            }
            logger.info("Added YouTube PO token to request context")
            
        # Add session token for age verification if available
        if self.youtube_po_token and self.youtube_session_token:
            extractor_args['youtube']['innertube_context']['client']['visitorData'] = self.youtube_session_token
            logger.info("Added visitor data for age verification")
            
        return extractor_args
        
    def _get_yt_dlp_opts(self, temp_dir_path: str, filename: str) -> Dict[str, Any]:
        """Get yt-dlp options."""
        opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio/best',  # Prefer m4a audio
            'extract_audio': True,
            'audio_format': 'mp3',
            'audio_quality': '0',  # Best quality
            'outtmpl': f'{temp_dir_path}/temp.%(ext)s',
            'paths': {
                'home': temp_dir_path,
                'temp': temp_dir_path,
            },
            'quiet': False,
            'verbose': True,
            'no_warnings': False,
            'noplaylist': True,
            'retries': 10,
            'fragment_retries': 10,
            'http_headers': self.headers,
            'socket_timeout': 30,
            'extractor_args': self._get_extractor_args(),
            'concurrent_fragment_downloads': 8,
            'file_access_retries': 10,
            'hls_prefer_native': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            }],
            'keepvideo': False,
            'sleep_interval': 3,
            'max_sleep_interval': 10,
            'sleep_interval_requests': 1,
            'overwrites': True,
        }
        
        # Only add cookiefile if it exists to avoid format errors
        try:
            if os.path.exists(self.cookie_file_path):
                # Verify the cookie file format before adding it
                with open(self.cookie_file_path, 'r') as f:
                    cookie_data = f.read()
                    # Check if it looks like a Netscape formatted cookie file (contains tab characters and has multiple lines)
                    if '\t' in cookie_data and cookie_data.count('\n') > 1:
                        logger.info(f"Using cookie file: {self.cookie_file_path}")
                        opts['cookiefile'] = self.cookie_file_path
                    else:
                        logger.warning(f"Cookie file {self.cookie_file_path} is not in Netscape format, skipping")
        except Exception as e:
            logger.warning(f"Error processing cookie file, not using cookies: {e}")
            
        # Add proxy if needed
        if self.current_proxy:
            opts['proxy'] = self.current_proxy
            logger.info(f"Using proxy: {self.current_proxy}")
            
        return opts
        
    async def validate_url(self, url: str) -> bool:
        """Validate if URL is a YouTube URL."""
        try:
            # Convert URL to string if needed
            url_str = str(url)
            youtube_regex = r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
            match = re.match(youtube_regex, url_str)
            return bool(match)
        except Exception as e:
            logger.error(f"Error validating URL with strategy {self.__class__.__name__}: {e}")
            return False
        
    async def get_info(self, url: str) -> Dict[str, any]:
        """Get video information."""
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                # Convert URL to string if needed
                url_str = str(url)
                
                with tempfile.TemporaryDirectory(dir=self.app_temp_dir) as temp_dir:
                    ydl_opts = self._get_yt_dlp_opts(temp_dir, 'temp')
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        logger.info(f"Attempt {attempt + 1}/{max_retries} to get info for: {url_str}")
                        info = ydl.extract_info(url_str, download=False)
                        
                        # Verify we actually got useful info
                        if not info or (isinstance(info, dict) and not info.get('title')):
                            logger.warning(f"Empty or incomplete info returned on attempt {attempt + 1}")
                            if attempt < max_retries - 1:
                                # Try a different proxy
                                if self.current_proxy:
                                    self._mark_proxy_failure(self.current_proxy)
                                # Wait before retry
                                await asyncio.sleep(random.uniform(1, 3))
                                continue
                            else:
                                logger.error("Failed to get info after all retries")
                                return {}
                                
                        return {
                            'title': info.get('title', 'Unknown'),
                            'author': info.get('uploader', 'Unknown'),
                            'length': info.get('duration', 0),
                            'views': info.get('view_count', 0),
                            'thumbnail_url': info.get('thumbnail', ''),
                            'age_restricted': info.get('age_limit', 0) > 0
                        }
            except yt_dlp.utils.ExtractorError as e:
                error_str = str(e)
                if "signature extraction failed" in error_str or "Unable to extract" in error_str:
                    logger.error(f"Critical yt-dlp extractor error: {error_str}")
                    # Mark proxy failure and immediately give up on this attempt
                    self._mark_proxy_failure(self.current_proxy)
                    return {}
                
                logger.error(f"yt-dlp extractor error on attempt {attempt + 1}: {error_str}")
                if attempt < max_retries - 1:
                    # Try with a different proxy
                    self._mark_proxy_failure(self.current_proxy)
                    await asyncio.sleep(random.uniform(1, 3))
                    continue
                else:
                    logger.error("Failed to get info after all retries")
                    return {}
            except Exception as e:
                logger.error(f"Error getting video info on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    # Try with a different proxy
                    self._mark_proxy_failure(self.current_proxy)
                    await asyncio.sleep(random.uniform(1, 3))
                    continue
                else:
                    logger.error("Failed to get info after all retries")
                    return {}
        
        return {}
            
    async def download(self, url: str, output_path: Union[str, Path], quality: Optional[str] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Download a video from YouTube using yt-dlp.
        
        Args:
            url: URL to download
            output_path: Path to save the downloaded file
            quality: Audio quality (high, medium, low)
            
        Yields:
            Progress updates
        """
        try:
            # Convert output_path to Path object if it's a string
            if isinstance(output_path, str):
                output_path = Path(output_path)
                
            # Ensure parent directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # First yield a starting status
            self.current_progress = {'status': 'downloading', 'progress': 0, 'url': url}
            yield self.current_progress
            
            # Set up progress tracking
            progress_tracker = {'status': 'downloading', 'progress': 0, 'url': url}
            
            def progress_hook(d):
                nonlocal progress_tracker
                
                if d['status'] == 'downloading':
                    if 'total_bytes' in d and d['total_bytes'] > 0:
                        # Calculate progress percentage
                        progress = (d['downloaded_bytes'] / d['total_bytes']) * 100
                        progress_tracker['progress'] = progress
                        progress_tracker['status'] = 'downloading'
                        progress_tracker['eta'] = d.get('eta')
                        progress_tracker['speed'] = d.get('speed')
                        progress_tracker['downloaded_bytes'] = d.get('downloaded_bytes')
                        progress_tracker['total_bytes'] = d.get('total_bytes')
                    elif 'downloaded_bytes' in d:
                        # If total_bytes is unknown, just show downloaded bytes
                        progress_tracker['progress'] = min(d['downloaded_bytes'] / 1024 / 1024, 99)  # Cap at 99%
                        progress_tracker['status'] = 'downloading'
                        progress_tracker['downloaded_bytes'] = d.get('downloaded_bytes')
                        
                elif d['status'] == 'finished':
                    progress_tracker['status'] = 'processing'
                    progress_tracker['progress'] = 99  # Almost done, need to process
                    
                elif d['status'] == 'error':
                    progress_tracker['status'] = 'error'
                    progress_tracker['error'] = d.get('error', 'Unknown error')
                    
                self.current_progress = progress_tracker.copy()
            
            # Configure yt-dlp options
            ydl_opts = self.get_ydl_opts(
                output_path=output_path,
                quality=quality or "medium",
                progress_hook=progress_hook
            )
            
            # Download the video with retries
            max_retries = 3
            success = False
            error_message = None
            
            for attempt in range(max_retries):
                try:
                    # Yield progress update
                    yield {
                        'status': 'downloading',
                        'progress': progress_tracker.get('progress', 0),
                        'attempt': attempt + 1,
                        'max_attempts': max_retries
                    }
                    
                    # Start download
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=True)
                        
                    # Check if file was downloaded
                    if output_path.exists() and output_path.stat().st_size > 0:
                        success = True
                        break
                    else:
                        error_message = "Download completed but file not found or is empty"
                        logger.warning(f"File not found after download for {url}")
                        time.sleep(1)  # Small delay before retry
                        
                except Exception as e:
                    error_message = str(e)
                    logger.error(f"Download attempt {attempt+1}/{max_retries} failed: {e}")
                    
                    # Check for specific YouTube errors
                    youtube_errors = [
                        "unable to extract", 
                        "signature extraction", 
                        "URL could not be reached",
                        "429",
                        "too many requests",
                        "This video is unavailable"
                    ]
                    
                    if any(err in str(e).lower() for err in youtube_errors):
                        logger.warning("YouTube protection detected, switching approach")
                        # Try with different settings
                        ydl_opts['extractor_args']['youtube']['player_client'] = ['web', 'android']
                        
                    time.sleep(2 * (attempt + 1))  # Exponential backoff
                    
            if success:
                # Final yield - complete
                yield {
                    'status': 'complete',
                    'progress': 100,
                    'file': str(output_path)
                }
            else:
                # Final yield - error
                yield {
                    'status': 'error',
                    'progress': 0,
                    'error': error_message or "Failed to download video after multiple attempts"
                }
                
        except Exception as e:
            logger.error(f"Error in yt-dlp download process: {e}")
            yield {
                'status': 'error',
                'progress': 0,
                'error': str(e)
            }
            
    async def cleanup(self):
        """Clean up temporary files."""
        for temp_file in self.temp_files:
            try:
                if isinstance(temp_file, Path) and temp_file.exists():
                    if temp_file.is_dir():
                        shutil.rmtree(temp_file, ignore_errors=True)
                    else:
                        temp_file.unlink(missing_ok=True)
            except Exception as e:
                logger.error(f"Error cleaning up temp file {temp_file}: {e}")
        self.temp_files.clear()
        
    async def _report_progress(self, progress_info: Dict[str, any]):
        """Helper method to report progress."""
        # Method is now a no-op since we use self.current_progress instead
        pass 

    def get_ydl_opts(self, output_path, quality="medium", **kwargs):
        """Get options for yt-dlp."""
        quality_settings = self._get_quality_settings(quality)
        
        # Base options
        ydl_opts = {
            'format': quality_settings['format'],
            'outtmpl': str(output_path),
            'quiet': True,
            'no_warnings': True,
            'noprogress': True,
            'noplaylist': True,
            'progress_hooks': [kwargs.get('progress_hook', None)] if kwargs.get('progress_hook') else [],
            # Enhanced YouTube handling
            'nocheckcertificate': True,
            'ignoreerrors': True,
            'socket_timeout': 30,
            'retries': 10,
            'fragment_retries': 10,
            'skip_unavailable_fragments': True,
            'concurrent_fragment_downloads': 4,
            'extractor_args': {
                'youtube': {
                    'player_client': ['android'],  # Try android client which has fewer restrictions
                    'player_skip': ['webpage', 'configs'],  # Skip webpage to avoid some protections
                }
            },
            # Add proxy support
            'source_address': None,  # Let yt-dlp choose the best interface
        }
        
        # Add cookies if available
        if self.cookie_file and os.path.exists(self.cookie_file):
            logger.info(f"Using YouTube cookie file: {self.cookie_file}")
            ydl_opts['cookiefile'] = self.cookie_file
        
        # Add headers if available
        if self.yt_headers:
            ydl_opts['http_headers'] = self.yt_headers
            
        # Add session tokens if available
        if self.session_token or self.po_token:
            if 'extractor_args' not in ydl_opts:
                ydl_opts['extractor_args'] = {}
            if 'youtube' not in ydl_opts['extractor_args']:
                ydl_opts['extractor_args']['youtube'] = {}
                
            if self.session_token:
                ydl_opts['extractor_args']['youtube']['session_token'] = self.session_token
            if self.po_token:
                ydl_opts['extractor_args']['youtube']['po_token'] = self.po_token
        
        return ydl_opts 