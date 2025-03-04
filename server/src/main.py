# First, ensure the right path is in the system path
import os
import sys
import time
import asyncio
from pathlib import Path

# Print debug information about the current environment
print(f"Current working directory: {os.getcwd()}")
print(f"Python path (before): {sys.path}")

# Map the directory structure
print("Directory structure analysis:")
try:
    current_dir = Path(os.getcwd())
    print(f"Current directory: {current_dir}")
    
    # Safely list directory contents
    if current_dir.is_dir():
        print(f"Contents: {[f.name for f in current_dir.iterdir() if f.exists()]}")
    else:
        print("Current path is not a directory")
    
    # Check for server directory (might be in different locations)
    server_dir = None
    
    # Try to locate the main project directory
    possible_project_dirs = [
        Path(os.getcwd()),                   # Current directory
        Path("/opt/render/project"),         # Root Render project dir
        Path("/opt/render/project/src"),     # Possible subdirectory on Render
        Path("/opt/render/project/server"),  # Another possible subdirectory
    ]
    
    # Try each possible project directory
    for project_dir in possible_project_dirs:
        print(f"Checking potential project directory: {project_dir}")
        if not project_dir.exists():
            print(f"  Directory doesn't exist")
            continue
            
        if not project_dir.is_dir():
            print(f"  Not a directory")
            continue
            
        # List contents to help with debugging
        try:
            contents = [f.name for f in project_dir.iterdir() if f.exists()]
            print(f"  Contents: {contents}")
        except Exception as e:
            print(f"  Error listing contents: {e}")
            continue

        # Check if this could be the server directory
        if (project_dir / "src").exists() and (project_dir / "src").is_dir():
            server_dir = project_dir
            print(f"✓ Found server directory: {server_dir}")
            break
            
    # After checking all options, set up Python path
    if server_dir:
        # Make sure the server dir is in the path
        if str(server_dir) not in sys.path:
            sys.path.insert(0, str(server_dir))
            print(f"Added server directory to path: {server_dir}")
        
        # Also add the src directory
        src_dir = server_dir / "src"
        if src_dir.exists() and src_dir.is_dir() and str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
            print(f"Added src directory to path: {src_dir}")
    else:
        print("WARNING: Could not locate server directory!")
except Exception as e:
    print(f"Error analyzing directory structure: {e}")

# Check for ffmpeg binary location
ffmpeg_binary_path = Path(os.path.expanduser("~/.ffmpeg-downloader/bin/ffmpeg"))
if ffmpeg_binary_path.exists():
    print(f"Found ffmpeg binary at: {ffmpeg_binary_path}")
    # Add to PATH
    os.environ["PATH"] = f"{ffmpeg_binary_path.parent}:{os.environ.get('PATH', '')}"
    print(f"Updated PATH with ffmpeg binary directory: {ffmpeg_binary_path.parent}")
else:
    print(f"ffmpeg binary not found at expected location: {ffmpeg_binary_path}")
    # Try to find ffmpeg in PATH
    import subprocess
    try:
        ffmpeg_path = subprocess.check_output(["which", "ffmpeg"]).decode().strip()
        print(f"Found ffmpeg in PATH at: {ffmpeg_path}")
    except subprocess.CalledProcessError:
        print("ffmpeg not found in PATH")

print(f"Python path (after): {sys.path}")

# Always use absolute imports with src prefix for better reliability
try:
    from src.config.settings import settings
    from src.config.database import connect_to_mongo, close_mongo_connection
    from src.api.v1.router import router as api_router
    from src.services.websocket_manager import websocket_manager
except ImportError as e:
    print(f"Failed to import required modules: {e}")
    raise ImportError("Failed to import required modules") from e

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import json
import logging
import re
import uvicorn
from fastapi.responses import JSONResponse
import traceback
import time
import asyncio

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format=settings.LOG_FORMAT,
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Ensure .env is loaded
load_dotenv()

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Music Download API",
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    debug=settings.DEBUG
)

# Log CORS settings
logger.info(f"Configuring CORS with origins: {settings.CORS_ORIGINS}")

# Create a list of allowed origins that is guaranteed to include the Netlify domain
netlify_domain = "https://slimthicc-commandcenter.netlify.app"
allowed_origins = ["*", netlify_domain, "http://localhost:5173", "http://localhost:3000"]
logger.warning(f"Setting up CORS with these origins: {allowed_origins}")

# Set up CORS middleware with improved handling of preflight requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=86400,  # Cache preflight request results for 24 hours (in seconds)
    expose_headers=["*"]
)

