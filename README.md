# SlimThicc YT Playlist Downloader

A simple and efficient YouTube playlist downloader that converts videos to MP3 format. Built with Python and supports both Intel and Apple Silicon Macs.

## Features

- Download entire YouTube playlists
- Automatically converts videos to MP3 format
- User-friendly GUI interface
- Universal binary support (works on both Intel and Apple Silicon Macs)
- Built-in ffmpeg binaries (no external dependencies needed)

## Installation

### Option 1: Download the Pre-built App

1. Go to the [Releases](../../releases) page
2. Download the latest `playlist_run_universal.app.zip`
3. Extract the zip file
4. Move the app to your Applications folder

### Option 2: Build from Source

1. Clone this repository:
   ```bash
   git clone https://github.com/LoganZechella/slimthicc_yt.git
   cd slimthicc_yt
   ```

2. Create and activate a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run the script directly:
   ```bash
   python playlist_run.py
   ```

   Or build the universal binary:
   ```bash
   chmod +x build_universal.sh
   ./build_universal.sh
   ```

## Usage

1. Launch the application
2. Enter a YouTube playlist URL in the "Playlist URL" field
3. Click "Browse" to select where you want to save the MP3 files
4. Click "Start Download" to begin the process
5. Wait for the download and conversion to complete

## Requirements

- macOS 10.15 or later
- Internet connection
- Sufficient storage space for downloaded files

## Development

This project uses Git LFS for managing large binary files. If you want to contribute, make sure to install Git LFS:

```bash
brew install git-lfs
git lfs install
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) for the YouTube download functionality
- [FFmpeg](https://ffmpeg.org/) for audio conversion 