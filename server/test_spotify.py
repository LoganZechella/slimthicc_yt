#!/usr/bin/env python3
"""
Test script for Spotify integration
This script tests the Spotify client initialization and URL validation
without going through the full web API.
"""

import os
import sys
import asyncio
import logging
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyClientCredentials
import spotipy

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("spotify-test")

# Load environment variables
load_dotenv()
logger.info("Loaded environment variables")

def print_separator(title):
    """Print a separator with a title."""
    print("\n" + "=" * 80)
    print(f" {title} ".center(80, "="))
    print("=" * 80 + "\n")

async def main():
    print_separator("SPOTIFY INTEGRATION TEST")
    
    # Check environment variables
    print_separator("Environment Variables")
    spotify_client_id = os.getenv("SPOTIFY_CLIENT_ID")
    spotify_client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    spotipy_client_id = os.getenv("SPOTIPY_CLIENT_ID")
    spotipy_client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")
    
    print(f"SPOTIFY_CLIENT_ID: {'Set' if spotify_client_id else 'Not set'}")
    print(f"SPOTIFY_CLIENT_SECRET: {'Set' if spotify_client_secret else 'Not set'}")
    print(f"SPOTIPY_CLIENT_ID: {'Set' if spotipy_client_id else 'Not set'}")
    print(f"SPOTIPY_CLIENT_SECRET: {'Set' if spotipy_client_secret else 'Not set'}")
    
    # Try to initialize Spotify client
    print_separator("Spotify Client Initialization")
    client_id = spotify_client_id or spotipy_client_id
    client_secret = spotify_client_secret or spotipy_client_secret
    
    if not client_id or not client_secret:
        print("ERROR: Spotify credentials not set. Please set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET")
        return
    
    print(f"Using client ID: {client_id[:4]}...{client_id[-4:]}")
    print(f"Using client secret: {client_secret[:4]}...{client_secret[-4:]}")
    
    try:
        auth_manager = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
        spotify = spotipy.Spotify(auth_manager=auth_manager)
        print("SUCCESS: Spotify client initialized")
        
        # Try to make a simple API call
        print_separator("Testing API Call")
        try:
            # Get a featured playlist
            results = spotify.featured_playlists(limit=1)
            playlist = results['playlists']['items'][0]
            print(f"SUCCESS: API call worked. Sample playlist: {playlist['name']}")
        except Exception as e:
            print(f"ERROR: API call failed: {e}")
    
        # Test URL validation
        print_separator("Testing URL Validation")
        test_urls = [
            "https://open.spotify.com/track/11dFghVXANMlKmJXsNCbNl",  # Carly Rae Jepsen - Cut To The Feeling
            "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M",  # Today's Top Hits playlist
            "https://open.spotify.com/playlist/37i9dQZEVXbMDoHDwVN2tF",  # Global Top 50
            "spotify:track:11dFghVXANMlKmJXsNCbNl",
            "spotify:playlist:37i9dQZF1DXcBWIGoYBM5M",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",  # Not a Spotify URL
            "https://soundcloud.com/rick-astley-official/never-gonna-give-you-up-7",  # Not a Spotify URL
        ]
        
        for url in test_urls:
            print(f"\nTesting URL: {url}")
            # Basic pattern matching
            is_spotify = False
            if 'spotify.com' in url or url.startswith('spotify:'):
                is_spotify = True
                print(f"URL matches Spotify pattern: {is_spotify}")
            
            # If it's a Spotify URL, try to extract the ID
            if is_spotify:
                try:
                    # Extract ID using similar logic to our SpotifyStrategy
                    spotify_id = None
                    if 'open.spotify.com' in url:
                        path_parts = url.split('/')
                        if len(path_parts) >= 5:  # https://open.spotify.com/track/ID
                            spotify_id = path_parts[4].split('?')[0]
                    elif url.startswith('spotify:'):
                        parts = url.split(':')
                        if len(parts) >= 3:
                            spotify_id = parts[2]
                    
                    if spotify_id:
                        print(f"Extracted ID: {spotify_id}")
                        
                        # Test if it's a valid ID by making an API call
                        if 'track' in url:
                            try:
                                track = spotify.track(spotify_id)
                                print(f"VALID TRACK: {track['name']} by {', '.join([a['name'] for a in track['artists']])}")
                            except Exception as e:
                                print(f"INVALID TRACK ID: {e}")
                        elif 'playlist' in url:
                            try:
                                playlist = spotify.playlist(spotify_id)
                                print(f"VALID PLAYLIST: {playlist['name']} ({playlist['tracks']['total']} tracks)")
                            except Exception as e:
                                print(f"INVALID PLAYLIST ID: {e}")
                    else:
                        print("Could not extract Spotify ID")
                except Exception as e:
                    print(f"Error processing URL: {e}")
            else:
                print("Not a Spotify URL")
    except Exception as e:
        print(f"ERROR: Failed to initialize Spotify client: {e}")
    
    print_separator("TEST COMPLETE")

if __name__ == "__main__":
    asyncio.run(main()) 