# Also add a raw middleware for handling CORS as a fallback
@app.middleware("http")
async def cors_middleware(request: Request, call_next):
    """CORS middleware handling."""
    # For OPTIONS requests, return a simple response right away
    if request.method == "OPTIONS":
        origin = request.headers.get("origin", "*")
        
        response = Response(
            content="",
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Credentials": "true",
                "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
                "Access-Control-Allow-Headers": "*",
                "Access-Control-Max-Age": "86400",
                "Content-Type": "text/plain",
                "Content-Length": "0"
            }
        )
        logger.info(f"CORS headers set for OPTIONS request from {origin}: {dict(response.headers)}")
        return response
    
    # For WebSocket upgrade requests, pass through without modification
    if request.headers.get("upgrade", "").lower() == "websocket":
        logger.info(f"WebSocket connection request for task {request.path_params.get('task_id')} from {request.client.host}")
        return await call_next(request)
    
    # For regular requests
    response = await call_next(request)
    
    # Set CORS headers
    origin = request.headers.get("origin", "*")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
    
    return response

# Global error handler for all routes
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {str(exc)}")
    logger.error(traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"}
    )

# Import the router modules
from src.api.v1.downloads.router import router as downloads_router

@app.websocket("/api/v1/downloads/{task_id}/ws")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    """WebSocket endpoint for task status updates."""
    try:
        logger.info(f"WebSocket connection request for task {task_id} from {websocket.client.host}")
        
        # Accept the connection
        await websocket.accept()
        logger.info(f"WebSocket connection accepted for task {task_id}")
        
        # Get the WebSocket manager
        from src.services.websocket_manager import websocket_manager
        from src.services.download_task_manager import download_task_manager
        
        # Connect to the WebSocket manager
        await websocket_manager.connect(websocket, task_id)
        
        # Get and send the initial task status
        task = await download_task_manager.get_task(task_id)
        if task:
            initial_status = {
                "type": "status",
                "task_id": task_id,
                "status": task.status,
                "progress": task.progress,
                "title": task.title,
                "error": task.error,
                "timestamp": time.time()
            }
            await websocket.send_json(initial_status)
            logger.info(f"Sent initial status for task {task_id}")
        
        # Handle messages from client
        while True:
            try:
                # Wait for a message with a timeout
                message_json = await asyncio.wait_for(websocket.receive_json(), timeout=60)
                
                # Handle client message - usually "hello" or heartbeat
                msg_type = message_json.get("type", "unknown")
                logger.info(f"Received {msg_type} message from client for task {task_id}")
                
                # Send acknowledgment
                await websocket.send_json({"type": "ack", "for": msg_type, "task_id": task_id})
                
            except asyncio.TimeoutError:
                # No message received within timeout, check if connection is still valid
                logger.debug(f"No message received from client for task {task_id} within timeout")
                continue
                
            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected for task {task_id}")
                await websocket_manager.disconnect(websocket, task_id)
                break
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for task {task_id}")
        try:
            from src.services.websocket_manager import websocket_manager
            await websocket_manager.disconnect(websocket, task_id)
        except Exception as e:
            logger.error(f"Error during disconnect: {str(e)}")
            
    except Exception as e:
        logger.error(f"Error in WebSocket endpoint for task {task_id}: {str(e)}")
        try:
            if websocket.client_state.name.lower() == "connected":
                await websocket.close(code=1011, reason=f"Internal server error: {str(e)}")
        except Exception as close_error:
            logger.error(f"Error closing WebSocket connection: {str(close_error)}")

