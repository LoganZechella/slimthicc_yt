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
        logger.info(f"Initialized downloader with output directory: {self.output_dir}")
        
        # Verify yt-dlp is installed
        try:
            subprocess.run(["yt-dlp", "--version"], capture_output=True, check=True)
            logger.info("yt-dlp is installed and working")
        except (subprocess.SubprocessError, FileNotFoundError):
            logger.error("yt-dlp is not installed or not working properly. Please install it with: pip install yt-dlp")
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
            log_file_path = self.temp_dir / "download.log"
            with open(log_file_path, 'a') as log_file:
                log_file.write(f"\n\n--- Download attempt for {name} - {artist_str} at {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
                log_file.write(f"Command: {' '.join(cmd)}\n\n")
                
                # Run yt-dlp with output piped to both console and log file
                process = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                
                # Log the output and error
                if process.stdout:
                    log_file.write(f"STDOUT:\n{process.stdout}\n")
                if process.stderr:
                    log_file.write(f"STDERR:\n{process.stderr}\n")
            
            # Log the result
            if process.returncode == 0:
                logger.info(f"Successfully downloaded: {name} - {artist_str}")
                return True, str(output_path)
            else:
                logger.error(f"Failed to download: {name} - {artist_str}")
                if process.stderr:
                    # Print the error to console logs for immediate debugging
                    logger.error(f"Error output: {process.stderr}")
                logger.error(f"Check {log_file_path} for detailed logs")
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
            
            # Add a small delay between downloads to avoid rate limiting
            if i < len(tracks_to_download):
                time.sleep(1)
            
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