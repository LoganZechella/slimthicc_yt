#!/usr/bin/env python3
import os
import sys
import json
import base64
import requests
import time
import re
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup

class SpotifyTrackExtractor:
    def __init__(self, client_id=None, client_secret=None):
        """Initialize with optional Spotify API credentials."""
        self.client_id = client_id or os.environ.get('SPOTIFY_CLIENT_ID')
        self.client_secret = client_secret or os.environ.get('SPOTIFY_CLIENT_SECRET')
        self.access_token = None
        self.token_expiry = 0
        
    def get_access_token(self):
        """Get Spotify API access token using client credentials flow."""
        if not self.client_id or not self.client_secret:
            print("Warning: Spotify API credentials not provided. Only track IDs will be extracted.")
            return None
            
        if self.access_token and time.time() < self.token_expiry:
            return self.access_token
            
        auth_string = f"{self.client_id}:{self.client_secret}"
        auth_bytes = auth_string.encode('utf-8')
        auth_base64 = base64.b64encode(auth_bytes).decode('utf-8')
        
        url = "https://accounts.spotify.com/api/token"
        headers = {
            "Authorization": f"Basic {auth_base64}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {"grant_type": "client_credentials"}
        
        try:
            response = requests.post(url, headers=headers, data=data)
            response.raise_for_status()
            json_result = response.json()
            self.access_token = json_result["access_token"]
            self.token_expiry = time.time() + json_result["expires_in"] - 60  # Buffer of 60 seconds
            return self.access_token
        except Exception as e:
            print(f"Error getting Spotify access token: {e}")
            return None
    
    def fetch_playlist_page(self, playlist_url):
        """Fetch the HTML content of a Spotify playlist page."""
        # Add nd=1 parameter to force web view
        if '?' in playlist_url:
            if 'nd=1' not in playlist_url:
                playlist_url += '&nd=1'
        else:
            playlist_url += '?nd=1'
            
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://open.spotify.com/',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        }
        
        try:
            print(f"Fetching playlist page: {playlist_url}")
            response = requests.get(playlist_url, headers=headers, allow_redirects=True)
            response.raise_for_status()
            print(f"Successfully fetched playlist page ({len(response.text)} bytes)")
            
            # Save HTML content for debugging
            with open('spotify_playlist_page.html', 'w', encoding='utf-8') as f:
                f.write(response.text)
                
            return response.text
        except Exception as e:
            print(f"Error fetching playlist page: {e}")
            return None
    
    def extract_track_ids_from_html(self, html_content):
        """Extract track IDs from Spotify playlist HTML content using meta tags."""
        if not html_content:
            return []
            
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Find all music:song meta tags
        track_meta_tags = soup.find_all('meta', attrs={'name': 'music:song'})
        
        track_ids = []
        for tag in track_meta_tags:
            track_url = tag.get('content', '')
            # Extract track ID from URL
            parsed_url = urlparse(track_url)
            path_parts = parsed_url.path.split('/')
            if len(path_parts) > 2 and path_parts[1] == 'track':
                track_id = path_parts[2]
                track_ids.append(track_id)
        
        return track_ids
    
    def get_playlist_title_from_html(self, html_content):
        """Extract playlist title from HTML content."""
        if not html_content:
            return "Unknown Playlist"
            
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Find the title meta tag
        title_tag = soup.find('meta', property='og:title')
        if title_tag:
            return title_tag.get('content', 'Unknown Playlist')
        
        # Fallback to title tag
        title_tag = soup.find('title')
        if title_tag and title_tag.string:
            # Extract playlist name from title like "Playlist Name - playlist by username | Spotify"
            title_text = title_tag.string
            if ' - ' in title_text and ' | Spotify' in title_text:
                return title_text.split(' - ')[0].strip()
        
        return 'Unknown Playlist'
    
    def get_track_info_from_api(self, track_id):
        """Get detailed track information from Spotify API."""
        if not track_id:
            return None
            
        token = self.get_access_token()
        if not token:
            # Return basic info if no API access
            return {
                "id": track_id,
                "url": f"https://open.spotify.com/track/{track_id}"
            }
            
        url = f"https://api.spotify.com/v1/tracks/{track_id}"
        headers = {"Authorization": f"Bearer {token}"}
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            track_data = response.json()
            
            # Extract relevant information
            artists = [artist["name"] for artist in track_data.get("artists", [])]
            
            return {
                "id": track_id,
                "name": track_data.get("name", "Unknown"),
                "artists": artists,
                "album": track_data.get("album", {}).get("name", "Unknown"),
                "duration_ms": track_data.get("duration_ms", 0),
                "url": f"https://open.spotify.com/track/{track_id}",
                "preview_url": track_data.get("preview_url")
            }
        except Exception as e:
            print(f"Error getting track info for {track_id}: {e}")
            # Return basic info on error
            return {
                "id": track_id,
                "url": f"https://open.spotify.com/track/{track_id}"
            }
    
    def extract_playlist_id_from_url(self, playlist_url):
        """Extract playlist ID from Spotify playlist URL."""
        parsed_url = urlparse(playlist_url)
        path_parts = parsed_url.path.split('/')
        
        if len(path_parts) > 2 and path_parts[1] == 'playlist':
            return path_parts[2]
        return None
    
    def get_tracks_from_playlist_api(self, playlist_id):
        """Get tracks directly from Spotify API (requires authentication)."""
        if not playlist_id:
            return []
            
        token = self.get_access_token()
        if not token:
            print("Cannot get tracks from API without authentication.")
            return []
            
        tracks = []
        url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"
        headers = {"Authorization": f"Bearer {token}"}
        
        try:
            while url:
                response = requests.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
                
                for item in data.get("items", []):
                    track = item.get("track")
                    if track:
                        track_id = track.get("id")
                        if track_id:
                            tracks.append(self.get_track_info_from_api(track_id))
                
                # Get next page if available
                url = data.get("next")
                
            return tracks
        except Exception as e:
            print(f"Error getting tracks from API: {e}")
            return []
    
    def get_tracks_from_playlist(self, playlist_url):
        """Get tracks from a Spotify playlist using either API or HTML scraping."""
        playlist_id = self.extract_playlist_id_from_url(playlist_url)
        
        # Try API method first if credentials are available
        if self.client_id and self.client_secret and playlist_id:
            print(f"Attempting to get tracks via Spotify API for playlist: {playlist_id}")
            tracks = self.get_tracks_from_playlist_api(playlist_id)
            if tracks:
                return tracks, playlist_id
        
        # Fallback to HTML scraping
        html_content = self.fetch_playlist_page(playlist_url)
        playlist_title = self.get_playlist_title_from_html(html_content)
        track_ids = self.extract_track_ids_from_html(html_content)
        
        print(f"Found {len(track_ids)} tracks in playlist: {playlist_title}")
        
        tracks = []
        for track_id in track_ids:
            track_info = self.get_track_info_from_api(track_id)
            if track_info:
                tracks.append(track_info)
                
        return tracks, playlist_title

def main():
    if len(sys.argv) != 2:
        print("Usage: ./spotify_track_extractor.py <spotify_playlist_url>")
        sys.exit(1)
    
    playlist_url = sys.argv[1]
    
    # Check if URL is a valid Spotify playlist URL
    if not re.match(r'https?://open\.spotify\.com/playlist/[a-zA-Z0-9]+', playlist_url):
        print("Error: Invalid Spotify playlist URL")
        sys.exit(1)
    
    # Get Spotify API credentials from environment variables
    client_id = os.environ.get('SPOTIFY_CLIENT_ID')
    client_secret = os.environ.get('SPOTIFY_CLIENT_SECRET')
    
    if not client_id or not client_secret:
        print("Warning: SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET environment variables not set.")
        print("Only basic track information will be available.")
    
    extractor = SpotifyTrackExtractor(client_id, client_secret)
    tracks, playlist_info = extractor.get_tracks_from_playlist(playlist_url)
    
    if not tracks:
        print("Error: No tracks found in the playlist")
        sys.exit(1)
    
    # Create a safe filename
    safe_name = re.sub(r'[^\w\s-]', '', playlist_info).strip().replace(' ', '_')
    output_file = f"{safe_name}_tracks.json"
    
    # Save tracks to JSON file
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(tracks, f, indent=2)
    
    print(f"\nExtracted {len(tracks)} tracks from playlist: {playlist_info}")
    print(f"Track information saved to {output_file}")
    
    # Print track list
    print("\nTrack List:")
    for i, track in enumerate(tracks, 1):
        artists = ", ".join(track.get("artists", ["Unknown Artist"]))
        name = track.get("name", "Unknown Track")
        print(f"{i}. {name} - {artists}")

if __name__ == "__main__":
    main() 