# Root-level WebSocket catch-all with alternative pattern
@app.websocket("/{path:path}")
async def global_fallback_websocket_endpoint(websocket: WebSocket, path: str):
    """
    Fallback global WebSocket handler to catch all other connection attempts.
    Tries to extract task_id from the path using various methods.
    """
    client_host = getattr(websocket.client, 'host', 'unknown')
    logger.info(f"Fallback WebSocket connection attempt for path: {path} from {client_host}")
    
    # Try multiple methods to extract task_id from the path
    task_id = None
    
    # Method 1: Extract using regex for UUID pattern
    uuid_pattern = r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})'
    uuid_match = re.search(uuid_pattern, path)
    if uuid_match:
        task_id = uuid_match.group(1)
        logger.info(f"Extracted task_id from UUID pattern: {task_id}")
    
    # Method 2: Check if path ends with /ws and extract the previous part
    if not task_id and path.endswith('/ws'):
        parts = path.strip('/').split('/')
        if len(parts) > 1:
            potential_task_id = parts[-2]  # Get the part before /ws
            if len(potential_task_id) > 30:  # Likely a UUID
                task_id = potential_task_id
                logger.info(f"Extracted task_id from path before /ws: {task_id}")
    
    # Method 3: Check if path contains 'downloads' and extract the next part
    if not task_id and 'downloads' in path:
        parts = path.strip('/').split('/')
        for i, part in enumerate(parts):
            if part == 'downloads' and i+1 < len(parts):
                potential_task_id = parts[i+1]
                if len(potential_task_id) > 30:  # Likely a UUID
                    task_id = potential_task_id
                    logger.info(f"Extracted task_id after 'downloads' in path: {task_id}")
                    break
    
    # Method 4: Last resort - just take the longest part that looks like a UUID
    if not task_id:
        parts = path.strip('/').split('/')
        for part in parts:
            if len(part) > 30:  # Likely a UUID
                task_id = part
                logger.info(f"Extracted task_id as longest part that looks like UUID: {task_id}")
                break
    
    # If we still don't have a task_id, use the first part as a fallback
    if not task_id and len(path.strip('/').split('/')) > 0:
        task_id = path.strip('/').split('/')[0]
        logger.info(f"Using first path part as task_id fallback: {task_id}")
    
    # If we cannot extract a task_id, reject the connection
    if not task_id:
        logger.error(f"Could not extract task_id from WebSocket path: {path}")
        try:
            await websocket.accept()
            await websocket.send_json({"error": "Invalid WebSocket path, could not extract task_id"})
            await websocket.close(code=1003, reason="Invalid path")
        except Exception as e:
            logger.error(f"Error rejecting WebSocket connection: {e}")
        return
    
    logger.info(f"Fallback handler extracted task_id '{task_id}' from path '{path}'")
    
    try:
        # Accept the connection
        connected = await websocket_manager.connect(websocket, task_id)
        if not connected:
            logger.error(f"Fallback: Failed to establish WebSocket connection for task {task_id}")
            try:
                await websocket.close(code=1011, reason="Failed to establish connection")
            except Exception:
                pass
            return
            
        logger.info(f"Fallback WebSocket connection accepted for task {task_id}")
        
        from services.download_task_manager import download_task_manager
        
        # Send initial status
        task = await download_task_manager.get_task(task_id)
        if task:
            initial_status = {
                "id": task.id,
                "status": task.status,
                "progress": task.progress,
                "title": task.title,
                "author": task.author,
                "error": task.error
            }
            await websocket.send_json(initial_status)
            logger.info(f"Sent initial status for task {task_id}: {task.status}, progress: {task.progress} (fallback)")
        else:
            logger.warning(f"Task {task_id} not found when sending initial status (fallback)")
            await websocket.send_json({"error": f"Task {task_id} not found"})
        
        # Handle messages
        try:
            while True:
                data = await websocket.receive_text()
                logger.debug(f"Received message from client {task_id}: {data} (fallback)")
                
                # Try to parse as JSON if possible
                try:
                    json_data = json.loads(data)
                    message_type = json_data.get('type', '')
                    
                    # Handle ping messages
                    if message_type == 'ping':
                        await websocket.send_json({"type": "pong", "timestamp": json_data.get('timestamp')})
                        logger.debug(f"Sent pong to client {task_id} (fallback)")
                        continue
                except Exception:
                    # Not JSON or other error, treat as regular message
                    pass
                
                # Send current status
                task = await download_task_manager.get_task(task_id)
                if task:
                    status_update = {
                        "id": task.id,
                        "status": task.status,
                        "progress": task.progress,
                        "title": task.title,
                        "author": task.author,
                        "error": task.error
                    }
                    await websocket.send_json(status_update)
                else:
                    await websocket.send_json({"error": f"Task {task_id} not found"})
                
        except WebSocketDisconnect as disconnect_error:
            logger.info(f"WebSocket disconnected for task {task_id}: code={getattr(disconnect_error, 'code', 'unknown')} (fallback)")
        except Exception as ws_error:
            logger.error(f"Error in WebSocket communication for task {task_id}: {ws_error} (fallback)", exc_info=True)
        finally:
            await websocket_manager.disconnect(websocket, task_id)
            logger.info(f"WebSocket connection closed for task {task_id} (fallback)")
            
    except Exception as e:
        logger.error(f"Error in fallback WebSocket handler for path {path}: {e}", exc_info=True)
        # Ensure connection is closed on error
        try:
            await websocket_manager.disconnect(websocket, task_id)
        except Exception:
            pass

# Include API router
app.include_router(api_router, prefix=settings.API_V1_STR)

# Health check endpoint for Render
@app.get(f"{settings.API_V1_STR}/health", tags=["health"])
async def health_check():
    """
    Health check endpoint for monitoring services
    """
    return {"status": "healthy", "version": settings.VERSION}

