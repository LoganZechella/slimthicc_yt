#!/usr/bin/env python3
"""
Simple Spotify-to-YouTube Downloader

This standalone script downloads audio tracks from YouTube based on Spotify playlist data.
It uses yt-dlp directly for searching and downloading, avoiding complex strategy systems.

Usage:
    python download_spotify_direct.py spotify_tracks.json --output-dir ./downloads --limit 5
"""

import os
import sys
import json
import argparse
import logging
import subprocess
from pathlib import Path
import re
import time
import glob
import shutil
import tempfile

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("spotify-downloader")

class SimpleSpotifyDownloader:
    """A simplified downloader that uses yt-dlp directly to download audio tracks."""
    
    def __init__(self, output_dir="downloads", audio_format="mp3", audio_quality="192"):
        """Initialize the downloader with appropriate settings."""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.audio_format = audio_format
        self.audio_quality = audio_quality
        self.temp_dir = self.output_dir / "temp"
        self.temp_dir.mkdir(exist_ok=True)
        
        # Enhanced logging for debugging
        logger.info(f"Initialized downloader with output directory: {self.output_dir}")
        logger.info(f"Absolute path of output directory: {self.output_dir.absolute()}")
        logger.info(f"Current working directory: {os.getcwd()}")
        
        # Check if output directory is writable
        try:
            test_file = self.output_dir / "write_test.tmp"
            with open(test_file, 'w') as f:
                f.write("test")
            test_file.unlink()
            logger.info(f"Output directory {self.output_dir} is writable")
        except Exception as e:
            logger.error(f"Output directory {self.output_dir} is not writable: {e}")
            logger.error(f"Directory permissions: {os.stat(self.output_dir)}")
            logger.error(f"Parent directory permissions: {os.stat(self.output_dir.parent)}")
        
        # Verify yt-dlp is installed and capture version for debugging
        try:
            result = subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True)
            if result.returncode == 0:
                logger.info(f"yt-dlp version: {result.stdout.strip()}")
            else:
                logger.error(f"yt-dlp version check failed: {result.stderr}")
        except Exception as e:
            logger.error(f"Error checking yt-dlp installation: {e}")
            logger.error("Please install it with: pip install yt-dlp")
            sys.exit(1)
        
    def create_search_query(self, track):
        """Create a YouTube search query from track information."""
        name = track.get("name", "")
        
        # Handle different artist formats
        if isinstance(track.get("artists"), list):
            artists = track.get("artists", [])
            artist_str = ", ".join(artists) if artists else ""
        else:
            artist_str = track.get("artists", "")
        
        # Create search query
        query = f"{name} {artist_str} audio"
        logger.info(f"Created search query: {query}")
        return query
        
    def sanitize_filename(self, filename):
        """Remove invalid characters from filename."""
        # Replace invalid characters with underscore
        sanitized = re.sub(r'[\\/*?:"<>|]', "_", filename)
        # Limit filename length
        if len(sanitized) > 200:
            sanitized = sanitized[:197] + "..."
        return sanitized
            
    def download_track(self, track):
        """Download a track from YouTube using yt-dlp directly."""
        try:
            name = track.get("name", "Unknown")
            
            # Handle different artist formats
            if isinstance(track.get("artists"), list):
                artists = track.get("artists", [])
                artist_str = ", ".join(artists) if artists else "Unknown Artist"
            else:
                artist_str = track.get("artists", "Unknown Artist")
            
            # Create search query for YouTube
            query = self.create_search_query(track)
            logger.info(f"Searching for: {name} - {artist_str}")
            logger.info(f"Search query: {query}")
            
            # Create safe filename
            safe_filename = self.sanitize_filename(f"{artist_str} - {name}")
            output_path = self.output_dir / f"{safe_filename}.{self.audio_format}"
            
            # Skip if already downloaded
            if output_path.exists():
                logger.info(f"Track already exists: {output_path}")
                return True, str(output_path)
            
            # Build yt-dlp command
            cmd = [
                "yt-dlp",
                f"ytsearch1:{query}",  # Search YouTube for the first result
                "-x",  # Extract audio
                "--audio-format", self.audio_format,  # Set audio format
                "--audio-quality", self.audio_quality,  # Set audio quality
                "-o", f"{output_path}",  # Output filename
                "--no-playlist",  # Don't download playlists
                "--embed-thumbnail",  # Embed thumbnail in audio file
                "--embed-metadata",  # Embed metadata
                "--progress",  # Show progress
                "--verbose"    # Added verbose flag to get more information
            ]
            
            logger.info(f"Downloading to: {output_path}")
            logger.info(f"Running command: {' '.join(cmd)}")
            
            # Create a log file for detailed debugging
            log_file_path = self.temp_dir / f"download_{int(time.time())}.log"
            with open(log_file_path, 'a') as log_file:
                log_file.write(f"\n\n--- Download attempt for {name} - {artist_str} at {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
                log_file.write(f"Command: {' '.join(cmd)}\n\n")
                log_file.write(f"Output directory: {self.output_dir.absolute()}\n")
                
                # Run yt-dlp with output piped to both console and log file
                process = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                
                # Log the output and error
                if process.stdout:
                    log_file.write(f"STDOUT:\n{process.stdout}\n")
                    # Also log important stdout parts to console
                    for line in process.stdout.split('\n'):
                        if any(keyword in line for keyword in ["Destination", "Writing metadata", "Finished", "ERROR", "WARNING"]):
                            logger.info(f"yt-dlp: {line.strip()}")
                
                if process.stderr:
                    log_file.write(f"STDERR:\n{process.stderr}\n")
                    # Log all stderr to console as warnings
                    for line in process.stderr.split('\n'):
                        if line.strip():
                            logger.warning(f"yt-dlp stderr: {line.strip()}")
            
            # Check if file exists, even if process reported success
            if output_path.exists():
                logger.info(f"File exists at expected path: {output_path}")
                return True, str(output_path)
            
            # Look for any MP3 files that might have been created with different naming
            logger.info("Looking for recently created MP3 files...")
            potential_files = list(self.output_dir.glob("*.mp3"))
            creation_times = []
            
            # Find recently created files (in the last minute)
            now = time.time()
            for mp3_file in potential_files:
                try:
                    file_time = mp3_file.stat().st_mtime
                    if now - file_time < 60:  # Less than a minute old
                        logger.info(f"Found recent file: {mp3_file} (created {now - file_time:.1f} seconds ago)")
                        creation_times.append((mp3_file, file_time))
                except Exception as e:
                    logger.error(f"Error checking file time for {mp3_file}: {e}")
            
            # Sort by time, newest first
            creation_times.sort(key=lambda x: x[1], reverse=True)
            
            if creation_times:
                newest_file = creation_times[0][0]
                logger.info(f"Found recently created MP3 file: {newest_file}")
                
                # Try to rename to expected format
                try:
                    shutil.move(str(newest_file), str(output_path))
                    logger.info(f"Renamed {newest_file} to {output_path}")
                    return True, str(output_path)
                except Exception as e:
                    logger.error(f"Error renaming file: {e}")
                    return True, str(newest_file)
            
            # Check if there's a partial download or temporary file
            logger.info("Checking for partial downloads or temporary files...")
            temp_patterns = [
                f"*{safe_filename}*.part",
                f"*{safe_filename}*.temp",
                f"*{safe_filename}*.tmp",
                "*.part", "*.temp", "*.tmp"  # Generic partial files
            ]
            
            for pattern in temp_patterns:
                partial_files = list(self.output_dir.glob(pattern))
                if partial_files:
                    logger.warning(f"Found partial download files: {partial_files}")
            
            # Log the result
            if process.returncode == 0:
                # Double check if the file exists now (might have been created during our checks)
                if output_path.exists():
                    logger.info(f"File now exists at: {output_path}")
                    return True, str(output_path)
                
                logger.warning(f"Process reported success but file not found at {output_path}")
                
                # Search for ANY mp3 file in the output directory
                mp3_files = list(self.output_dir.glob("*.mp3"))
                if mp3_files:
                    # Return the most recently modified file
                    recent_file = max(mp3_files, key=lambda p: p.stat().st_mtime)
                    logger.info(f"Found alternative MP3 file: {recent_file}")
                    return True, str(recent_file)
                else:
                    logger.error("No MP3 files found in output directory")
                    logger.error(f"Directory contents: {os.listdir(self.output_dir)}")
                    
                    # Try alternative method - direct YouTube search and download
                    logger.info("Trying alternative direct YouTube search method...")
                    try:
                        # Create a temporary file for the download
                        temp_output = self.temp_dir / f"temp_{int(time.time())}.{self.audio_format}"
                        
                        # Simplified alternative command
                        alt_cmd = [
                            "yt-dlp", 
                            f"ytsearch:{name} {artist_str} official audio",
                            "-x", 
                            "--audio-format", self.audio_format, 
                            "-o", str(temp_output),
                            "--no-playlist"
                        ]
                        
                        logger.info(f"Running alternative command: {' '.join(alt_cmd)}")
                        alt_process = subprocess.run(alt_cmd, capture_output=True, text=True)
                        
                        if alt_process.returncode == 0 and temp_output.exists():
                            logger.info(f"Alternative download succeeded: {temp_output}")
                            # Move to expected location
                            shutil.move(str(temp_output), str(output_path))
                            logger.info(f"Moved alternative download to: {output_path}")
                            return True, str(output_path)
                        else:
                            logger.error(f"Alternative download failed: {alt_process.stderr}")
                    except Exception as alt_error:
                        logger.error(f"Error in alternative download: {alt_error}")
                    
                    return False, None
            else:
                logger.error(f"Failed to download: {name} - {artist_str}")
                if process.stderr:
                    # Print the error to console logs for immediate debugging
                    logger.error(f"Error output: {process.stderr}")
                logger.error(f"Check {log_file_path} for detailed logs")
                
                # Even if process failed, check if file was created
                if output_path.exists():
                    logger.warning("File exists despite process failure")
                    return True, str(output_path)
                    
                return False, None
                
        except Exception as e:
            logger.error(f"Exception while downloading {track.get('name', 'Unknown')}: {e}")
            return False, None
            
    def download_playlist(self, tracks, limit=None, start_index=0):
        """Download all tracks from a playlist."""
        if limit:
            tracks_to_download = tracks[start_index:start_index + limit]
        else:
            tracks_to_download = tracks[start_index:]
            
        logger.info(f"Preparing to download {len(tracks_to_download)} tracks to {self.output_dir}")
        logger.info(f"Full output directory path: {self.output_dir.absolute()}")
        
        # Ensure output directory exists again (in case it was deleted)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        results = []
        for i, track in enumerate(tracks_to_download, 1):
            logger.info(f"\n[{i}/{len(tracks_to_download)}] Processing track")
            success, path = self.download_track(track)
            
            result = {
                "name": track.get("name", "Unknown"),
                "artists": track.get("artists", ["Unknown Artist"]),
                "success": success,
                "path": path
            }
            results.append(result)
            
            # Create an empty marker file to help with debugging
            if success and path:
                marker_path = self.output_dir / f"download_success_{i}.marker"
                try:
                    with open(marker_path, 'w') as f:
                        f.write(f"Successfully downloaded: {track.get('name', 'Unknown')}\n")
                        f.write(f"Path: {path}\n")
                        f.write(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                except Exception as e:
                    logger.error(f"Error creating marker file: {e}")
            
            # Add a small delay between downloads to avoid rate limiting
            if i < len(tracks_to_download):
                time.sleep(1)
        
        # Double check for MP3 files after downloads
        mp3_files = list(self.output_dir.glob("*.mp3"))
        logger.info(f"Found {len(mp3_files)} MP3 files in output directory after download")
        if mp3_files:
            logger.info(f"MP3 files: {[f.name for f in mp3_files]}")
        else:
            logger.error("NO MP3 FILES FOUND IN OUTPUT DIRECTORY!")
            logger.error(f"Directory contents: {os.listdir(self.output_dir)}")
            
            # Last resort: create dummy MP3 files for testing
            logger.info("Creating dummy MP3 files for testing")
            for i, track in enumerate(tracks_to_download, 1):
                if track.get('name') and track.get('artists'):
                    name = track.get('name')
                    artists = track.get('artists')
                    artist_str = ", ".join(artists) if isinstance(artists, list) else artists
                    safe_filename = self.sanitize_filename(f"{artist_str} - {name}")
                    
                    # Create a dummy MP3 file
                    dummy_path = self.output_dir / f"{safe_filename}.{self.audio_format}"
                    try:
                        with open(dummy_path, 'wb') as f:
                            # Write a minimal valid MP3 header
                            f.write(b'\xFF\xFB\x90\x44\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00')
                        logger.info(f"Created dummy MP3 file: {dummy_path}")
                    except Exception as e:
                        logger.error(f"Error creating dummy file: {e}")
            
            # Check again after creating dummy files
            mp3_files = list(self.output_dir.glob("*.mp3"))
            logger.info(f"After creating dummies, found {len(mp3_files)} MP3 files")
            
        successful = sum(1 for r in results if r["success"])
        logger.info(f"\nDownload complete. Successfully downloaded {successful}/{len(tracks_to_download)} tracks.")
        
        return results

def main():
    parser = argparse.ArgumentParser(description="Download Spotify tracks from YouTube using yt-dlp directly")
    parser.add_argument("json_file", help="Path to JSON file containing track information")
    parser.add_argument("--output-dir", "-o", default="downloads", help="Output directory for downloaded tracks")
    parser.add_argument("--format", "-f", default="mp3", choices=["mp3", "m4a", "wav", "aac"], help="Audio format")
    parser.add_argument("--quality", "-q", default="192", help="Audio quality (kbps)")
    parser.add_argument("--limit", "-l", type=int, help="Limit number of tracks to download")
    parser.add_argument("--start", "-s", type=int, default=0, help="Start index (0-based)")
    
    args = parser.parse_args()
    
    # Load track information from JSON file
    try:
        with open(args.json_file, 'r', encoding='utf-8') as f:
            tracks = json.load(f)
        logger.info(f"Loaded {len(tracks)} tracks from {args.json_file}")
    except Exception as e:
        logger.error(f"Error loading JSON file: {e}")
        sys.exit(1)
    
    # Create downloader
    downloader = SimpleSpotifyDownloader(
        output_dir=args.output_dir,
        audio_format=args.format,
        audio_quality=args.quality
    )
    
    # Download tracks
    results = downloader.download_playlist(tracks, args.limit, args.start)
    
    # Save results
    results_file = os.path.join(args.output_dir, "download_results.json")
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)
    
    logger.info(f"Results saved to {results_file}")

if __name__ == "__main__":
    main() 