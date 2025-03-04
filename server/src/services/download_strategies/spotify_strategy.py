import re
import os
import logging
import asyncio
import json
import tempfile
import subprocess
import time
import shutil
import zipfile
from typing import Dict, List, Any, Optional, Generator, AsyncGenerator, Union
from pathlib import Path
from datetime import datetime
from fastapi import HTTPException

from src.config.settings import settings
from src.models.download import DownloadTask, DownloadStatus, DownloadError
from src.services.download_strategies.base_strategy import DownloadStrategy
from src.services.download_strategies.ytdlp_strategy import YtdlpStrategy

logger = logging.getLogger(__name__)

class SpotifyStrategy(DownloadStrategy):
    """Strategy for handling Spotify URLs using the standalone scripts."""
    
    def __init__(self):
        """Initialize the Spotify strategy."""
        super().__init__()
        self.ytdlp_strategy = YtdlpStrategy()
        self.temp_files = []  # List to track temporary files for cleanup
        self.task_id = None  # Will be set when download is called
        logger.info("Initialized Spotify strategy with standalone scripts approach")
        
        # Path to standalone scripts - set paths for Render environment
        # Check if running on Render
        is_render = settings.IS_RENDER
        
        # Set up organized directory structure
        if is_render:
            # Use Render's persistent storage for all data
            render_root = "/opt/render/project/src/server"
            data_root = str(settings.RENDER_DATA_DIR)
            
            # Create organized directory structure
            self.scripts_dir = os.path.join(data_root, "scripts")
            self.temp_dir = os.path.join(data_root, "temp")
            self.spotify_temp_dir = os.path.join(self.temp_dir, "spotify")
            self.downloads_dir = os.path.join(data_root, "downloads")
            
            # Ensure all directories exist
            for directory in [self.scripts_dir, self.temp_dir, self.spotify_temp_dir, self.downloads_dir]:
                os.makedirs(directory, exist_ok=True)
                logger.info(f"Ensured directory exists: {directory}")
            
            # Set up script paths in the persistent scripts directory
            self.extractor_script = os.path.join(self.scripts_dir, "spotify_track_extractor.py")
            self.downloader_script = os.path.join(self.scripts_dir, "download_spotify_direct.py")
            self.cookies_path = os.path.join(self.scripts_dir, "youtube.cookies")
            
            # Check for YouTube cookies in multiple locations
            repo_cookies_path = os.path.join(render_root, "youtube.cookies")
            render_secrets_path = "/etc/secrets/youtube.cookies"
            
            # Copy cookies if they exist in either location
            if os.path.exists(render_secrets_path):
                logger.info(f"Copying YouTube cookies from Render secrets to scripts directory")
                try:
                    shutil.copy2(render_secrets_path, self.cookies_path)
                    os.chmod(self.cookies_path, 0o600)  # Restrictive permissions for security
                    logger.info(f"Successfully copied YouTube cookies to: {self.cookies_path}")
                except Exception as e:
                    logger.error(f"Failed to copy YouTube cookies from Render secrets: {e}")
            elif os.path.exists(repo_cookies_path):
                logger.info(f"Copying YouTube cookies from repository to scripts directory")
                try:
                    shutil.copy2(repo_cookies_path, self.cookies_path)
                    os.chmod(self.cookies_path, 0o600)  # Restrictive permissions for security
                    logger.info(f"Successfully copied YouTube cookies to: {self.cookies_path}")
                except Exception as e:
                    logger.error(f"Failed to copy YouTube cookies from repository: {e}")
            else:
                logger.warning("No YouTube cookies file found. Downloads may fail due to bot detection.")
            
            # If scripts don't exist in the data directory, copy them from the app directory
            if not os.path.exists(self.extractor_script):
                source_script = os.path.join(render_root, "spotify_track_extractor.py")
                if os.path.exists(source_script):
                    logger.info(f"Copying extractor script to data directory: {self.extractor_script}")
                    try:
                        shutil.copy2(source_script, self.extractor_script)
                        # Set executable permissions
                        os.chmod(self.extractor_script, 0o755)
                    except Exception as e:
                        logger.error(f"Failed to copy extractor script: {e}")
            
            if not os.path.exists(self.downloader_script):
                source_script = os.path.join(render_root, "download_spotify_direct.py")
                if os.path.exists(source_script):
                    logger.info(f"Copying downloader script to data directory: {self.downloader_script}")
                    try:
                        shutil.copy2(source_script, self.downloader_script)
                        # Set executable permissions
                        os.chmod(self.downloader_script, 0o755)
                    except Exception as e:
                        logger.error(f"Failed to copy downloader script: {e}")
        else:
            # Development environment paths - use absolute paths
            server_dir = os.getcwd()
            
            # Create organized directory structure
            self.scripts_dir = os.path.join(server_dir, "scripts")
            self.temp_dir = os.path.join(server_dir, "temp")
            self.spotify_temp_dir = os.path.join(self.temp_dir, "spotify")
            self.downloads_dir = os.path.join(server_dir, "downloads")
            
            # Ensure all directories exist
            for directory in [self.scripts_dir, self.temp_dir, self.spotify_temp_dir, self.downloads_dir]:
                os.makedirs(directory, exist_ok=True)
                logger.info(f"Ensured directory exists: {directory}")
            
            # Set paths to the scripts - in development they're in the root directory
            self.extractor_script = os.path.join(server_dir, "spotify_track_extractor.py")
            self.downloader_script = os.path.join(server_dir, "download_spotify_direct.py")
            self.cookies_path = os.path.join(self.scripts_dir, "youtube.cookies")
            
            # Check for YouTube cookies in the repository
            repo_cookies_path = os.path.join(server_dir, "youtube.cookies")
            
            # Copy cookies if they exist
            if os.path.exists(repo_cookies_path):
                logger.info(f"Copying YouTube cookies from repository to scripts directory")
                try:
                    shutil.copy2(repo_cookies_path, self.cookies_path)
                    os.chmod(self.cookies_path, 0o600)  # Restrictive permissions for security
                    logger.info(f"Successfully copied YouTube cookies to: {self.cookies_path}")
                except Exception as e:
                    logger.error(f"Failed to copy YouTube cookies from repository: {e}")
            else:
                logger.warning("No YouTube cookies file found in development environment. Downloads may fail due to bot detection.")
            
        # Final fallback to any location in PATH
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
                    
        # Add executable permissions
        try:
            os.chmod(self.extractor_script, 0o755)
            os.chmod(self.downloader_script, 0o755)
            logger.info(f"Added executable permissions to scripts")
        except Exception as e:
            logger.warning(f"Could not set permissions on scripts: {e}")
            
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
            
    def is_spotify_url(self, url: str) -> bool:
        """
        Check if the URL is a Spotify URL.
        This is a sync version of validate_url for use in non-async contexts.
        
        Args:
            url: URL to check
            
        Returns:
            True if URL is a Spotify URL, False otherwise
        """
        # Simple check for spotify domains or URI scheme
        return 'spotify.com' in url or url.startswith('spotify:')
            
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
            
    async def run_extractor_script(self, spotify_url: str) -> Optional[str]:
        """Run the Spotify extractor script to get track information."""
        try:
            logger.info(f"Running extractor script for URL: {spotify_url}")
            
            # Use the pre-created spotify temp directory
            temp_dir = Path(self.spotify_temp_dir)
            logger.info(f"Using temporary output directory: {temp_dir}")
            
            # Generate a unique subdirectory for this extraction to avoid conflicts
            import uuid
            run_id = str(uuid.uuid4())[:8]
            extraction_dir = temp_dir / run_id
            extraction_dir.mkdir(exist_ok=True, parents=True)
            logger.info(f"Created unique extraction directory: {extraction_dir}")
            
            # Add extraction_dir to the list of temporary files for cleanup
            self.temp_files.append(extraction_dir)
            
            # Check if the extractor script exists
            if not os.path.exists(self.extractor_script):
                logger.error(f"Extractor script not found at {self.extractor_script}")
                return None
            else:
                logger.info(f"Using extractor script at {self.extractor_script}")
            
            # Try two approaches to ensure the output file is created in our directory
            
            # Approach 1: Modify the script (preferred but may fail)
            use_modified_script = True
            modified_script_path = extraction_dir / "modified_extractor.py"
            
            try:
                # Read the original script
                with open(self.extractor_script, 'r') as f:
                    script_content = f.read()
                
                # Modify the script to save files to our extraction directory
                # Find the line that saves the JSON file
                output_file_line = "output_file = f\"{safe_name}_tracks.json\""
                modified_output_file_line = f"output_file = os.path.join('{str(extraction_dir)}', f\"{{safe_name}}_tracks.json\")"
                
                # Replace the line with our modified version
                modified_script = script_content.replace(output_file_line, modified_output_file_line)
                
                # Write the modified script
                with open(modified_script_path, 'w') as f:
                    f.write(modified_script)
                
                # Make it executable
                os.chmod(modified_script_path, 0o755)
                logger.info(f"Created modified extractor script at {modified_script_path}")
                
                # Add to cleanup list
                self.temp_files.append(modified_script_path)
            except Exception as e:
                logger.error(f"Failed to create modified extractor script: {e}")
                use_modified_script = False
            
            # Approach 2: Create symbolic link from current working directory to extraction directory
            # This is a fallback for when we can't modify the script
            symlink_created = False
            cwd_path = Path.cwd()
            
            if not use_modified_script:
                try:
                    # Create a symlink to track cwd files in our extraction directory
                    # This helps us keep track of files created in the current directory
                    symlink_path = extraction_dir / "cwd_link"
                    if symlink_path.exists():
                        symlink_path.unlink()
                    
                    # Create symlink from extraction_dir/cwd_link to current working directory
                    os.symlink(cwd_path, symlink_path)
                    logger.info(f"Created symlink from {symlink_path} to {cwd_path}")
                    symlink_created = True
                    self.temp_files.append(symlink_path)
                except Exception as e:
                    logger.warning(f"Could not create symlink, falling back to path monitoring: {e}")
            
            # Set up environment variables for script
            env = os.environ.copy()
            env['SPOTIFY_OUTPUT_DIR'] = str(extraction_dir)  # Pass output dir as environment variable
            env['PYTHONPATH'] = os.getcwd()  # Ensure the script can import app modules
            
            # Determine which script to run
            script_to_run = str(modified_script_path) if use_modified_script else self.extractor_script 
            cmd = ["python", script_to_run, spotify_url]
            logger.info(f"Running command: {' '.join(cmd)}")
            
            # Track files in cwd before running script if we couldn't modify it
            existing_json_files = set()
            if not use_modified_script:
                existing_json_files = set(path for path in cwd_path.glob("*_tracks.json"))
                logger.info(f"Found {len(existing_json_files)} existing JSON files in CWD before running script")
            
            # Run the extractor script
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=os.getcwd()  # Run from the application root
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
            
            # If we didn't modify the script, check for new files in cwd
            if not use_modified_script:
                # Find new JSON files that appeared in cwd after running the script
                new_json_files = set(path for path in cwd_path.glob("*_tracks.json")) - existing_json_files
                if new_json_files:
                    latest_file = max(new_json_files, key=lambda f: f.stat().st_mtime)
                    logger.info(f"Found new track information file in CWD: {latest_file}")
                    
                    # Copy the file to our extraction directory
                    dest_path = extraction_dir / latest_file.name
                    try:
                        shutil.copy2(latest_file, dest_path)
                        logger.info(f"Copied JSON file to extraction directory: {dest_path}")
                        
                        # Add original file to temp_files for cleanup
                        self.temp_files.append(latest_file)
                        
                        return str(dest_path)
                    except Exception as e:
                        logger.error(f"Failed to copy JSON file to extraction directory: {e}")
                        # Continue with the search anyway
            
            # Look for the output JSON file in multiple possible locations
            search_paths = [
                extraction_dir,  # Our dedicated extraction directory (primary)
                Path.cwd(),      # Current working directory (fallback)
                Path(self.temp_dir),  # General temp directory
                Path(self.spotify_temp_dir)  # Spotify temp directory
            ]
            
            for search_path in search_paths:
                logger.info(f"Searching for JSON files in {search_path}")
                json_files = list(search_path.glob("*_tracks.json"))
                if json_files:
                    # Use the most recently created file
                    latest_file = max(json_files, key=lambda f: f.stat().st_mtime)
                    logger.info(f"Found track information at {latest_file}")
                    
                    # If file is not in our extraction directory, copy it there for future reference
                    if latest_file.parent != extraction_dir:
                        dest_path = extraction_dir / latest_file.name
                        shutil.copy2(latest_file, dest_path)
                        logger.info(f"Copied JSON file to extraction directory: {dest_path}")
                        
                        # Add the original file to cleanup if it's not in our extraction directory
                        if not str(latest_file).startswith(str(extraction_dir)):
                            self.temp_files.append(latest_file)
                        
                        latest_file = dest_path
                    
                    # Add the JSON file to the list of temporary files for cleanup
                    self.temp_files.append(latest_file)
                    
                    return str(latest_file)
            
            # Try to parse the output to see if we can get file path information
            if stdout_str:
                # Look for lines like "Track information saved to <filename>"
                import re
                file_match = re.search(r"Track information saved to\s+(\S+)", stdout_str)
                if file_match:
                    potential_file = file_match.group(1).strip()
                    logger.info(f"Found potential file path in output: {potential_file}")
                    
                    # Try different path combinations
                    potential_paths = [
                        Path(potential_file),  # As is
                        Path.cwd() / potential_file,  # Relative to cwd
                        extraction_dir / potential_file  # Relative to extraction dir
                    ]
                    
                    for path in potential_paths:
                        if path.exists():
                            logger.info(f"Found track information file from stdout: {path}")
                            
                            # Copy to extraction dir if not already there
                            if path.parent != extraction_dir:
                                dest_path = extraction_dir / path.name
                                shutil.copy2(path, dest_path)
                                logger.info(f"Copied JSON file to extraction directory: {dest_path}")
                                self.temp_files.append(path)
                                path = dest_path
                            
                            # Add to cleanup
                            self.temp_files.append(path)
                            return str(path)
            
            logger.error("No track information JSON file found after running extractor")
            return None
            
        except Exception as e:
            logger.error(f"Error running extractor script: {e}", exc_info=True)
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
            
    async def download(self, url: str, output_path: str, quality: str = None) -> AsyncGenerator[dict, None]:
        """
        Download a track or playlist from Spotify.
        
        Args:
            url: The Spotify URL to download from
            output_path: Path where the downloaded file should be saved
            quality: The quality setting (optional)
            
        Yields:
            Status updates as the download progresses
        """
        # Save task_id to use in filenames, etc.
        self.task_id = Path(output_path).stem
        
        # Validate URL before proceeding
        if not self.is_spotify_url(url):
            logger.error(f"Invalid Spotify URL: {url}")
            yield {
                "status": "error",
                "details": {"message": f"Invalid Spotify URL: {url}"}
            }
            return
            
        # Extract Spotify ID for use in filenames
        spotify_id = self._extract_spotify_id(url)
        if not spotify_id:
            logger.error(f"Could not extract Spotify ID from URL: {url}")
            yield {
                "status": "error",
                "details": {"message": f"Could not extract Spotify ID from URL: {url}"}
            }
            return
        
        # Use the Render data directory if running on Render
        if settings.IS_RENDER:
            # Use the mounted disk for output
            base_output_dir = Path(settings.RENDER_DATA_DIR) / "downloads"
            logger.info(f"Using Render data directory for output: {base_output_dir}")
        else:
            # Use the configured output directory for development
            base_output_dir = Path(settings.DOWNLOADS_DIR)
            
        # Create a dedicated output directory for this task
        spotify_output_dir = base_output_dir / f"spotify_{spotify_id}_{self.task_id}"
        
        try:
            # Ensure output directory exists
            spotify_output_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created dedicated output directory for playlist: {spotify_output_dir}")
        except Exception as e:
            logger.error(f"Failed to create output directory: {e}")
            yield {
                "status": "error",
                "details": {"message": f"Failed to create output directory: {str(e)}"}
            }
            return
        
        # Detect if it's a playlist or a track
        is_playlist = "playlist" in url.lower()

        # Get quality from quality parameter
        quality_setting = quality or "high"
        
        # Use the URL to extract the track or playlist ID
        spotify_id = self._extract_spotify_id(url)
        
        # For playlists, create a dedicated directory
        if is_playlist:
            # Create a dedicated output directory for this playlist
            output_dir = str(spotify_output_dir)
            output_template = str(spotify_output_dir / f"%(title)s_{self.task_id}.%(ext)s")
            
            # Log the playlist download
            logger.info(f"Downloading Spotify playlist: {url} to {output_dir}")
            yield {"status": "processing", "progress": 0, "detail": f"Starting download of Spotify playlist to {output_dir}"}
        else:
            # For single track
            output_template = str(spotify_output_dir / f"track_%(title)s.%(ext)s")
            logger.info(f"Downloading Spotify track: {url} to {output_template}")
            yield {"status": "processing", "progress": 0, "detail": f"Starting download of Spotify track to {output_template}"}
        
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
                
                # Extract spotify ID for directory organization
                spotify_id = self._extract_spotify_id(url) or 'unknown'
                
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
            
            # Create a dedicated output directory
            spotify_output_dir = os.path.join("/opt/render/project/src/server/downloads", f"spotify_{spotify_id}_{self.task_id}")
            os.makedirs(spotify_output_dir, exist_ok=True)
            logger.info(f"Using output directory: {spotify_output_dir}")
            
            # DIRECT APPROACH: Process tracks directly with yt-dlp
            successful_tracks = []
            
            # Process each track in the playlist
            for i, track in enumerate(tracks):
                track_name = track.get('name', 'Unknown Track')
                artists = track.get('artists', ['Unknown Artist'])
                if isinstance(artists, list):
                    artist_str = ', '.join(artists)
                else:
                    artist_str = str(artists)
                
                # Create search query
                search_query = f"{track_name} {artist_str} audio"
                
                # Create safe filename
                safe_name = re.sub(r'[^\w\-\.]', '_', f"{artist_str} - {track_name}")
                if len(safe_name) > 100:
                    safe_name = safe_name[:100]
                
                track_path = os.path.join(spotify_output_dir, f"{safe_name}.mp3")
                
                # Update progress
                current_progress = 10 + (i * 80 / track_count)
                yield {
                    'status': 'downloading',
                    'progress': current_progress,
                    'details': f"[{i+1}/{track_count}] Downloading: {track_name} by {artist_str}"
                }
                
                logger.info(f"Downloading track {i+1}/{track_count}: {track_name} by {artist_str}")
                
                try:
                    # Check for YouTube cookies file in multiple locations
                    scripts_cookies_path = self.cookies_path if hasattr(self, 'cookies_path') else None
                    repo_cookies_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "youtube.cookies")
                    render_cookies_path = "/etc/secrets/youtube.cookies"
                    
                    # Try scripts directory first, then Render secrets, then repo location
                    if scripts_cookies_path and os.path.exists(scripts_cookies_path):
                        cookies_path = scripts_cookies_path
                        logger.info(f"Using YouTube cookies from scripts directory: {cookies_path}")
                    elif os.path.exists(render_cookies_path):
                        cookies_path = render_cookies_path
                        logger.info(f"Using YouTube cookies from Render secrets: {cookies_path}")
                    elif os.path.exists(repo_cookies_path):
                        cookies_path = repo_cookies_path
                        logger.info(f"Using YouTube cookies from repository: {cookies_path}")
                    else:
                        cookies_path = None
                        logger.warning("YouTube cookies file not found. Download may fail due to bot detection.")
                    
                    cmd = [
                        "yt-dlp",
                        f"ytsearch1:{search_query}",
                        "-x", "--audio-format", "mp3",
                        "--audio-quality", "192" if quality_setting != "high" else "320",
                        "-o", track_path,
                        "--no-playlist",
                    ]
                    
                    # Add cookies option if available
                    if cookies_path:
                        cmd.extend(["--cookies", cookies_path])
                        # Add additional options that help avoid bot detection
                        cmd.extend([
                            "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                            "--socket-timeout", "60",
                            "--retry-sleep", "3",
                            "--max-retries", "5",
                            "--geo-bypass"
                        ])
                    
                    logger.info(f"Running yt-dlp command: {' '.join(cmd)}")
                    
                    process = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    
                    stdout, stderr = await process.communicate()
                    
                    if process.returncode == 0:
                        logger.info(f"Successfully downloaded track: {track_path}")
                        successful_tracks.append(track_path)
                    else:
                        logger.error(f"Failed to download track: {stderr.decode()}")
                except Exception as track_error:
                    logger.error(f"Error downloading track: {track_error}")
            
            # Create ZIP file with downloaded tracks
            if successful_tracks:
                zip_path = os.path.join("/opt/render/project/src/server/downloads", f"spotify_playlist_{spotify_id}_{self.task_id}.zip")
                
                yield {
                    'status': 'processing',
                    'progress': 90,
                    'details': f"Creating ZIP file with {len(successful_tracks)}/{track_count} tracks..."
                }
                
                try:
                    with zipfile.ZipFile(zip_path, 'w') as zipf:
                        for track_file in successful_tracks:
                            zipf.write(track_file, os.path.basename(track_file))
                
                    logger.info(f"Created ZIP file at {zip_path}")
                    
                    yield {
                        'status': 'complete',
                        'progress': 100,
                        'details': f"Downloaded {len(successful_tracks)}/{track_count} tracks. ZIP file created.",
                        'output_path': zip_path
                    }
                    return
                except Exception as zip_error:
                    logger.error(f"Error creating ZIP file: {zip_error}")
                    yield {
                        'status': 'error',
                        'error': f"Error creating ZIP file: {str(zip_error)}"
                    }
                    return
            else:
                logger.error("No tracks were successfully downloaded")
                yield {
                    'status': 'error',
                    'error': "Failed to download any tracks from the playlist"
                }
                return
                
        except Exception as e:
            logger.error(f"Error processing track information: {e}", exc_info=True)
            yield {
                'status': 'error',
                'error': f"Error processing track information: {str(e)}"
            }
            return
        
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
        
        # Use the pre-defined downloads directory for consistent file access
        base_dir = self.downloads_dir
        
        if playlist_id:
            # For playlists, create a dedicated directory
            output_dir = os.path.join(base_dir, f"spotify_playlist_{playlist_id}_{self.task_id}")
            os.makedirs(output_dir, exist_ok=True)
            logger.info(f"Created dedicated output directory for playlist: {output_dir}")
            
            # Create an output path for each track within the playlist directory
            filename = f"{track_id}.%(ext)s"
            output_path = os.path.join(output_dir, filename)
        else:
            # For single tracks, use a direct path
            filename = f"spotify_track_{track_id}_{self.task_id}.%(ext)s"
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
            
            # Generate output paths
            try:
                output_path, _ = self.generate_output_paths(options)
                logger.info(f"Generated output path: {output_path}")
            except Exception as path_error:
                logger.error(f"Error generating output paths: {path_error}", exc_info=True)
                yield {"status": "error", "error": f"Failed to generate output paths: {str(path_error)}"}
                return
            
            # Execute download
            try:
                async for update in self.download(task.url, output_path, options.get("quality")):
                    yield update
            except Exception as download_error:
                logger.error(f"Error during download: {download_error}", exc_info=True)
                yield {"status": "error", "error": f"Download failed: {str(download_error)}"}
                
        except Exception as e:
            logger.error(f"Error in Spotify strategy: {e}", exc_info=True)
            yield {"status": "error", "error": f"Spotify strategy error: {str(e)}"} 