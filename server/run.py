# Correct Python path for imports
import os
import sys
from pathlib import Path

# Get the server directory path - handle multiple possible structures
print(f"Initial working directory: {os.getcwd()}")

# Determine the server directory based on context
server_dir = None

# Option 1: We're already in the server directory
if Path("src").exists() and Path("requirements.txt").exists():
    server_dir = Path(os.getcwd())
    print(f"We are in the server directory: {server_dir}")

# Option 2: We're in a parent directory containing a server directory
elif Path("server").exists() and Path("server/src").exists():
    server_dir = Path(os.getcwd()) / "server"
    print(f"Server directory found at: {server_dir}")

# Option 3: We're in the Render environment
elif Path("/opt/render/project").exists():
    # Try to locate the server directory within the Render project
    for potential_path in [
        Path("/opt/render/project/server"),
        Path("/opt/render/project")
    ]:
        if (potential_path / "src").exists():
            server_dir = potential_path
            print(f"Found server directory in Render environment: {server_dir}")
            break

if not server_dir:
    print("WARNING: Could not determine server directory")
    SERVER_DIR = Path(__file__).resolve().parent
    ROOT_DIR = SERVER_DIR.parent
else:
    SERVER_DIR = server_dir
    ROOT_DIR = SERVER_DIR.parent

# Print directory structure for debugging
print(f"Server directory: {SERVER_DIR}")
print(f"Root directory: {ROOT_DIR}")
print(f"Server directory exists: {SERVER_DIR.exists()}")
print(f"Server directory contents: {[f.name for f in SERVER_DIR.iterdir() if f.exists()]}")

# Add both server and root directories to Python path
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Also add the src directory explicitly
src_dir = SERVER_DIR / "src"
if src_dir.exists() and str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
    print(f"Added src directory to path: {src_dir}")

print(f"Python path: {sys.path}")
print(f"Current working directory: {os.getcwd()}")

# Check for ffmpeg binary location
ffmpeg_binary_path = Path(os.path.expanduser("~/.ffmpeg-downloader/bin/ffmpeg"))
if ffmpeg_binary_path.exists():
    print(f"Found ffmpeg binary at: {ffmpeg_binary_path}")
    # Add to PATH
    os.environ["PATH"] = f"{ffmpeg_binary_path.parent}:{os.environ.get('PATH', '')}"
    # Set for Python ffmpeg wrapper
    os.environ["FFMPEG_BINARY"] = str(ffmpeg_binary_path)
    print(f"Updated PATH with ffmpeg binary directory: {ffmpeg_binary_path.parent}")
else:
    print(f"ffmpeg binary not found at expected location: {ffmpeg_binary_path}")
    # Try to find ffmpeg in PATH
    import subprocess
    try:
        ffmpeg_path = subprocess.check_output(["which", "ffmpeg"]).decode().strip()
        print(f"Found ffmpeg in PATH at: {ffmpeg_path}")
        os.environ["FFMPEG_BINARY"] = ffmpeg_path
    except subprocess.CalledProcessError:
        print("ffmpeg not found in PATH, some functionality might be limited")

# Try different import approaches
print("Attempting to import the FastAPI app...")

try:
    # Try the normal import path first
    from src.main import app as application
    print("Successfully imported app from src.main")
except ImportError as e1:
    print(f"Failed to import from src.main: {e1}")
    try:
        # Try with a different import path
        import src.main
        application = src.main.app
        print("Successfully imported app from src.main (alternative approach)")
    except ImportError as e2:
        print(f"Failed alternative import approach: {e2}")
        # Last resort: try a direct file import
        main_path = SERVER_DIR / "src" / "main.py"
        if main_path.exists():
            print(f"Found main.py at: {main_path}")
            import importlib.util
            spec = importlib.util.spec_from_file_location("main", main_path)
            if spec and spec.loader:
                main_module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = main_module
                spec.loader.exec_module(main_module)
                application = main_module.app
                print("Successfully imported app using direct file loading")
            else:
                raise ImportError(f"Could not load spec from {main_path}")
        else:
            raise ImportError(f"main.py not found at {main_path}")

# Export the application for Gunicorn
app = application

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("run:app", host="0.0.0.0", port=8000, reload=True) 