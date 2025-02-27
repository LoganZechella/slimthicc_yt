#!/bin/bash
set -e

# Log CORS settings
echo "Starting server with the following CORS configuration:"
echo "CORS_ORIGINS=${CORS_ORIGINS:-'Not set, using defaults'}"
echo "CORS_ALLOW_ALL=${CORS_ALLOW_ALL:-'false'}"

# Start the server
exec uvicorn src.main:app --host 0.0.0.0 --port 8000 