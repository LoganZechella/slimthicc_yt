from fastapi import APIRouter
import os
import sys
from pathlib import Path

# Debug output
print(f"Router path: {__file__}")
print(f"Router absolute path: {Path(__file__).resolve()}")
print(f"Working directory: {os.getcwd()}")
print(f"Parent level structure:")
try:
    for i in range(5):
        current_path = Path(__file__).resolve()
        for _ in range(i):
            current_path = current_path.parent
        print(f"Level {i} ({current_path}): {[p.name for p in current_path.iterdir() if p.exists()]}")
except Exception as e:
    print(f"Error mapping directories: {e}")

print(f"Downloads router path: {Path(__file__).parent / 'downloads' / 'router.py'}")
print(f"Downloads router exists: {(Path(__file__).parent / 'downloads' / 'router.py').exists()}")
print(f"Parent contents: {list((Path(__file__).parent).iterdir())}")
print(f"Downloads folder contents: {list((Path(__file__).parent / 'downloads').iterdir()) if (Path(__file__).parent / 'downloads').exists() else 'Dir not found'}")

# Try with direct import using importlib
import importlib.util

# First attempt: looking for downloads in the current directory structure
router_path = Path(__file__).parent / "downloads" / "router.py"
router_found = False

if router_path.exists():
    print(f"Loading router from: {router_path}")
    spec = importlib.util.spec_from_file_location("downloads_router", router_path)
    if spec and spec.loader:
        downloads_module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = downloads_module
        spec.loader.exec_module(downloads_module)
        downloads_router = downloads_module.router
        print("Successfully loaded downloads router")
        router_found = True
    else:
        print(f"Failed to create spec for {router_path}")
else:
    print(f"Router file does not exist at expected path: {router_path}")
    
    # Second attempt: try to find router.py anywhere in the project
    print("Searching for router.py in alternate locations...")
    
    # Try to detect the project root (either /opt/render/project or wherever the git repo was cloned)
    potential_roots = [
        Path('/opt/render/project'),          # Standard Render path
        Path('/opt/render/project/src'),      # Potential structure
        Path('/opt/render/project/server'),   # Another potential structure
        Path(__file__).resolve().parent.parent.parent.parent.parent,  # Move up from current file
        Path(os.getcwd())                     # Current working directory
    ]
    
    for root in potential_roots:
        if root.exists():
            print(f"Searching from potential root: {root}")
            # Look for any router.py in the downloads directory
            try:
                for path in root.glob('**/downloads/router.py'):
                    print(f"Found potential router at: {path}")
                    if not router_found:
                        try:
                            print(f"Attempting to load from: {path}")
                            spec = importlib.util.spec_from_file_location("downloads_router", path)
                            if spec and spec.loader:
                                downloads_module = importlib.util.module_from_spec(spec)
                                sys.modules[spec.name] = downloads_module
                                spec.loader.exec_module(downloads_module)
                                downloads_router = downloads_module.router
                                print(f"Successfully loaded downloads router from: {path}")
                                router_found = True
                                break
                        except Exception as e:
                            print(f"Failed to load from {path}: {e}")
            except Exception as e:
                print(f"Error searching in {root}: {e}")

if not router_found:
    print("Creating fallback router as last resort")
    # Create a simple router as fallback
    simple_router = APIRouter()
    @simple_router.get("/")
    async def empty_downloads():
        return {"message": "Downloads API placeholder - file not found"}
    downloads_router = simple_router

router = APIRouter()

# Include the downloads router with the correct prefix
router.include_router(downloads_router, prefix="/downloads")

@router.get("/health")
async def health_check():
    """
    Health check endpoint
    """
    return {"status": "ok"} 