import os
import urllib.parse
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

def get_spotify_client():
    """Initialize and return a Spotify client using environment variables for authentication."""
    client_id = os.getenv("SPOTIPY_CLIENT_ID")
    client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise Exception("Spotify API credentials are not set. Please set SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET environment variables.")
    auth_manager = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
    return spotipy.Spotify(auth_manager=auth_manager)

def extract_playlist_id(playlist_url):
    """Extract the playlist ID from a Spotify playlist URL."""
    # Handle various Spotify URL formats
    parsed = urllib.parse.urlparse(playlist_url)
    parts = parsed.path.split('/')
    if len(parts) >= 3 and parts[1] == 'playlist':
        # Remove any query parameters
        return parts[2].split('?')[0]
    raise ValueError("Invalid Spotify playlist URL. Please provide a valid Spotify playlist URL.")

def get_spotify_playlist_tracks(playlist_url):
    """
    Retrieve all tracks from a Spotify playlist.
    
    Returns:
    List of dictionaries, each containing:
        - 'query': Search string optimized for YouTube search
        - 'title': Display title for the track
    """
    sp = get_spotify_client()
    playlist_id = extract_playlist_id(playlist_url)
    
    tracks = []
    offset = 0
    limit = 100  # Spotify API limit per request
    
    while True:
        results = sp.playlist_items(
            playlist_id,
            offset=offset,
            limit=limit,
            fields='items.track(name,artists.name),total'
        )
        
        if not results['items']:
            break
            
        for item in results['items']:
            track = item.get('track')
            if not track:  # Skip unavailable tracks
                continue
                
            track_name = track.get('name', '').strip()
            artists = [artist.get('name', '').strip() for artist in track.get('artists', [])]
            artist_string = ", ".join(filter(None, artists))
            
            if not track_name or not artist_string:  # Skip tracks with missing data
                continue
                
            # Create a search query optimized for finding the official audio version
            query = f"{artist_string} - {track_name} official audio explicit"
            display_title = f"{track_name} by {artist_string}"
            
            tracks.append({
                'query': query,
                'title': display_title
            })
        
        offset += limit
        if offset >= results.get('total', 0):
            break
    
    return tracks 