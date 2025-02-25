#!/bin/bash

# Create downloads directory if it doesn't exist
mkdir -p downloads

# Set proper permissions (755 for directories)
chmod 755 downloads

# Create empty cookies file if it doesn't exist
touch youtube.cookies
chmod 600 youtube.cookies

echo "Setup complete. Directory structure initialized with proper permissions." 