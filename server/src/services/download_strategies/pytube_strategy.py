import asyncio
from pathlib import Path
from typing import Dict, Optional, AsyncGenerator, List
import re
import tempfile
import os
import logging
import json
from pytube import YouTube
from pytube.exceptions import VideoUnavailable, RegexMatchError, ExtractError
from .base import DownloadStrategy
from src.services.ffmpeg_manager import ffmpeg_manager
from src.config.settings import settings

logger = logging.getLogger(__name__)

class PytubeStrategy(DownloadStrategy):
    """YouTube download strategy using pytube."""
    
    def __init__(self):
        self.temp_files = []
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
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
            'X-Youtube-Client-Version': '2.20240221.08.00'
        }
        
        # Load cookies if available
        self.cookies = {}
        cookie_file = settings.YOUTUBE_COOKIE_FILE
        if cookie_file and os.path.exists(cookie_file):
            try:
                with open(cookie_file, 'r') as f:
                    for line in f:
                        if line.strip() and not line.startswith('#'):
                            try:
                                domain, _, _, _, expiry, name, value = line.strip().split('\t')
                                if domain in ['.youtube.com', 'youtube.com']:
                                    self.cookies[name] = value
                            except ValueError:
                                continue
                logger.info("Loaded YouTube cookies successfully")
            except Exception as e:
                logger.error(f"Error loading cookies: {e}")
                
    def _create_youtube_object(self, url: str, **kwargs) -> YouTube:
        """Create a YouTube object with proper initialization and retries."""
        max_retries = 3
        retry_count = 0
        last_error = None
        
        while retry_count < max_retries:
            try:
                # Create YouTube object
                yt = YouTube(
                    url,
                    use_oauth=False,
                    allow_oauth_cache=False,
                    **kwargs
                )
                
                # Apply headers and cookies
                yt.headers = self.headers
                if self.cookies:
                    yt.cookies = self.cookies
                
                # Force initial data fetch to validate object
                _ = yt.vid_info
                
                return yt
                
            except VideoUnavailable as e:
                logger.error(f"Video unavailable: {e}")
                raise
            except RegexMatchError as e:
                logger.error(f"Invalid YouTube URL: {e}")
                raise
            except ExtractError as e:
                logger.error(f"Failed to extract video info: {e}")
                retry_count += 1
                last_error = e
                asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Error creating YouTube object (attempt {retry_count + 1}): {e}")
                retry_count += 1
                last_error = e
                asyncio.sleep(1)
        
        if last_error:
            raise last_error
        raise Exception("Failed to create YouTube object after retries")
                
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
            
            # Create YouTube object with retries
            yt = self._create_youtube_object(url_str)
            
            return {
                'title': yt.title,
                'author': yt.author,
                'length': yt.length,
                'views': yt.views,
                'thumbnail_url': yt.thumbnail_url,
                'age_restricted': yt.age_restricted
            }
        except VideoUnavailable:
            logger.error("Video is unavailable")
            return {}
        except Exception as e:
            logger.error(f"Error getting video info: {e}")
            return {}
            
    async def download(self, url: str, output_path: Path, quality: str) -> AsyncGenerator[Dict[str, any], None]:
        """Download audio using pytube with progress tracking."""
        try:
            # Convert URL to string if needed
            url_str = str(url)
            
            # Setup progress tracking
            progress = {'bytes_downloaded': 0, 'file_size': 0}
            
            def progress_callback(stream, chunk, bytes_remaining):
                progress['bytes_downloaded'] = stream.filesize - bytes_remaining
                progress['file_size'] = stream.filesize
            
            # Create YouTube object with progress callback
            yt = self._create_youtube_object(
                url_str,
                on_progress_callback=progress_callback,
                on_complete_callback=None
            )
            
            # Get audio stream with retries
            max_retries = 3
            retry_count = 0
            audio_stream = None
            
            while retry_count < max_retries and not audio_stream:
                try:
                    # Try to get the best audio stream
                    audio_stream = yt.streams.filter(only_audio=True).order_by('abr').desc().first()
                    if not audio_stream:
                        retry_count += 1
                        await asyncio.sleep(1)  # Wait before retry
                    else:
                        break
                except Exception as e:
                    logger.error(f"Error getting audio stream (attempt {retry_count + 1}): {e}")
                    retry_count += 1
                    await asyncio.sleep(1)
            
            if not audio_stream:
                yield {'status': 'error', 'error': 'No audio stream found after retries', 'progress': 0}
                return
                
            # Create temp directory
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir) / f"{yt.video_id}.{audio_stream.subtype}"
                self.temp_files.append(temp_path)
                
                # Start download
                yield {'status': 'downloading', 'progress': 0}
                
                try:
                    # Download in a separate thread to not block
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        None,
                        lambda: audio_stream.download(
                            output_path=temp_dir,
                            filename=f"{yt.video_id}.{audio_stream.subtype}"
                        )
                    )
                    
                    # Report final download progress
                    if progress['file_size'] > 0:
                        yield {'status': 'downloading', 'progress': 90}
                        
                except Exception as e:
                    logger.error(f"Error during download: {e}")
                    yield {'status': 'error', 'error': f'Download failed: {str(e)}', 'progress': 0}
                    return
                
                # Verify the downloaded file
                if not temp_path.exists() or temp_path.stat().st_size == 0:
                    yield {'status': 'error', 'error': 'Downloaded file is missing or empty', 'progress': 0}
                    return
                
                # Convert to desired format using FFmpeg
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
                
                # Verify the output file
                if not output_path.exists() or output_path.stat().st_size == 0:
                    yield {'status': 'error', 'error': 'Converted file is missing or empty', 'progress': 0}
                    return
                
                yield {'status': 'complete', 'progress': 100}
                
        except Exception as e:
            logger.error(f"Error downloading with pytube: {e}")
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