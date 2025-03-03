# Correct Python path for imports
import os
import sys
from pathlib import Path

# Get the server directory path
SERVER_DIR = Path(__file__).resolve().parent
ROOT_DIR = SERVER_DIR.parent

# Add both server and root directories to Python path
sys.path.insert(0, str(SERVER_DIR))
sys.path.insert(0, str(ROOT_DIR))

print(f"Python path: {sys.path}")
print(f"Current working directory: {os.getcwd()}")
print(f"Server directory: {SERVER_DIR}")
print(f"Root directory: {ROOT_DIR}")

# Import the FastAPI app from src.main
from src.main import app as application

# Export the application for Gunicorn
app = application

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("run:app", host="0.0.0.0", port=8000, reload=True) 