import re
import os
import logging
import asyncio
import json
import tempfile
import subprocess
import time
import shutil
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
        self.temp_files = []  # List to track temporary files for cleanup
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
        """
        Extract the Spotify ID from a URL or URI.
        
        Args:
            url: Spotify URL or URI
            
        Returns:
            Spotify ID or None if not found
        """
        # Match playlist ID from URL or URI
        playlist_match = re.search(r'playlist[:/]([a-zA-Z0-9]+)', url)
        if playlist_match:
            return playlist_match.group(1)
            
        # Match track ID from URL or URI
        track_match = re.search(r'track[:/]([a-zA-Z0-9]+)', url)
        if track_match:
            return track_match.group(1)
            
        # Match album ID from URL or URI
        album_match = re.search(r'album[:/]([a-zA-Z0-9]+)', url)
        if album_match:
            return album_match.group(1)
            
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
            
            # Add temp_dir to the list of temporary files for cleanup
            self.temp_files.append(temp_dir)
            
            # Set up environment variables for script
            env = os.environ.copy()
            env['SPOTIFY_OUTPUT_DIR'] = str(temp_dir)  # Pass temp dir as an environment variable
            
            # Run the extractor script within the temporary directory
            cmd = ["python", self.extractor_script, url]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=str(temp_dir)  # Run from the temporary directory
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
            
            # Add the JSON file to the list of temporary files for cleanup
            self.temp_files.append(latest_file)
            
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
            
    async def download(self, task: DownloadTask, options: dict = None) -> AsyncGenerator[dict, None]:
        """Download a track or playlist from Spotify."""
        try:
            user_url = task.url or ""
            if not user_url:
                raise ValueError("No URL provided")

            if not self.is_spotify_url(user_url):
                raise ValueError(f"URL is not a valid Spotify URL: {user_url}")

            # Detect if it's a playlist or a track
            is_playlist = "playlist" in user_url

            # Set the output directory to the downloads folder
            output_dir = "/opt/render/project/src/server/downloads"
            os.makedirs(output_dir, exist_ok=True)
            
            # Get quality from options
            quality = options.get("quality", "high") if options else "high"
            
            # Use the URL to extract the track or playlist ID
            spotify_id = self._extract_spotify_id(user_url)
            
            # For playlists, create a dedicated directory
            if is_playlist:
                # Use our path generator for consistency
                _, output_dir = self.generate_output_paths({"playlist_id": spotify_id})
                
                # Log the playlist download
                logger.info(f"Downloading Spotify playlist: {user_url} to {output_dir}")
                yield {"status": "processing", "progress": 0, "detail": f"Starting download of Spotify playlist to {output_dir}"}
            else:
                # For single track
                output_path, output_dir = self.generate_output_paths({"track_id": spotify_id})
                logger.info(f"Downloading Spotify track: {user_url} to {output_path}")
                yield {"status": "processing", "progress": 0, "detail": f"Starting download of Spotify track to {output_path}"}
            
            # First yield a starting status
            yield {
                'status': 'downloading', 
                'progress': 0, 
                'details': 'Starting Spotify download process'
            }
            
            # Extract tracks using the extractor script
            json_file = await self.run_extractor_script(user_url)
            
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
                    
                    # Extract spotify ID for directory organization
                    spotify_id = self._extract_spotify_id(user_url) or 'unknown'
                    
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
                spotify_id = self._extract_spotify_id(user_url) or 'unknown'
            
            # Create a dedicated task-specific output directory
            if is_playlist:
                spotify_output_dir = output_dir
            else:
                # For single tracks, use the base directory
                spotify_output_dir = output_dir
                
            logger.info(f"Starting download with output directory: {spotify_output_dir}")
            
            # Add docker and render paths for compatibility
            docker_path = spotify_output_dir.replace("/opt/render/project/src/server/", "/app/")
            render_path = spotify_output_dir
            
            yield {"status": "processing", "progress": 10, "spotify_output_dir": render_path, "docker_path": docker_path}
            
            # Set up the command
            if quality == "high":
                bitrate = "320"
            else:
                bitrate = "192"
                
            # Set up proper output format with task ID for uniqueness
            output_format = "mp3"  # Just use mp3 format for the format parameter
            output_template = os.path.join(spotify_output_dir, f"%(title)s_{self.task_id}.mp3")  # Full path for output template
            
            # Set up command for the downloader script
            cmd = [
                self.downloader_script,
                json_file,
                "--output-dir", str(spotify_output_dir),
                "--format", output_format,
                "--quality", bitrate,
                "--output-template", output_template
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
            last_progress = 10  # Start with 10% (after initialization)
            last_update_time = time.time()
            
            # Process stdout in real-time with timeout protection
            try:
                # Set up queue for progress updates from tasks
                progress_queue = asyncio.Queue()
                
                # Flag to indicate when reading is done
                reading_complete = asyncio.Event()
                
                # Task to read stdout and stderr
                async def read_output():
                    nonlocal current_track, total_tracks, last_progress
                    try:
                        while True:
                            # Try to read from stdout with timeout
                            try:
                                line = await asyncio.wait_for(process.stdout.readline(), timeout=2.0)
                            except asyncio.TimeoutError:
                                # Send periodic update on timeout
                                await progress_queue.put({
                                    'status': 'downloading',
                                    'progress': last_progress,
                                    'details': f"Still working on track {current_track}/{total_tracks}..."
                                })
                                continue
                                
                            if not line:
                                # No more output from stdout, check stderr
                                stderr_line = await process.stderr.readline()
                                if not stderr_line:
                                    # No more output from both stdout and stderr
                                    break
                                else:
                                    # Process stderr output
                                    stderr_str = stderr_line.decode().strip()
                                    logger.debug(f"Downloader stderr: {stderr_str}")
                                    # Continue the loop
                                    continue
                                    
                            # Process stdout line
                            line_str = line.decode().strip()
                            logger.debug(f"Downloader output: {line_str}")
                            
                            # Check for track progress indicators
                            match = progress_pattern.search(line_str)
                            if match:
                                current_track = int(match.group(1))
                                total_tracks = int(match.group(2))
                                progress = int((current_track / total_tracks) * 80) + 10  # Scale to 10-90%
                                last_progress = progress
                                
                                await progress_queue.put({
                                    'status': 'downloading',
                                    'progress': progress,
                                    'details': f"Downloading track {current_track}/{total_tracks}"
                                })
                            
                            # Check for track names to provide more detailed status
                            if "Searching for:" in line_str:
                                track_name = line_str.split("Searching for:")[1].strip()
                                await progress_queue.put({
                                    'status': 'downloading',
                                    'progress': last_progress,
                                    'details': f"Searching for track: {track_name}"
                                })
                                
                            elif "Downloading to:" in line_str:
                                track_path = line_str.split("Downloading to:")[1].strip()
                                track_filename = os.path.basename(track_path)
                                
                                await progress_queue.put({
                                    'status': 'downloading',
                                    'progress': last_progress,
                                    'details': f"Downloading {track_filename}"
                                })
                            
                            # Check for success messages    
                            elif "Successfully downloaded:" in line_str:
                                track_name = line_str.split("Successfully downloaded:")[1].strip()
                                await progress_queue.put({
                                    'status': 'downloading',
                                    'progress': last_progress,
                                    'details': f"Successfully downloaded: {track_name}"
                                })
                                
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
                                await progress_queue.put({
                                    'status': 'processing',
                                    'progress': 95,
                                    'details': f"Download complete! Successfully downloaded {success_count}/{total_count} tracks."
                                })
                    except Exception as e:
                        logger.error(f"Error in read_output task: {e}")
                    finally:
                        reading_complete.set()  # Signal reading is done
                
                # Task to send heartbeat updates
                async def send_heartbeat():
                    nonlocal last_progress
                    try:
                        while not reading_complete.is_set():
                            await progress_queue.put({
                                'status': 'downloading',
                                'progress': last_progress,
                                'details': f"Still working on track {current_track}/{total_tracks}..."
                            })
                            await asyncio.sleep(3)  # Send update every 3 seconds
                    except Exception as e:
                        logger.error(f"Error in heartbeat task: {e}")
                
                # Start the tasks
                read_task = asyncio.create_task(read_output())
                heartbeat_task = asyncio.create_task(send_heartbeat())
                
                # Process updates from the queue and yield them
                while not reading_complete.is_set() or not progress_queue.empty():
                    try:
                        # Wait for a progress update with a timeout
                        update = await asyncio.wait_for(progress_queue.get(), timeout=1.0)
                        yield update
                        progress_queue.task_done()
                    except asyncio.TimeoutError:
                        # Check if reading is still in progress
                        if not reading_complete.is_set():
                            continue
                        else:
                            # If reading is done and queue is empty, break
                            if progress_queue.empty():
                                break
                    except Exception as e:
                        logger.error(f"Error processing progress update: {e}")
                
                # Clean up tasks
                try:
                    heartbeat_task.cancel()
                    await asyncio.gather(read_task, return_exceptions=True)
                except Exception as e:
                    logger.error(f"Error cleaning up tasks: {e}")
                    
            except Exception as e:
                logger.error(f"Error in download process: {e}")
                yield {
                    'status': 'downloading',
                    'progress': last_progress,
                    'details': f"Error in download process: {str(e)}"
                }
            
            # Get the remaining stderr
            try:
                stderr_data = await asyncio.wait_for(process.stderr.read(), timeout=2.0)
                stderr_str = stderr_data.decode()
                
                if stderr_str:
                    logger.warning(f"Downloader stderr: {stderr_str}")
            except asyncio.TimeoutError:
                logger.warning("Timeout reading stderr from downloader process")
            except Exception as e:
                logger.error(f"Error reading stderr: {e}")
            
            # Wait for the process to complete with a timeout
            return_code = None
            try:
                return_code = await asyncio.wait_for(process.wait(), timeout=5.0)
                logger.info(f"Downloader process completed with return code {return_code}")
            except asyncio.TimeoutError:
                logger.warning("Process did not complete in time, checking for files anyway")
                
            # Check if download was successful
            if return_code is not None and return_code != 0:
                logger.error(f"Downloader script failed with return code {return_code}")
                yield {
                    'status': 'error',
                    'progress': 0,
                    'error': f"Download failed with error code {return_code}"
                }
                return
                
            # Check for downloaded files
            downloaded_files = list(spotify_output_dir.glob("*.mp3"))
            if downloaded_files:
                file_count = len(downloaded_files)
                file_list = ", ".join([os.path.basename(str(f)) for f in downloaded_files[:3]])
                if file_count > 3:
                    file_list += f" and {file_count - 3} more files"
                
                # Add successful output directory to spotify_output_dir for tracking
                output_dir_info = f"{spotify_output_dir}\nDownloaded {file_count} files: {file_list}"
                
                # If we've reached here, download completed
                yield {
                    'status': 'processing',
                    'progress': 95,
                    'details': {
                        'statusMessage': 'Download completed, finalizing files',
                        'spotify_output_dir': str(spotify_output_dir).replace('/app/', '/opt/render/project/src/server/'),
                        'fileCount': file_count,
                        'spotify_output_dir': render_path,
                        'docker_path': docker_path,
                        'downloadPath': render_path,
                        'detail': {
                            'statusMessage': 'Download completed, finalizing files',
                            'spotify_output_dir': render_path,
                            'fileCount': file_count,
                            'docker_path': docker_path,
                            'downloadPath': render_path,
                            'files': downloaded_files
                        }
                    }
                }
                
                # Complete the task
                detail = {
                    "status": "complete", 
                    "file_count": len(downloaded_files), 
                    "spotify_output_dir": str(spotify_output_dir).replace('/app/', '/opt/render/project/src/server/'),
                    "files": downloaded_files
                }
                
                # Final yield
                yield {
                    "status": "complete", 
                    "progress": 100, 
                    "spotify_output_dir": render_path,
                    "detail": {
                        "status": "complete", 
                        "file_count": file_count,
                        "spotify_output_dir": render_path,
                        "docker_path": docker_path,
                        "downloadPath": render_path,
                        "files": [str(f) for f in downloaded_files]
                    }
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
        
        # Clean up temporary files and directories
        for temp_path in self.temp_files:
            try:
                if isinstance(temp_path, Path) and temp_path.exists():
                    if temp_path.is_file():
                        logger.info(f"Removing temporary file: {temp_path}")
                        temp_path.unlink()
                    elif temp_path.is_dir():
                        logger.info(f"Removing temporary directory: {temp_path}")
                        shutil.rmtree(temp_path, ignore_errors=True)
            except Exception as e:
                logger.error(f"Error cleaning up temporary file/directory {temp_path}: {e}")
                
        # Clear the list
        self.temp_files.clear()

    @staticmethod
    def can_handle(url: str) -> bool:
        """
        Check if this strategy can handle the given URL.
        
        Args:
            url: URL to check
            
        Returns:
            True if this strategy can handle the URL, False otherwise
        """
        return 'spotify.com' in url or url.startswith('spotify:') 

    def generate_output_paths(self, options: dict) -> tuple[str, str]:
        """Generate paths for a track."""
        track_id = options.get("track_id", options.get("id", ""))
        playlist_id = options.get("playlist_id", "")
        
        # Use Render path for consistent file access
        base_dir = "/opt/render/project/src/server/downloads"
        
        if playlist_id:
            # For playlists, create a dedicated directory
            output_dir = f"{base_dir}/spotify_{playlist_id}_{self.task_id}"
            os.makedirs(output_dir, exist_ok=True)
            logger.info(f"Created dedicated output directory for playlist: {output_dir}")
            
            # Create an output path for each track within the playlist directory
            filename = f"{track_id}.%(ext)s"
            output_path = os.path.join(output_dir, filename)
        else:
            # For single tracks, use a direct path
            filename = f"spotify_{track_id}_{self.task_id}.%(ext)s"
            output_path = os.path.join(base_dir, filename)
            output_dir = base_dir
            
        # Store both paths for later use
        self.output_dir = output_dir
        logger.info(f"Output directory: {output_dir}")
        logger.info(f"Output path: {output_path}")
        
        return output_path, output_dir 

    async def run(self, task: DownloadTask) -> AsyncGenerator[dict, None]:
        """Run the Spotify download strategy."""
        try:
            logger.info(f"Starting Spotify download for task {task.id}")
            
            # Set default options
            options = task.options or {}
            
            async for update in self.download(task, options):
                yield update
                
        except Exception as e:
            logger.error(f"Error in Spotify strategy: {e}", exc_info=True)
            yield {"status": "error", "error": str(e)}

    # Helper methods for Spotify
    async def run_extractor_script(self, spotify_url: str) -> Optional[str]:
        """Run the Spotify extractor script to get track information."""
        try:
            logger.info(f"Running extractor script for URL: {spotify_url}")
            
            # Create temporary directory for output
            temp_dir = Path(settings.TEMP_DIR) / "spotify"
            temp_dir.mkdir(exist_ok=True, parents=True)
            
            # Add temp_dir to the list of temporary files for cleanup
            self.temp_files.append(temp_dir)
            
            # Set up environment variables for script
            env = os.environ.copy()
            env['SPOTIFY_OUTPUT_DIR'] = str(temp_dir)  # Pass temp dir as an environment variable
            
            # Run the extractor script within the temporary directory
            cmd = ["python", self.extractor_script, spotify_url]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=str(temp_dir)  # Run from the temporary directory
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
            
            # Add the JSON file to the list of temporary files for cleanup
            self.temp_files.append(latest_file)
            
            return str(latest_file)
            
        except Exception as e:
            logger.error(f"Error running extractor script: {e}")
            return None 