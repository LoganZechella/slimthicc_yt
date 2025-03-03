from fastapi import APIRouter
import os
import sys
from pathlib import Path

# Print debug information
print(f"Router: Current working directory: {os.getcwd()}")
print(f"Router: __file__: {__file__}")
print(f"Router: Python path: {sys.path}")

# Try multiple import strategies
try:
    # Try explicit relative import
    from .downloads.router import router as downloads_router
    print("Router: Using relative import (.downloads.router)")
except ImportError as e:
    try:
        # Try absolute import with src prefix
        from src.api.v1.downloads.router import router as downloads_router
        print("Router: Using absolute import (src.api.v1.downloads.router)")
    except ImportError as e:
        # Try absolute import with full path
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "downloads_router", 
            Path(__file__).parent / "downloads" / "router.py"
        )
        if spec and spec.loader:
            downloads_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(downloads_module)
            downloads_router = downloads_module.router
            print("Router: Using spec loader for downloads router")
        else:
            # Fallback to hard-coded path for debugging
            router_path = Path(__file__).parent / "downloads" / "router.py"
            print(f"Router: Attempted to load from {router_path}, exists: {router_path.exists()}")
            raise ImportError(f"Could not import downloads router: {e}")

router = APIRouter()

# Include the downloads router with the correct prefix
router.include_router(downloads_router, prefix="/downloads")

@router.get("/health")
async def health_check():
    """
    Health check endpoint
    """
    return {"status": "ok"} 