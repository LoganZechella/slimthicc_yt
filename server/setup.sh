#!/bin/bash

echo "Setting up environment..."

# Create required directories if they don't exist
mkdir -p downloads
mkdir -p temp
mkdir -p tmp

# Set proper permissions
chmod 755 downloads
chmod 755 temp
chmod 755 tmp

# Create empty cookies file if it doesn't exist
touch youtube.cookies
chmod 600 youtube.cookies

# Add ffmpeg-downloader to ensure binary is available
pip install ffmpeg-downloader
python -m ffmpeg_downloader.entry_point

# Export binary path to environment
export PATH="$HOME/.ffmpeg-downloader/bin:$PATH"
echo "PATH updated to include ffmpeg binaries: $PATH"
echo "ffmpeg location: $(which ffmpeg || echo 'Not found')"

echo "Setup complete. Environment initialized with proper permissions." 