#!/bin/bash
set -e

# Print environment information for debugging
echo "========== SERVER STARTUP ==========="
echo "Environment information:"
echo "HOSTNAME: $(hostname)"
echo "PWD: $(pwd)"
echo "USER: $(whoami)"
echo "Python version: $(python --version)"

# Print all environment variables with their values for debugging (with sensitive data masked)
echo "========== ENVIRONMENT VARIABLES =========="
echo "CORS_ORIGINS: ${CORS_ORIGINS:-'(not set)'}"
echo "CORS_ALLOW_ALL: ${CORS_ALLOW_ALL:-'(not set)'}"
echo "MONGODB_URL: ${MONGODB_URL:0:15}...(masked)...${MONGODB_URL: -5}"
echo "MONGODB_DB_NAME: ${MONGODB_DB_NAME:-'(not set)'}"
echo "SPOTIFY_CLIENT_ID: ${SPOTIFY_CLIENT_ID:0:4}...(masked)...${SPOTIFY_CLIENT_ID: -4}"
echo "SPOTIFY_CLIENT_SECRET: ${SPOTIFY_CLIENT_SECRET:0:4}...(masked)"

# Check if the required directories exist
echo "========== DIRECTORY CHECK =========="
mkdir -p downloads tmp
echo "Downloads directory: $(ls -la downloads)"
echo "Temp directory: $(ls -la tmp)"

echo "========== STARTING SERVER =========="
# Start the server with appropriate error handling
exec uvicorn src.main:app --host 0.0.0.0 --port 8000 