import re
import os
import logging
import asyncio
import json
import tempfile
import subprocess
import time
from typing import Dict, List, Any, Optional, Generator, AsyncGenerator
from pathlib import Path

from .base import DownloadStrategy
from .ytdlp_strategy import YtdlpStrategy
from ...config.settings import settings

logger = logging.getLogger(__name__)

class SpotifyStrategy(DownloadStrategy):
    """Strategy for handling Spotify URLs using the standalone scripts."""
    
    def __init__(self):
        """Initialize the Spotify strategy."""
        super().__init__()
        self.ytdlp_strategy = YtdlpStrategy()
        logger.info("Initialized Spotify strategy with standalone scripts approach")
        
        # Path to standalone scripts - Update to point to server directory root
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
        self.extractor_script = os.path.join(root_dir, "spotify_track_extractor.py")
        self.downloader_script = os.path.join(root_dir, "download_spotify_direct.py")
        
        # Check if scripts exist
        if not os.path.exists(self.extractor_script):
            logger.warning(f"Spotify extractor script not found at {self.extractor_script}")
            # Try alternate locations
            alt_paths = [
                "/app/spotify_track_extractor.py",
                "spotify_track_extractor.py",
                os.path.join(os.getcwd(), "spotify_track_extractor.py")
            ]
            for path in alt_paths:
                if os.path.exists(path):
                    self.extractor_script = path
                    logger.info(f"Found extractor script at {path}")
                    break
            
        if not os.path.exists(self.downloader_script):
            logger.warning(f"Spotify downloader script not found at {self.downloader_script}")
            # Try alternate locations
            alt_paths = [
                "/app/download_spotify_direct.py",
                "download_spotify_direct.py",
                os.path.join(os.getcwd(), "download_spotify_direct.py")
            ]
            for path in alt_paths:
                if os.path.exists(path):
                    self.downloader_script = path
                    logger.info(f"Found downloader script at {path}")
                    break
            
        logger.info(f"Using extractor script: {self.extractor_script}")
        logger.info(f"Using downloader script: {self.downloader_script}")
        
    async def validate_url(self, url: str) -> bool:
        """Validate if the URL is a Spotify URL."""
        try:
            url = str(url).strip()
            logger.info(f"Validating Spotify URL: {url}")
            
            # Define regex patterns for Spotify URLs
            spotify_track_pattern = re.compile(r'(https?://open\.spotify\.com/track/|spotify:track:)([a-zA-Z0-9]+)')
            spotify_playlist_pattern = re.compile(r'(https?://open\.spotify\.com/playlist/|spotify:playlist:)([a-zA-Z0-9]+)')
            
            # Check if URL matches any Spotify pattern
            is_track = bool(spotify_track_pattern.match(url))
            is_playlist = bool(spotify_playlist_pattern.match(url))
            
            if is_track or is_playlist:
                logger.info(f"URL is a valid Spotify {'track' if is_track else 'playlist'} URL")
                return True
            else:
                logger.debug(f"URL does not match Spotify patterns: {url}")
                return False
        except Exception as e:
            logger.error(f"Error validating Spotify URL: {e}")
            return False
            
    def _extract_spotify_id(self, url: str) -> Optional[str]:
        """Extract Spotify ID from URL."""
        try:
            if 'open.spotify.com' in url:
                path_parts = url.split('/')
                if len(path_parts) >= 5:  # https://open.spotify.com/track/ID
                    spotify_id = path_parts[4].split('?')[0]
                    return spotify_id
            elif url.startswith('spotify:'):
                parts = url.split(':')
                if len(parts) >= 3:
                    spotify_id = parts[2]
                    return spotify_id
            return None
        except Exception as e:
            logger.error(f"Error extracting Spotify ID: {e}")
            return None
            
    async def run_extractor_script(self, url: str) -> Optional[str]:
        """
        Run the standalone extractor script to get track information.
        
        Args:
            url: Spotify URL
            
        Returns:
            Path to the JSON file containing track information
        """
        try:
            logger.info(f"Running extractor script for URL: {url}")
            
            # Create temporary directory for output
            temp_dir = Path(settings.TEMP_DIR) / "spotify"
            temp_dir.mkdir(exist_ok=True, parents=True)
            
            # Set up environment variables for script
            env = os.environ.copy()
            
            # Run the extractor script
            cmd = ["python", self.extractor_script, url]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=str(temp_dir)
            )
            
            stdout, stderr = await process.communicate()
            stdout_str = stdout.decode()
            stderr_str = stderr.decode()
            
            logger.debug(f"Extractor script stdout: {stdout_str}")
            if stderr_str:
                logger.warning(f"Extractor script stderr: {stderr_str}")
                
            if process.returncode != 0:
                logger.error(f"Extractor script failed with return code {process.returncode}")
                return None
                
            # Find the output JSON file in the temp directory
            json_files = list(temp_dir.glob("*_tracks.json"))
            if not json_files:
                logger.error("No track information JSON file found after running extractor")
                return None
                
            # Use the most recently created file
            latest_file = max(json_files, key=lambda f: f.stat().st_mtime)
            logger.info(f"Found track information at {latest_file}")
            
            return str(latest_file)
            
        except Exception as e:
            logger.error(f"Error running extractor script: {e}")
            return None
            
    async def get_info(self, url: str) -> Dict[str, Any]:
        """
        Get information about the Spotify content.
        
        Args:
            url: Spotify URL to get info for
            
        Returns:
            Dict containing metadata like title, type, etc.
        """
        try:
            logger.info(f"Getting info for Spotify URL: {url}")
            
            # Check if it's a playlist or track
            is_playlist = 'playlist' in url.lower()
            
            # Run the extractor script to get track information
            json_file = await self.run_extractor_script(url)
            
            if not json_file:
                logger.error("Failed to extract track information")
                return {
                    'title': 'Unknown Spotify Content',
                    'type': 'playlist' if is_playlist else 'track',
                    'platform': 'spotify',
                    'error': 'Failed to extract track information',
                    'url': url
                }
                
            # Read the JSON file
            try:
                with open(json_file, 'r') as f:
                    tracks = json.load(f)
            except Exception as e:
                logger.error(f"Error reading track information: {e}")
                return {
                    'title': 'Unknown Spotify Content',
                    'type': 'playlist' if is_playlist else 'track',
                    'platform': 'spotify',
                    'error': f'Error reading track information: {str(e)}',
                    'url': url
                }
                
            # Extract information from the tracks
            if is_playlist:
                # Get playlist name from JSON file name
                playlist_name = os.path.basename(json_file).replace('_tracks.json', '')
                
                return {
                    'title': f"Spotify Playlist: {playlist_name}",
                    'type': 'playlist',
                    'platform': 'spotify',
                    'track_count': len(tracks),
                    'tracks': tracks[:5],  # Include first 5 tracks as preview
                    'url': url,
                    'task_id': self._extract_spotify_id(url) or 'unknown'  # Add task_id for frontend
                }
            else:
                # Single track
                if not tracks:
                    return {
                        'title': 'Unknown Spotify Track',
                        'type': 'track',
                        'platform': 'spotify',
                        'error': 'Could not retrieve track information',
                        'url': url
                    }
                
                track = tracks[0]
                track_name = track.get('name', 'Unknown Track')
                
                # Handle different artist formats
                if isinstance(track.get('artists'), list):
                    artists = track.get('artists', [])
                    artist_str = ", ".join(artists) if artists else "Unknown Artist"
                else:
                    artist_str = track.get('artists', 'Unknown Artist')
                
                return {
                    'title': f"{track_name} - {artist_str}",
                    'type': 'track',
                    'platform': 'spotify',
                    'artists': artist_str,
                    'track_name': track_name,
                    'url': url,
                    'task_id': self._extract_spotify_id(url) or 'unknown'  # Add task_id for frontend
                }
                
        except Exception as e:
            logger.error(f"Error getting Spotify info: {e}")
            return {
                'title': 'Unknown Spotify Content',
                'type': 'unknown',
                'platform': 'spotify',
                'error': str(e),
                'url': url
            }
            
    async def download(self, url: str, output_path: Path, quality: str = "high") -> AsyncGenerator[Dict[str, Any], None]:
        """
        Download tracks from Spotify URL using the standalone downloader script.
        
        Args:
            url: The Spotify URL to download from
            output_path: Path to save the downloaded files
            quality: Audio quality setting
            
        Yields:
            Progress updates as dictionaries
        """
        try:
            # First yield a starting status
            yield {
                'status': 'downloading', 
                'progress': 0, 
                'details': 'Starting Spotify download process'
            }
            
            # Extract tracks using the extractor script
            json_file = await self.run_extractor_script(url)
            
            if not json_file:
                logger.error("Failed to extract track information")
                yield {
                    'status': 'error',
                    'progress': 0,
                    'error': 'Failed to extract track information from Spotify URL'
                }
                return
                
            logger.info(f"Successfully extracted track information to {json_file}")
            
            # Get track count to calculate progress
            try:
                with open(json_file, 'r') as f:
                    tracks = json.load(f)
                    track_count = len(tracks)
                    logger.info(f"Found {track_count} tracks in playlist")
                    
                    # Yield track list information
                    track_names = [f"{t.get('name', 'Unknown')} - {', '.join(t.get('artists', ['Unknown']))}" for t in tracks[:10]]
                    playlist_info = f"Playlist contains {track_count} tracks. First tracks: " + " | ".join(track_names[:3])
                    if track_count > 3:
                        playlist_info += f" (+ {track_count - 3} more)"
                    
                    yield {
                        'status': 'downloading',
                        'progress': 5,
                        'details': playlist_info
                    }
            except Exception as e:
                logger.error(f"Error reading track information: {e}")
                track_count = 0
            
            # Prepare output directory
            output_dir = output_path.parent
            output_dir.mkdir(exist_ok=True, parents=True)
            
            # Yield progress update before starting the download
            yield {
                'status': 'downloading',
                'progress': 10,
                'details': f'Starting download of {track_count} tracks from YouTube'
            }
            
            # Set up command for the downloader script
            cmd = [
                "python", 
                self.downloader_script,
                json_file,
                "--output-dir", str(output_dir),
                "--format", "mp3",
                "--quality", "192" if quality.lower() == "medium" else "320"
            ]
            
            logger.info(f"Running downloader script: {' '.join(cmd)}")
            
            # Start the process
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Track progress using stdout
            progress_pattern = re.compile(r'\[(\d+)/(\d+)\]')
            current_track = 0
            total_tracks = track_count if track_count > 0 else 1
            
            # Variables to track updates
            last_progress = 0
            last_update_time = time.time()
            
            # Process stdout in real-time
            while True:
                line = await process.stdout.readline()
                if not line:
                    # No more output but process might still be running
                    # Check if there's anything in stderr
                    stderr_line = await process.stderr.readline()
                    if not stderr_line:
                        # If no output from stdout or stderr, break
                        break
                    else:
                        # Log stderr output
                        stderr_str = stderr_line.decode().strip()
                        logger.debug(f"Downloader stderr: {stderr_str}")
                        
                        # Yield progress update to keep frontend informed
                        current_time = time.time()
                        if current_time - last_update_time > 2:  # Send update every 2 seconds
                            last_update_time = current_time
                            yield {
                                'status': 'downloading',
                                'progress': last_progress,
                                'details': f"Still working on track {current_track}/{total_tracks}..." 
                            }
                        continue
                        
                line_str = line.decode().strip()
                logger.debug(f"Downloader output: {line_str}")
                
                # Check for track progress indicators
                match = progress_pattern.search(line_str)
                if match:
                    current_track = int(match.group(1))
                    total_tracks = int(match.group(2))
                    progress = int((current_track / total_tracks) * 80) + 10  # Scale to 10-90%
                    last_progress = progress
                    
                    yield {
                        'status': 'downloading',
                        'progress': progress,
                        'details': f"Downloading track {current_track}/{total_tracks}"
                    }
                    last_update_time = time.time()
                
                # Check for track names to provide more detailed status
                if "Searching for:" in line_str:
                    track_name = line_str.split("Searching for:")[1].strip()
                    yield {
                        'status': 'downloading',
                        'progress': last_progress,
                        'details': f"Searching for track: {track_name}"
                    }
                    last_update_time = time.time()
                    
                elif "Downloading to:" in line_str:
                    track_path = line_str.split("Downloading to:")[1].strip()
                    track_filename = os.path.basename(track_path)
                    
                    yield {
                        'status': 'downloading',
                        'progress': last_progress,
                        'details': f"Downloading {track_filename}"
                    }
                    last_update_time = time.time()
                
                # Check for success messages    
                elif "Successfully downloaded:" in line_str:
                    track_name = line_str.split("Successfully downloaded:")[1].strip()
                    yield {
                        'status': 'downloading',
                        'progress': last_progress,
                        'details': f"Successfully downloaded: {track_name}"
                    }
                    last_update_time = time.time()
                    
                # Check for completion messages
                elif "Download complete" in line_str:
                    success_count = 0
                    total_count = 0
                    
                    if "Successfully downloaded" in line_str:
                        parts = line_str.split("Successfully downloaded")[1].strip()
                        if "/" in parts:
                            success_parts = parts.split("/")
                            success_count = int(success_parts[0])
                            total_count = int(success_parts[1].split(" ")[0])
                    
                    # Explicitly yield a 95% progress update
                    yield {
                        'status': 'processing',
                        'progress': 95,
                        'details': f"Download complete! Successfully downloaded {success_count}/{total_count} tracks."
                    }
                
                # Force periodic updates to keep connection alive
                current_time = time.time()
                if current_time - last_update_time > 3:  # Send at least every 3 seconds
                    last_update_time = current_time
                    yield {
                        'status': 'downloading',
                        'progress': last_progress,
                        'details': f"Still working on track {current_track}/{total_tracks}..."
                    }
            
            # Get the remaining stderr
            stderr_data = await process.stderr.read()
            stderr_str = stderr_data.decode()
            
            if stderr_str:
                logger.warning(f"Downloader stderr: {stderr_str}")
            
            # Wait for the process to complete
            await process.wait()
            
            # Check if download was successful
            if process.returncode != 0:
                logger.error(f"Downloader script failed with return code {process.returncode}")
                yield {
                    'status': 'error',
                    'progress': 0,
                    'error': f"Download failed with error code {process.returncode}"
                }
                return
                
            # Check for downloaded files
            downloaded_files = list(output_dir.glob("*.mp3"))
            if downloaded_files:
                file_count = len(downloaded_files)
                file_list = ", ".join([os.path.basename(str(f)) for f in downloaded_files[:3]])
                if file_count > 3:
                    file_list += f" and {file_count - 3} more files"
                
                # Yield success status with explicit file path information
                yield {
                    'status': 'complete',
                    'progress': 100,
                    'details': f"Download complete - tracks saved to {output_dir}\nDownloaded files: {file_list}"
                }
            else:
                logger.warning("No MP3 files found in output directory after download")
                yield {
                    'status': 'error',
                    'progress': 0,
                    'error': "Download process completed but no files were found"
                }
            
        except Exception as e:
            logger.error(f"Error in download process: {e}")
            yield {
                'status': 'error',
                'progress': 0,
                'error': f"Download failed: {str(e)}"
            }
            
    async def cleanup(self):
        """Clean up resources."""
        await self.ytdlp_strategy.cleanup() 