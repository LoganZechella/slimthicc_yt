#!/bin/bash

echo "Setting up environment..."

# Get current directory
CURRENT_DIR=$(pwd)
echo "Current directory: $CURRENT_DIR"

# Define data directories
if [ -d "/opt/render" ]; then
  # On Render, use a directory relative to the current directory (which is 'server')
  DATA_DIR="render_data"
  echo "Running on Render, using data directory: $DATA_DIR"
else
  # Local development
  DATA_DIR="render_data"
  echo "Running locally, using data directory: $DATA_DIR"
fi

# Create required directories if they don't exist
mkdir -p $DATA_DIR/downloads
mkdir -p $DATA_DIR/temp
mkdir -p $DATA_DIR/scripts
mkdir -p $DATA_DIR/tmp
mkdir -p $DATA_DIR/chrome_profile

# Set proper permissions
chmod -R 755 $DATA_DIR

# Create empty cookies file if it doesn't exist
touch youtube.cookies
chmod 600 youtube.cookies

# Copy YouTube cookies to persistent directory if it exists
if [ -f youtube.cookies ]; then
  cp youtube.cookies $DATA_DIR/scripts/youtube.cookies 2>/dev/null || true
  chmod 600 $DATA_DIR/scripts/youtube.cookies 2>/dev/null || true
  echo "YouTube cookies copied to persistent storage"
fi

# Install Chrome/Chromium for cookies-from-browser feature
echo "Installing Chrome for browser cookie support..."

# Check if running on Render
if [ -d "/opt/render" ]; then
  echo "Detected Render.com environment, installing Chrome..."
  
  # Install Chrome dependencies
  apt-get update || true
  apt-get install -y wget gnupg || true
  
  # Add Chrome repository
  wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - || true
  echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list || true
  
  # Install Chrome
  apt-get update || true
  apt-get install -y google-chrome-stable || true
  
  # Verify Chrome installation
  CHROME_VERSION=$(google-chrome --version || echo "Chrome not installed")
  echo "Chrome version: $CHROME_VERSION"
  
  # Create writable directories for Render
  echo "Setting up writable directories for Render..."
  mkdir -p $DATA_DIR/downloads $DATA_DIR/temp $DATA_DIR/scripts $DATA_DIR/tmp $DATA_DIR/chrome_profile
  chmod -R 755 $DATA_DIR
  echo "Created writable directories in $DATA_DIR"
else
  echo "Not running on Render, skipping Chrome installation"
fi

# Add ffmpeg-downloader to ensure binary is available
pip install ffmpeg-downloader
python -m ffmpeg_downloader.entry_point || true

# Export binary path to environment
export PATH="$HOME/.ffmpeg-downloader/bin:$PATH"
echo "PATH updated to include ffmpeg binaries: $PATH"
echo "ffmpeg location: $(which ffmpeg || echo 'Not found')"

echo "Setup complete. Environment initialized with proper permissions."