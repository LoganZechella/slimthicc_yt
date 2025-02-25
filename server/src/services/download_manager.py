from typing import Dict, Optional, Callable
import asyncio
import yt_dlp
from datetime import datetime
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from src.models.download import DownloadTask, DownloadRequest, DownloadStatus, AudioQuality
from src.config.database import db
from src.services.websocket_manager import websocket_manager
from src.services.ffmpeg_manager import ffmpeg_manager
from src.config.settings import settings
import logging
import uuid
import re
from pathlib import Path
import tempfile
import shutil
import os
import certifi
import time
import random
from src.services.download_strategies import StrategySelector

logger = logging.getLogger(__name__)

class DownloadManager:
    def __init__(self):
        self.active_downloads: Dict[str, DownloadTask] = {}
        self.progress_callbacks: Dict[str, Callable[[str, float], None]] = {}
        self.quality_map = {
            AudioQuality.HIGH: "320",
            AudioQuality.MEDIUM: "192",
            AudioQuality.LOW: "128"
        }
        self.last_request_time = 0
        self.min_request_interval = 2  # Minimum seconds between requests
        
        # Initialize strategy selector
        self.strategy_selector = StrategySelector()
        
        # Get PO token from environment
        self.po_token = os.getenv('YOUTUBE_PO_TOKEN', '')
        if not self.po_token:
            logger.warning("YouTube PO token not found in environment variables")
        
        # Initialize Spotify client if credentials are available
        if hasattr(settings, 'SPOTIFY_CLIENT_ID') and hasattr(settings, 'SPOTIFY_CLIENT_SECRET'):
            self.spotify = spotipy.Spotify(
                client_credentials_manager=SpotifyClientCredentials(
                    client_id=settings.SPOTIFY_CLIENT_ID,
                    client_secret=settings.SPOTIFY_CLIENT_SECRET
                )
            )
        else:
            self.spotify = None
            logger.warning("Spotify credentials not found in settings")

    def register_progress_callback(self, task_id: str, callback: Callable[[str, float], None]):
        """Register a callback for progress updates"""
        self.progress_callbacks[task_id] = callback

    def unregister_progress_callback(self, task_id: str):
        """Unregister a progress callback"""
        if task_id in self.progress_callbacks:
            del self.progress_callbacks[task_id]

    def _create_progress_hook(self, task_id: str):
        async def progress_hook(d: Dict):
            if d['status'] == 'downloading':
                try:
                    total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                    if total > 0:
                        downloaded = d.get('downloaded_bytes', 0)
                        progress = (downloaded / total) * 100
                        await websocket_manager.broadcast_progress(
                            task_id=task_id,
                            progress=progress,
                            status='downloading'
                        )
                except Exception as e:
                    logger.error(f"Error in progress hook: {e}")
            elif d['status'] == 'finished':
                await websocket_manager.broadcast_progress(
                    task_id=task_id,
                    progress=100,
                    status='processing'
                )
        return progress_hook

    async def create_task(self, url: str, format: str = 'mp3', quality: AudioQuality = AudioQuality.HIGH) -> DownloadTask:
        """Create a new download task for a Spotify or YouTube playlist"""
        task = DownloadTask(
            id=str(uuid.uuid4()),
            url=url,
            format=format,
            quality=quality,
            status=DownloadStatus.QUEUED,
            progress=0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        self.active_downloads[task.id] = task
        
        # Store task in database
        await db.db.downloads.insert_one(task.model_dump())
        
        # Start processing in background
        asyncio.create_task(self._process_task(task))
        
        return task

    async def get_task(self, task_id: str) -> Optional[DownloadTask]:
        """Get a task by ID"""
        if task_id in self.active_downloads:
            return self.active_downloads[task_id]
            
        # Try to find in MongoDB
        task_data = await db.db.downloads.find_one({"id": task_id})
        if task_data:
            task = DownloadTask(**task_data)
            if task.status in [DownloadStatus.DOWNLOADING, DownloadStatus.PROCESSING]:
                self.active_downloads[task.id] = task
            return task
            
        return None

    async def update_task(self, task_id: str, **updates) -> Optional[DownloadTask]:
        """Update a task's status and progress"""
        task = await self.get_task(task_id)
        if not task:
            return None
            
        for key, value in updates.items():
            setattr(task, key, value)
        
        task.updated_at = datetime.utcnow()
            
        # Update in MongoDB
        await db.db.downloads.update_one(
            {"id": task_id},
            {"$set": task.model_dump()}
        )
        
        # Notify progress callback if registered
        if task_id in self.progress_callbacks and 'progress' in updates:
            self.progress_callbacks[task_id](task_id, updates['progress'])
        
        return task

    async def remove_task(self, task_id: str) -> bool:
        """Remove a task from active downloads"""
        if task_id in self.active_downloads:
            del self.active_downloads[task_id]
            self.unregister_progress_callback(task_id)
            return True
        return False

    async def _process_task(self, task: DownloadTask):
        """Process a download task based on URL type"""
        try:
            # Determine URL type
            is_spotify = 'spotify.com' in task.url.lower()
            is_youtube = any(domain in task.url.lower() for domain in ['youtube.com', 'youtu.be'])
            
            if is_spotify:
                if not self.spotify:
                    raise Exception("Spotify integration not configured")
                
                # Extract Spotify ID
                spotify_id = self._extract_spotify_id(task.url)
                if not spotify_id:
                    raise Exception("Invalid Spotify URL")
                
                # Process Spotify playlist
                await self._process_spotify_playlist(task, spotify_id)
                
            elif is_youtube:
                # Process YouTube playlist
                await self._process_youtube_playlist(task, task.url)
                
            else:
                raise Exception("Invalid URL. Please provide a Spotify or YouTube playlist URL.")
            
        except Exception as e:
            logger.error(f"Task processing error: {e}")
            task.status = DownloadStatus.ERROR
            task.error = str(e)
            await websocket_manager.broadcast_progress(
                task_id=task.id,
                progress=0,
                status='error',
                error=str(e)
            )
        finally:
            # Update task in database
            task.updated_at = datetime.utcnow()
            await self.update_task(task.id, **task.model_dump())

    def _extract_spotify_id(self, url: str) -> Optional[str]:
        """Extract Spotify ID from URL"""
        patterns = [
            r'spotify:track:([a-zA-Z0-9]+)',
            r'spotify.com/track/([a-zA-Z0-9]+)',
            r'spotify:playlist:([a-zA-Z0-9]+)',
            r'spotify.com/playlist/([a-zA-Z0-9]+)'
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    async def _rate_limit(self):
        """Implement rate limiting for requests"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_request_interval:
            delay = self.min_request_interval - time_since_last + random.uniform(0.1, 0.5)
            await asyncio.sleep(delay)
        self.last_request_time = time.time()

    def _get_yt_dlp_opts(self, temp_dir_path: Path, filename: str) -> dict:
        """Get yt-dlp options focused on audio extraction"""
        headers = {
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

        extractor_args = {
            'youtube': {
                'player_client': ['web', 'android'],  # Try web first, then android
                'player_skip': [],  # Don't skip anything
                'innertube_key': 'AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8',  # Latest key
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

        return {
            'format': 'bestaudio[ext=m4a]/bestaudio/best',  # Prefer m4a audio
            'extract_audio': True,
            'audio_format': 'mp3',
            'audio_quality': '0',  # Best quality
            'outtmpl': str(temp_dir_path / f"{filename}.%(ext)s"),
            'paths': {'home': str(temp_dir_path), 'temp': str(temp_dir_path)},
            'quiet': False,  # Enable output for debugging
            'verbose': True,  # Enable verbose output
            'no_warnings': False,  # Show warnings
            'progress_hooks': [lambda d: asyncio.create_task(self._progress_hook(d))],
            'noplaylist': True,
            'retries': 10,
            'fragment_retries': 10,
            'http_headers': headers,
            'cookiefile': '/app/youtube.cookies',
            'socket_timeout': 30,
            'extractor_args': extractor_args,
            'concurrent_fragment_downloads': 8,  # Speed up downloads
            'file_access_retries': 10,
            'hls_prefer_native': True,  # Use native HLS downloader
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            }],
            'keepvideo': False,
            'sleep_interval': random.randint(1, 3),  # Shorter delays
            'max_sleep_interval': 5,
            'sleep_interval_requests': 1,
            'overwrites': True,  # Overwrite files if they exist
        }

    async def _verify_cookies(self):
        """Verify and refresh YouTube cookies if needed"""
        try:
            cookie_file = Path('/app/youtube.cookies')
            if not cookie_file.exists():
                logger.warning("Cookie file not found")
                return False
                
            # Check cookie file format
            with open(cookie_file, 'r') as f:
                lines = f.readlines()
                
            if not lines or not lines[0].startswith('# Netscape HTTP Cookie File'):
                logger.warning("Invalid cookie file format")
                return False
                
            # Verify each cookie line
            valid_cookies = ['# Netscape HTTP Cookie File']
            for line in lines[1:]:
                if line.strip() and not line.startswith('#'):
                    parts = line.strip().split('\t')
                    if len(parts) == 7:  # Correct number of fields for Netscape format
                        valid_cookies.append(line.strip())
                    else:
                        logger.warning(f"Invalid cookie line format: {line}")
                        
            # Write back valid cookies
            with open(cookie_file, 'w') as f:
                f.write('\n'.join(valid_cookies))
                
            return True
            
        except Exception as e:
            logger.error(f"Error verifying cookies: {e}")
            return False

    async def _download_from_youtube(self, task: DownloadTask, query: str, filename: str):
        """Download a video from YouTube using the strategy system."""
        try:
            # Create temp directory for download
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_dir_path = Path(temp_dir)
                output_path = temp_dir_path / f"{filename}.mp3"
                
                # Get appropriate strategy
                strategy = await self.strategy_selector.get_strategy(query)
                if not strategy:
                    raise Exception("No suitable download strategy found")
                    
                # Start download
                async for progress_info in strategy.download(
                    url=query,
                    output_path=output_path,
                    quality=self.quality_map[task.quality]
                ):
                    # Update progress
                    if progress_info['status'] == 'error':
                        raise Exception(progress_info['error'])
                        
                    await websocket_manager.broadcast_progress(
                        task_id=task.id,
                        progress=progress_info['progress'],
                        status=progress_info['status']
                    )
                    
                    # Move file to downloads directory when complete
                    if progress_info['status'] == 'complete':
                        downloads_dir = Path('downloads')
                        downloads_dir.mkdir(exist_ok=True)
                        final_path = downloads_dir / f"{filename}.mp3"
                        
                        # Move the file
                        shutil.move(str(output_path), str(final_path))
                        
                        # Update task with file location
                        await self.update_task(
                            task.id,
                            status=DownloadStatus.COMPLETED,
                            progress=100,
                            file_path=str(final_path)
                        )
                        
        except Exception as e:
            logger.error(f"Error downloading from YouTube: {e}")
            await websocket_manager.broadcast_progress(
                task_id=task.id,
                progress=0,
                status='error',
                error=str(e)
            )
            raise

    async def _progress_hook(self, d: Dict):
        """Handle download progress updates"""
        try:
            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                if total > 0:
                    downloaded = d.get('downloaded_bytes', 0)
                    progress = (downloaded / total) * 100
                    await websocket_manager.broadcast_progress(
                        task_id=d['id'],
                        progress=progress,
                        status='downloading'
                    )
            elif d['status'] == 'finished':
                await websocket_manager.broadcast_progress(
                    task_id=d['id'],
                    progress=100,
                    status='processing'
                )
        except Exception as e:
            logger.error(f"Error in progress hook: {e}")

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a download task"""
        if task_id in self.active_downloads:
            task = self.active_downloads[task_id]
            task.status = DownloadStatus.ERROR
            task.error = "Download cancelled by user"
            task.updated_at = datetime.utcnow()
            await websocket_manager.broadcast_progress(
                task_id=task_id,
                progress=task.progress,
                status='error'
            )
            await self.update_task(task.id, **task.model_dump())
            return True
        return False

    async def _process_spotify_playlist(self, task: DownloadTask, spotify_id: str):
        """Process Spotify playlist and extract audio for each track"""
        try:
            results = self.spotify.playlist_tracks(spotify_id)
            tracks = results['items']
            
            # Handle pagination
            while results['next']:
                results = self.spotify.next(results)
                tracks.extend(results['items'])
            
            total_tracks = len(tracks)
            logger.info(f"Processing {total_tracks} tracks from Spotify playlist")
            
            for index, item in enumerate(tracks, 1):
                try:
                    track = item['track']
                    artists = ' '.join(artist['name'] for artist in track['artists'])
                    track_name = track['name']
                    
                    # Create search query matching desktop app format
                    query = f"{track_name} {artists} audio"
                    filename = f"{track_name} - {artists}"
                    
                    logger.info(f"Processing track {index}/{total_tracks}: {filename}")
                    
                    # Update progress
                    overall_progress = ((index - 1) / total_tracks) * 100
                    await websocket_manager.broadcast_progress(
                        task_id=task.id,
                        progress=overall_progress,
                        status=f'Processing track {index}/{total_tracks}'
                    )
                    
                    # Add random delay between tracks
                    await asyncio.sleep(random.uniform(5, 15))
                    
                    # Extract audio
                    await self._download_from_youtube(task, query, filename)
                    
                except Exception as e:
                    logger.error(f"Error processing track {index}/{total_tracks}: {e}")
                    # Add longer delay after error
                    await asyncio.sleep(random.uniform(15, 30))
                    continue
            
            task.status = DownloadStatus.COMPLETE
            await websocket_manager.broadcast_progress(
                task_id=task.id,
                progress=100,
                status='complete'
            )
            
        except Exception as e:
            logger.error(f"Error processing Spotify playlist: {e}")
            task.status = DownloadStatus.ERROR
            task.error = str(e)
            await websocket_manager.broadcast_progress(
                task_id=task.id,
                progress=0,
                status='error',
                error=str(e)
            )
            raise

    async def _process_youtube_playlist(self, task: DownloadTask, url: str):
        """Process YouTube playlist and extract audio for each video"""
        try:
            with yt_dlp.YoutubeDL({'extract_flat': True, 'quiet': True}) as ydl:
                # Get playlist info
                info = await asyncio.to_thread(ydl.extract_info, url, download=False)
                if not info:
                    raise Exception("Could not fetch playlist information")
                
                entries = info.get('entries', [])
                total_tracks = len(entries)
                
                logger.info(f"Processing {total_tracks} tracks from YouTube playlist")
                
                for index, entry in enumerate(entries, 1):
                    try:
                        video_url = entry['url']
                        title = entry.get('title', f'Track {index}')
                        
                        logger.info(f"Processing track {index}/{total_tracks}: {title}")
                        
                        # Update progress
                        overall_progress = ((index - 1) / total_tracks) * 100
                        await websocket_manager.broadcast_progress(
                            task_id=task.id,
                            progress=overall_progress,
                            status=f'Processing track {index}/{total_tracks}'
                        )
                        
                        # Extract audio
                        await self._download_from_youtube(task, video_url, title)
                        
                    except Exception as e:
                        logger.error(f"Error processing track {index}/{total_tracks}: {e}")
                        continue
                
                task.status = DownloadStatus.COMPLETE
                await websocket_manager.broadcast_progress(
                    task_id=task.id,
                    progress=100,
                    status='complete'
                )
                
        except Exception as e:
            logger.error(f"Error processing YouTube playlist: {e}")
            task.status = DownloadStatus.ERROR
            task.error = str(e)
            await websocket_manager.broadcast_progress(
                task_id=task.id,
                progress=0,
                status='error',
                error=str(e)
            )
            raise

# Create a global instance
download_manager = DownloadManager() 