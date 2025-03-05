#!/bin/bash

echo "Setting up environment..."

# Create required directories if they don't exist
mkdir -p downloads
mkdir -p temp
mkdir -p tmp
mkdir -p /opt/render/data/scripts
mkdir -p /opt/render/data/temp
mkdir -p /opt/render/data/downloads
mkdir -p /opt/render/data/chrome_profile

# Set proper permissions
chmod 755 downloads
chmod 755 temp
chmod 755 tmp
chmod 755 /opt/render/data/scripts
chmod 755 /opt/render/data/temp
chmod 755 /opt/render/data/downloads
chmod 755 /opt/render/data/chrome_profile

# Create empty cookies file if it doesn't exist
touch youtube.cookies
chmod 600 youtube.cookies

# Copy YouTube cookies to persistent directory if it exists
if [ -f youtube.cookies ]; then
  cp youtube.cookies /opt/render/data/scripts/youtube.cookies
  chmod 600 /opt/render/data/scripts/youtube.cookies
  echo "YouTube cookies copied to persistent storage"
fi

# Install Chrome/Chromium for cookies-from-browser feature
echo "Installing Chrome for browser cookie support..."

# Check if running on Render
if [ -d "/opt/render" ]; then
  echo "Detected Render.com environment, installing Chrome..."
  
  # Install Chrome dependencies
  apt-get update
  apt-get install -y wget gnupg
  
  # Add Chrome repository
  wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -
  echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list
  
  # Install Chrome
  apt-get update
  apt-get install -y google-chrome-stable
  
  # Verify Chrome installation
  CHROME_VERSION=$(google-chrome --version || echo "Chrome not installed")
  echo "Chrome version: $CHROME_VERSION"
else
  echo "Not running on Render, skipping Chrome installation"
fi

# Add ffmpeg-downloader to ensure binary is available
pip install ffmpeg-downloader
python -m ffmpeg_downloader.entry_point

# Export binary path to environment
export PATH="$HOME/.ffmpeg-downloader/bin:$PATH"
echo "PATH updated to include ffmpeg binaries: $PATH"
echo "ffmpeg location: $(which ffmpeg || echo 'Not found')"

# Generate a basic browser profile for cookies-from-browser
echo "Setting up browser profile directories..."
mkdir -p /opt/render/data/chrome_profile
chmod 755 /opt/render/data/chrome_profile

echo "Setup complete. Environment initialized with proper permissions."