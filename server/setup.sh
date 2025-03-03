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

# Install system dependencies (for Render deployment)
if [ -f /etc/debian_version ]; then
    echo "Installing ffmpeg on Debian/Ubuntu..."
    apt-get update
    apt-get install -y ffmpeg
elif command -v yum > /dev/null; then
    echo "Installing ffmpeg on CentOS/RHEL..."
    yum install -y ffmpeg
elif command -v brew > /dev/null; then
    echo "Installing ffmpeg with Homebrew (macOS)..."
    brew install ffmpeg
else
    echo "WARNING: Could not install ffmpeg automatically. Please install it manually."
fi

echo "Setup complete. Environment initialized with proper permissions." 