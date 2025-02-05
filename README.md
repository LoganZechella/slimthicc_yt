# Playlist Downloader

A powerful desktop application that allows you to download music from both YouTube and Spotify playlists. The application converts the downloaded content to high-quality MP3 format.

## Features

- Download tracks from YouTube playlists
- Download tracks from Spotify playlists (converts to MP3 via YouTube)
- Dual playlist support - download from both sources simultaneously
- Progress tracking with estimated time remaining
- Detailed logging of download progress
- High-quality MP3 conversion (192kbps)
- Cross-platform support (macOS, Windows, Linux)

## Prerequisites

- Python 3.7 or higher
- FFmpeg (included in the application bundle)
- Spotify Developer credentials (only needed for Spotify playlist support)

## Installation

1. Clone this repository:
```bash
git clone https://github.com/yourusername/playlist-downloader.git
cd playlist-downloader
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows, use: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Spotify Setup (Optional)

To use Spotify playlist functionality, you need to set up Spotify API credentials:

1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Log in with your Spotify account
3. Create a new application
4. Get your Client ID and Client Secret
5. Create a `.env` file in the project root with your credentials:
```bash
SPOTIPY_CLIENT_ID='your-spotify-client-id'
SPOTIPY_CLIENT_SECRET='your-spotify-client-secret'
```

## Usage

1. Run the application:
```bash
python playlist_run.py
```

2. In the application:
   - Enter a YouTube playlist URL and/or a Spotify playlist URL
   - Select a download directory
   - Click "Start Download"
   - Monitor progress in the status window

## Building from Source

To create a standalone executable:

```bash
# For macOS Universal Binary (both Intel and Apple Silicon)
./build_universal.sh

# For other platforms
pyinstaller playlist_run.spec
```

The built application will be available in the `dist` directory.

## Notes

- For Spotify playlists, the application searches YouTube for the highest quality official audio version of each track
- The application will continue downloading even if some tracks fail
- A summary of any failed downloads will be shown at the end
- The application uses threading to keep the UI responsive during downloads

## Troubleshooting

1. **Spotify Authentication Error**
   - Verify your Spotify credentials in the `.env` file
   - Ensure you have created a Spotify Developer application
   - Check that your application is properly configured in the Spotify Developer Dashboard

2. **Download Failures**
   - Check your internet connection
   - Verify the playlist URLs are correct and accessible
   - Ensure you have write permissions in the download directory

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. 