#!/usr/bin/env python3
"""
Simple test script for Spotify playlist scraping without using the API
"""

import os
import sys
import asyncio
import logging
import json
from bs4 import BeautifulSoup
import aiohttp
import re

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("spotify-scraper")

def print_separator(title):
    """Print a separator with a title."""
    print("\n" + "=" * 80)
    print(f" {title} ".center(80, "="))
    print("=" * 80 + "\n")

async def get_playlist_tracks(url):
    """Scrape tracks from a Spotify playlist."""
    print(f"Scraping playlist: {url}")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url) as response:
            if response.status != 200:
                print(f"Error: Failed to fetch page (status code: {response.status})")
                return []
                
            html = await response.text()
            
    # Save HTML content for debugging
    with open("spotify_playlist_page.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("Saved HTML content to spotify_playlist_page.html for debugging")
            
    # Parse HTML content
    soup = BeautifulSoup(html, 'html.parser')
    
    # Method 1: Try to extract JSON data from script tags
    print("Attempting to extract track data from script tags...")
    scripts = soup.find_all('script')
    playlist_data = None
    
    for script in scripts:
        if script.string and 'Spotify.Entity' in script.string:
            try:
                # Extract JSON data
                json_text = script.string.split('Spotify.Entity = ')[1].split(';</script>')[0]
                playlist_data = json.loads(json_text)
                print("Found Spotify.Entity data")
                break
            except Exception as e:
                print(f"Error parsing script tag: {e}")
                continue
                
    tracks = []
    
    # Process JSON data if found
    if playlist_data:
        try:
            print("\nProcessing JSON data from Spotify.Entity...")
            playlist_name = playlist_data.get('name', 'Unknown Playlist')
            print(f"Playlist name: {playlist_name}")
            
            playlist_items = playlist_data.get('tracks', {}).get('items', [])
            print(f"Found {len(playlist_items)} tracks in JSON data")
            
            for item in playlist_items:
                track = item.get('track', {})
                if not track:
                    continue
                    
                title = track.get('name', '')
                artists = [artist.get('name', '') for artist in track.get('artists', [])]
                artist_string = ", ".join(artists) if artists else "Unknown Artist"
                
                tracks.append({
                    'name': title,
                    'artists': artist_string,
                    'search_query': f"{title} - {artist_string}"
                })
        except Exception as e:
            print(f"Error processing JSON data: {e}")
    
    # Method 2: Direct HTML parsing if JSON method failed
    if not tracks:
        print("\nFalling back to direct HTML parsing...")
        track_elements = soup.select('div[data-testid="tracklist-row"]')
        print(f"Found {len(track_elements)} track elements in HTML")
        
        if not track_elements:
            # Try alternative selectors
            print("Trying alternative selectors...")
            # Look for any element that might contain track information
            for selector in [
                'div.track-row', 
                'div.tracklist-row', 
                'div[role="row"]',
                'div[role="listitem"]',
                'div.tracklistRow',
                'tr.tracklistRow'
            ]:
                elements = soup.select(selector)
                if elements:
                    print(f"Found {len(elements)} elements with selector: {selector}")
                    track_elements = elements
                    break
        
        for i, element in enumerate(track_elements[:10]):  # Process first 10 tracks for demo
            try:
                # Try multiple potential selectors for track title and artist
                title = None
                artists = []
                
                # Try different selectors for title
                title_selectors = [
                    'a[data-testid="internal-track-link"]',
                    'div[data-testid="tracklist-row"] span',
                    'a.track-name',
                    'span.track-name',
                    'div.track-name',
                    'div[role="gridcell"] a',
                    'div[role="gridcell"] span',
                    'a',  # Last resort: any link
                ]
                
                for selector in title_selectors:
                    title_element = element.select_one(selector)
                    if title_element:
                        title = title_element.get_text().strip()
                        break
                
                # Try different selectors for artists
                artist_selectors = [
                    'a[href*="/artist/"]',
                    'span.artist-name',
                    'div.artist-name',
                    'a[href*="artist"]',
                    'div[role="gridcell"]:nth-child(2) a',
                ]
                
                for selector in artist_selectors:
                    artist_elements = element.select(selector)
                    if artist_elements:
                        artists = [artist.get_text().strip() for artist in artist_elements]
                        break
                
                # If we found a title but no artists, try to extract from parent text
                if title and not artists:
                    text = element.get_text()
                    if " - " in text:
                        artist_string = text.split(" - ")[1].strip()
                        artists = [artist_string]
                
                artist_string = ", ".join(artists) if artists else "Unknown Artist"
                
                if title:
                    tracks.append({
                        'name': title,
                        'artists': artist_string,
                        'search_query': f"{title} - {artist_string}"
                    })
            except Exception as e:
                print(f"Error parsing track element {i}: {e}")
    
    # If still no tracks, try to extract from page title
    if not tracks:
        print("\nTrying to extract playlist content from page metadata...")
        try:
            # Get playlist title
            title_meta = soup.find('meta', property='og:title')
            playlist_title = title_meta.get('content') if title_meta else "Unknown Playlist"
            print(f"Playlist title from metadata: {playlist_title}")
            
            # Look for any text content that might represent tracks
            print("Dumping all text content that might be track data")
            with open("spotify_text_content.txt", "w", encoding="utf-8") as f:
                # Look for text patterns that might be track listings
                for element in soup.find_all(['div', 'span', 'li']):
                    text = element.get_text().strip()
                    if " - " in text or " by " in text:
                        f.write(f"{text}\n\n")
            print("Saved potential track listing text to spotify_text_content.txt")
        except Exception as e:
            print(f"Error extracting metadata: {e}")
    
    return tracks

async def main():
    print_separator("SPOTIFY PLAYLIST SCRAPER TEST")
    
    # Test URLs
    test_urls = [
        "https://open.spotify.com/playlist/0MUTRlQUXW9hZQdSsyNNSC?si=eba74d6443ff4a54",  # User provided playlist
        "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M",  # Today's Top Hits
        "https://open.spotify.com/playlist/37i9dQZEVXbMDoHDwVN2tF"   # Global Top 50
    ]
    
    for url in test_urls:
        print_separator(f"Testing URL: {url}")
        tracks = await get_playlist_tracks(url)
        
        if tracks:
            print(f"\nSuccessfully extracted {len(tracks)} tracks")
            print("\nSample tracks:")
            for i, track in enumerate(tracks[:5]):  # Show first 5 tracks
                print(f"{i+1}. {track['name']} - {track['artists']}")
        else:
            print("Failed to extract any tracks from this playlist")
    
    print_separator("TEST COMPLETE")

if __name__ == "__main__":
    asyncio.run(main()) 