@app.on_event("startup")
async def startup_db_client():
    # Log important environment variables (redacted for security)
    logger.info("Application starting with configuration:")
    logger.info(f"API base URL: {settings.API_V1_STR}")
    logger.info(f"CORS origins: {settings.CORS_ORIGINS}")
    
    # Configure ffmpeg wrapper with binary path if available
    ffmpeg_binary_path = Path(os.path.expanduser("~/.ffmpeg-downloader/bin/ffmpeg"))
    if ffmpeg_binary_path.exists():
        logger.info(f"Using ffmpeg binary at: {ffmpeg_binary_path}")
        os.environ["FFMPEG_BINARY"] = str(ffmpeg_binary_path)
    else:
        # Try to find ffmpeg in PATH
        import subprocess
        try:
            ffmpeg_path = subprocess.check_output(["which", "ffmpeg"]).decode().strip()
            logger.info(f"Using ffmpeg from PATH at: {ffmpeg_path}")
            os.environ["FFMPEG_BINARY"] = ffmpeg_path
        except subprocess.CalledProcessError:
            logger.warning("ffmpeg not found in PATH, some functionality might be limited")
    
    # Log Spotify credential presence
    spotify_client_id = settings.SPOTIFY_CLIENT_ID or os.getenv("SPOTIPY_CLIENT_ID")
    spotify_client_secret = settings.SPOTIFY_CLIENT_SECRET or os.getenv("SPOTIPY_CLIENT_SECRET")
    
    logger.info(f"Spotify credentials configured: {bool(spotify_client_id and spotify_client_secret)}")
    
    # Log directories
    logger.info(f"Downloads directory: {settings.DOWNLOADS_DIR}")
    logger.info(f"Temp directory: {settings.TEMP_DIR}")
    
    # Connect to MongoDB
    await connect_to_mongo()
    logger.info("Successfully connected to MongoDB")

@app.on_event("shutdown")
async def shutdown_db_client():
    await close_mongo_connection()
    logger.info("Disconnected from MongoDB")

@app.get("/")
async def root():
    """
    Root endpoint for health checks
    """
    return {"status": "ok", "message": "SlimThicc YT Server is running"}

@app.get("/health")
async def root_health_check():
    """
    Root-level health check endpoint for Render
    """
    return {"status": "ok"}

# Helper function to send task status update
async def _send_task_status_update(task_id: str, websocket: WebSocket):
    """Send the current task status to a specific websocket."""
    try:
        from services.download_task_manager import download_task_manager
        task = await download_task_manager.get_task(task_id)
        
        if task:
            status_update = {
                "type": "status_update",
                "status": task.status,
                "progress": task.progress,
                "timestamp": time.time()
            }
            
            # Include additional task information
            if hasattr(task, 'title'):
                status_update["title"] = task.title
            if hasattr(task, 'author'):
                status_update["author"] = task.author
            if hasattr(task, 'details'):
                status_update["details"] = task.details
            if hasattr(task, 'error'):
                status_update["error"] = task.error
            if hasattr(task, 'download_url') and task.status == 'completed':
                status_update["download_url"] = task.download_url
                
            await websocket.send_json(status_update)
            logger.debug(f"Sent status update for task {task_id}: {task.status}, progress: {task.progress}")
        else:
            logger.warning(f"Task {task_id} not found when sending status update")
            await websocket.send_json({
                "type": "error",
                "error": f"Task {task_id} not found",
                "timestamp": time.time()
            })
    except Exception as e:
        logger.error(f"Error sending task status update for {task_id}: {e}", exc_info=True)
        # Don't re-raise to prevent connection termination

@app.options("/api/v1/cors-test")
async def cors_test_preflight(request: Request):
    """
    OPTIONS endpoint that explicitly tests CORS preflight requests.
    This route handles the OPTIONS preflight request for CORS testing.
    """
    origin = request.headers.get("origin", "unknown")
    logger.info(f"Received OPTIONS request to /api/v1/cors-test from origin: {origin}")
    
    # No content needed for OPTIONS response
    return {}

@app.get("/api/v1/cors-test")
async def cors_test(request: Request):
    """
    Simple endpoint to test if CORS is working correctly.
    Frontend can call this endpoint to verify CORS headers are being set properly.
    """
    origin = request.headers.get("origin", "unknown")
    logger.info(f"Received GET request to /api/v1/cors-test from origin: {origin}")
    
    return {
        "status": "success",
        "message": "CORS is configured correctly!",
        "cors_origins": allowed_origins,
        "netlify_domain": netlify_domain,
        "request_origin": origin,
        "timestamp": time.time(),
        "server": "slimthicc-yt.onrender.com"
    }

if __name__ == "__main__":
    # Run the app
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    ) 