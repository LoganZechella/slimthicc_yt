import asyncio
from pathlib import Path
from typing import Dict, Optional, AsyncGenerator, List
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

logger = logging.getLogger(__name__)

class YtdlpStrategy(DownloadStrategy):
    """YouTube download strategy using yt-dlp."""
    
    def __init__(self):
        self.temp_files = []
        self.current_progress = {'status': 'idle', 'progress': 0}
        self.user_agents = [
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15',
            'Mozilla/5.0 (iPad; CPU OS 17_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Mobile/15E148 Safari/604.1'
        ]
        self.headers = self._get_headers()
        
        # Check for cookie file
        self.cookie_file = '/app/youtube.cookies'
        if not os.path.exists(self.cookie_file):
            logger.warning(f"Cookie file not found at {self.cookie_file}")
        else:
            logger.info(f"Using cookie file: {self.cookie_file}")
            
        # Get YouTube PO token from environment
        self.youtube_po_token = os.getenv('YOUTUBE_PO_TOKEN', '')
        if not self.youtube_po_token:
            logger.warning("YouTube PO token not found in environment")
        else:
            logger.info("YouTube PO token found in environment")
            
        # Get YouTube session token from environment    
        self.youtube_session_token = os.getenv('YOUTUBE_SESSION_TOKEN', '')
        if not self.youtube_session_token:
            logger.warning("YouTube session token not found in environment")
        else:
            logger.info("YouTube session token found in environment")
            
        # Create a dedicated temp directory
        self.app_temp_dir = '/app/tmp'
        if not os.path.exists(self.app_temp_dir):
            try:
                os.makedirs(self.app_temp_dir, mode=0o777, exist_ok=True)
                logger.info(f"Created application temp directory: {self.app_temp_dir}")
            except Exception as e:
                logger.error(f"Failed to create app temp directory: {e}")
                self.app_temp_dir = None
        
    def _get_headers(self):
        """Get randomized headers to avoid detection."""
        user_agent = random.choice(self.user_agents)
        current_time = datetime.now().strftime("%Y%m%d%H%M%S")
        client_version = f"2.{current_time[:8]}.01.00"
        
        return {
            'User-Agent': user_agent,
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Origin': 'https://www.youtube.com',
            'Referer': 'https://www.youtube.com/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Ch-Ua': '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"macOS"',
            'X-Youtube-Client-Name': '1',
            'X-Youtube-Client-Version': client_version
        }
        
    def _get_yt_dlp_opts(self, temp_dir_path: Path, filename: str) -> dict:
        """Get yt-dlp options focused on audio extraction."""
        # Get fresh headers for each download
        headers = self._get_headers()
        
        # Use latest extractor args to improve success rate
        extractor_args = {
            'youtube': {
                'player_client': ['android', 'web'],  # Try multiple clients
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
        
        # Match desktop app configuration while keeping the simplicity
        return {
            'format': 'bestaudio/best',  # Get best audio format
            'extract_audio': True,
            'audio_format': 'mp3',
            'audio_quality': '0',  # Best quality
            'outtmpl': str(temp_dir_path / f"{filename}.%(ext)s"),
            'paths': {'home': str(temp_dir_path), 'temp': str(temp_dir_path)},
            'ffmpeg_location': '/usr/bin/ffmpeg',  # Use system ffmpeg
            'quiet': False,  # Enable output for debugging
            'no_warnings': False,  # Show warnings for debugging
            'noplaylist': True,
            'retries': 10,
            'fragment_retries': 10,
            'http_headers': headers,
            'cookiefile': self.cookie_file if os.path.exists(self.cookie_file) else None,
            'socket_timeout': 30,
            'extractor_args': extractor_args,
            'concurrent_fragment_downloads': 8,
            'file_access_retries': 10,
            'hls_prefer_native': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            }],
            'keepvideo': False,
            'sleep_interval': 1,
            'max_sleep_interval': 5,
            'sleep_interval_requests': 1,
            'overwrites': True,
            'verbose': True,  # Enable detailed logs to troubleshoot issues
            'progress': True,  # Show progress
            'geo_bypass': True,  # Try to bypass geo-restrictions
            'geo_bypass_country': 'US'  # Use US IP for geo-bypass
        }
        
    async def validate_url(self, url: str) -> bool:
        """Validate if URL is a YouTube URL."""
        try:
            # Convert URL to string if needed
            url_str = str(url)
            youtube_regex = (
                r'(https?://)?(www\.)?'
                '(youtube|youtu|youtube-nocookie)\.(com|be)/'
                '(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
            )
            match = re.match(youtube_regex, url_str)
            return bool(match)
        except Exception as e:
            logger.error(f"Error validating URL with strategy {self.__class__.__name__}: {e}")
            return False
        
    async def get_info(self, url: str) -> Dict[str, any]:
        """Get video information."""
        try:
            # Convert URL to string if needed
            url_str = str(url)
            
            with tempfile.TemporaryDirectory(dir=self.app_temp_dir) as temp_dir:
                ydl_opts = self._get_yt_dlp_opts(Path(temp_dir), 'temp')
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url_str, download=False)
                    return {
                        'title': info.get('title', 'Unknown'),
                        'author': info.get('uploader', 'Unknown'),
                        'length': info.get('duration', 0),
                        'views': info.get('view_count', 0),
                        'thumbnail_url': info.get('thumbnail', ''),
                        'age_restricted': info.get('age_limit', 0) > 0
                    }
        except Exception as e:
            logger.error(f"Error getting video info: {e}")
            return {}
            
    async def download(self, url: str, output_path: Path, quality: str) -> AsyncGenerator[Dict[str, any], None]:
        """Download audio using yt-dlp with progress tracking."""
        try:
            # Convert URL to string if needed
            url_str = str(url)
            
            # Generate a unique ID for this download
            download_id = f"download_{int(time.time())}"
            
            # Log current permissions and environment
            logger.info(f"Current user: {os.getuid()}:{os.getgid()}")
            logger.info(f"Current working directory: {os.getcwd()}")
            logger.info(f"TMPDIR environment variable: {os.environ.get('TMPDIR', 'Not set')}")
            logger.info(f"Output path permissions: Parent={output_path.parent} exists={output_path.parent.exists()}")
            
            if output_path.parent.exists():
                try:
                    parent_stat = os.stat(output_path.parent)
                    logger.info(f"Output parent dir permissions: mode={oct(parent_stat.st_mode)}, uid={parent_stat.st_uid}, gid={parent_stat.st_gid}")
                except Exception as e:
                    logger.error(f"Could not check output parent permissions: {e}")
            
            # Create a dedicated temporary directory for this download
            temp_dir_path = Path(self.app_temp_dir) / download_id if self.app_temp_dir else None
            
            if temp_dir_path:
                # Create the temp directory with permissive permissions
                try:
                    os.makedirs(temp_dir_path, mode=0o777, exist_ok=True)
                    logger.info(f"Created dedicated temp directory: {temp_dir_path}")
                    # Set very permissive permissions
                    os.chmod(temp_dir_path, 0o777)
                    # Track this directory for cleanup
                    self.temp_files.append(temp_dir_path)
                except Exception as e:
                    logger.error(f"Failed to create dedicated temp directory: {e}")
                    temp_dir_path = None
            
            # Use the system temp directory as fallback
            if not temp_dir_path:
                logger.info("Using system temporary directory as fallback")
                temp_dir = tempfile.mkdtemp(prefix="ytdlp_")
                temp_dir_path = Path(temp_dir)
                self.temp_files.append(temp_dir_path)
                # Make it very permissive
                os.chmod(temp_dir_path, 0o777)
            
            # Log the download attempt
            logger.info(f"Starting download for URL: {url_str} to {output_path}")
            logger.info(f"Using temporary directory: {temp_dir_path}")
            
            # Log permissions of temp directory
            try:
                temp_stat = os.stat(temp_dir_path)
                logger.info(f"Temp directory permissions: mode={oct(temp_stat.st_mode)}, uid={temp_stat.st_uid}, gid={temp_stat.st_gid}")
            except Exception as e:
                logger.error(f"Could not check temp dir permissions: {e}")
            
            # Start download
            yield {'status': 'downloading', 'progress': 0}
            
            # Configure yt-dlp options
            ydl_opts = self._get_yt_dlp_opts(temp_dir_path, 'audio')
            
            def progress_hook(d):
                if d['status'] == 'downloading':
                    try:
                        total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                        if total > 0:
                            downloaded = d.get('downloaded_bytes', 0)
                            progress = (downloaded / total) * 100
                            # Use class attribute to store progress info for reporting
                            self.current_progress = {'status': 'downloading', 'progress': progress}
                            logger.debug(f"Download progress: {progress:.2f}%")
                    except Exception as e:
                        logger.error(f"Error in progress hook: {e}")
                elif d['status'] == 'finished':
                    logger.info("Download finished, processing file")
                    self.current_progress = {'status': 'processing', 'progress': 95}
            
            # Add progress hook
            ydl_opts['progress_hooks'] = [progress_hook]
            
            try:
                # Download in a separate thread to not block
                loop = asyncio.get_event_loop()
                
                # Create a more detailed log for debugging
                logger.info(f"Starting yt-dlp download with options: {json.dumps(ydl_opts, default=str)[:200]}...")
                
                # Run the download
                await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).download([url_str]))
                
                # Log available files after download
                all_files = list(temp_dir_path.glob('*.*'))
                logger.info(f"Files in temp directory after download: {[f.name for f in all_files]}")
                
                # Find the downloaded file (check for mp3 first, then any audio file)
                downloaded_files = list(temp_dir_path.glob('*.mp3'))
                if not downloaded_files:
                    logger.warning("No MP3 files found, looking for any files")
                    downloaded_files = list(temp_dir_path.glob('*.*'))
                    if not downloaded_files:
                        logger.error("No files found in temp directory after download")
                        yield {'status': 'error', 'error': 'Downloaded file not found', 'progress': 0}
                        return
                
                downloaded_file = downloaded_files[0]
                logger.info(f"Found downloaded file: {downloaded_file}, size: {downloaded_file.stat().st_size} bytes")
                
                # Check file type
                try:
                    file_type = subprocess.check_output(['file', '-b', str(downloaded_file)], text=True).strip()
                    logger.info(f"File type: {file_type}")
                except Exception as e:
                    logger.error(f"Error checking file type: {e}")
                
                # Ensure the output directory exists
                output_path.parent.mkdir(parents=True, exist_ok=True)
                logger.info(f"Ensuring output directory exists: {output_path.parent}")
                
                # Try chmod on parent directory to ensure we can write
                try:
                    os.chmod(output_path.parent, 0o777)
                    logger.info(f"Updated output directory permissions to 777")
                except Exception as e:
                    logger.error(f"Could not update output directory permissions: {e}")
                
                # Try different file movement approaches to ensure success
                try:
                    logger.info(f"Attempting to copy file to: {output_path}")
                    
                    # Copy2 preserves metadata
                    shutil.copy2(str(downloaded_file), str(output_path))
                    logger.info(f"File copied successfully to: {output_path}")
                    
                    # Verify the file was copied correctly
                    if output_path.exists() and output_path.stat().st_size > 0:
                        logger.info(f"Verified file at destination: {output_path}, size: {output_path.stat().st_size} bytes")
                        
                        # Try to apply permissive permissions to the output file
                        try:
                            os.chmod(output_path, 0o666)  # rw-rw-rw-
                            logger.info(f"Updated output file permissions to 666")
                        except Exception as e:
                            logger.error(f"Could not update output file permissions: {e}")
                    else:
                        logger.error(f"Destination file missing or empty: {output_path}")
                        raise FileNotFoundError(f"Destination file missing or empty: {output_path}")
                    
                    # Clean up the source file
                    if downloaded_file.exists():
                        os.remove(str(downloaded_file))
                        logger.info(f"Removed source file: {downloaded_file}")
                    
                    # Final verification
                    if not output_path.exists():
                        logger.error(f"File disappeared after cleanup: {output_path}")
                        raise FileNotFoundError(f"File disappeared after cleanup: {output_path}")
                    
                    # Success!
                    yield {'status': 'complete', 'progress': 100}
                    logger.info(f"Download complete: {output_path}")
                    
                except Exception as e:
                    logger.error(f"Error moving file to output path: {e}")
                    
                    # Fallback approach 1: Try copy with shutil
                    try:
                        logger.info(f"Attempting fallback with shutil.copyfile: {downloaded_file} to {output_path}")
                        shutil.copyfile(str(downloaded_file), str(output_path))
                        
                        if output_path.exists() and output_path.stat().st_size > 0:
                            logger.info(f"Fallback copyfile successful: {output_path}")
                            yield {'status': 'complete', 'progress': 100}
                            return
                        else:
                            logger.error(f"Fallback copyfile failed: {output_path}")
                    except Exception as e1:
                        logger.error(f"Fallback copyfile error: {e1}")
                        
                        # Fallback approach 2: try direct copy with os.system
                        try:
                            logger.info(f"Attempting fallback copy with os.system: {downloaded_file} to {output_path}")
                            result = os.system(f"cp '{downloaded_file}' '{output_path}'")
                            logger.info(f"System copy command exit code: {result}")
                            
                            if output_path.exists() and output_path.stat().st_size > 0:
                                logger.info(f"Fallback os.system copy successful: {output_path}")
                                yield {'status': 'complete', 'progress': 100}
                                return
                            else:
                                logger.error(f"Fallback os.system copy failed: {output_path}")
                        except Exception as e2:
                            logger.error(f"Fallback os.system copy error: {e2}")
                            
                            # Final fallback: Use subprocess with sudo
                            try:
                                logger.info(f"Final fallback with subprocess: {downloaded_file} to {output_path}")
                                subprocess.run(['cp', str(downloaded_file), str(output_path)], check=True)
                                
                                if output_path.exists() and output_path.stat().st_size > 0:
                                    logger.info(f"Subprocess copy successful: {output_path}")
                                    yield {'status': 'complete', 'progress': 100}
                                    return
                                else:
                                    logger.error(f"Subprocess copy failed: {output_path}")
                                    yield {'status': 'error', 'error': f'Failed to move file (tried all methods)', 'progress': 0}
                                    return
                            except Exception as e3:
                                logger.error(f"Subprocess copy error: {e3}")
                                yield {'status': 'error', 'error': f'Failed to move file (tried all methods)', 'progress': 0}
                                return
                    
            except Exception as e:
                logger.error(f"Error during download: {e}")
                yield {'status': 'error', 'error': f'Download failed: {str(e)}', 'progress': 0}
                return
                
        except Exception as e:
            logger.error(f"Error downloading with yt-dlp: {e}")
            yield {'status': 'error', 'error': str(e), 'progress': 0}
            
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