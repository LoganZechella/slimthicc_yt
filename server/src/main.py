from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
from src.config.settings import settings
from src.config.database import connect_to_mongo, close_mongo_connection
from src.api.v1.router import router as api_router
from src.services.websocket_manager import websocket_manager
import json
import logging
import re
import sys
import uvicorn

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

# Add fallback for CORS settings if empty or missing
if not settings.CORS_ORIGINS or len(settings.CORS_ORIGINS) == 0:
    logger.warning("No CORS origins found in settings, using fallback with wildcard")
    cors_origins = ["*"]
    settings.CORS_ALLOW_ALL = True
else:
    cors_origins = settings.CORS_ORIGINS

if "*" in cors_origins:
    logger.warning("Allowing all origins with CORS wildcard '*'")

# Set up CORS middleware with improved handling of preflight requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    max_age=86400,  # Cache preflight request results for 24 hours (in seconds)
)

# Custom middleware for debugging CORS requests
@app.middleware("http")
async def cors_debug_middleware(request: Request, call_next):
    # Log all OPTIONS requests for debugging
    if request.method == "OPTIONS":
        logger.info(f"Received OPTIONS preflight request from {request.client.host} to {request.url.path}")
        logger.debug(f"Request headers: {dict(request.headers)}")
    
    # Debug WebSocket connection attempts
    if request.url.path.endswith('/ws') or 'websocket' in request.headers.get('upgrade', '').lower():
        logger.info(f"WebSocket connection attempt detected: {request.url.path} from {request.client.host}")
        logger.debug(f"Request headers: {dict(request.headers)}")

    # Process the request and get the response
    response = await call_next(request)

    # Add CORS headers to every response
    if request.method == "OPTIONS":
        # Log the response headers for debugging
        logger.info(f"Responding to OPTIONS request with headers: {dict(response.headers)}")
    
    # Log 404 responses for debugging
    if response.status_code == 404:
        logger.warning(f"404 Not Found: {request.method} {request.url.path}")
    
    return response

# Root-level WebSocket catch-all
@app.websocket("/api/v1/downloads/{task_id}/ws")
async def root_websocket_endpoint(websocket: WebSocket, task_id: str):
    """
    Root-level WebSocket endpoint for real-time task updates.
    This is registered at the application level to ensure it captures all WebSocket connections.
    """
    logger.info(f"ROOT WebSocket connection request for task {task_id} from {websocket.client.host}")
    
    try:
        # Accept the connection
        await websocket_manager.connect(websocket, task_id)
        logger.info(f"ROOT WebSocket connection accepted for task {task_id}")
        
        from src.services.download_task_manager import download_task_manager
        
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
            logger.info(f"ROOT Sent initial status for task {task_id}: {task.status}, progress: {task.progress}")
        else:
            logger.warning(f"ROOT Task {task_id} not found when sending initial status")
            await websocket.send_json({"error": f"Task {task_id} not found"})
        
        # Keep the connection open and handle client messages
        try:
            while True:
                # Wait for any message from the client (ping/keepalive)
                data = await websocket.receive_text()
                logger.debug(f"ROOT Received message from client {task_id}: {data}")
                
                # Send current status on any client message
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
                    logger.debug(f"ROOT Sent status update for task {task_id}: {task.status}, progress: {task.progress}")
                else:
                    logger.warning(f"ROOT Task {task_id} not found when sending status update")
                    await websocket.send_json({"error": f"Task {task_id} not found"})
                
        except WebSocketDisconnect:
            logger.info(f"ROOT WebSocket disconnected for task {task_id}")
        except Exception as ws_error:
            logger.error(f"ROOT Error in WebSocket communication for task {task_id}: {ws_error}", exc_info=True)
        finally:
            # Clean up the connection
            await websocket_manager.disconnect(websocket, task_id)
            logger.info(f"ROOT WebSocket connection closed for task {task_id}")
            
    except Exception as e:
        logger.error(f"ROOT Error in WebSocket connection setup for task {task_id}: {e}", exc_info=True)
        # Ensure connection is closed on error
        try:
            await websocket_manager.disconnect(websocket, task_id)
            logger.info(f"ROOT WebSocket connection force closed after error for task {task_id}")
        except Exception as disconnect_error:
            logger.error(f"ROOT Error disconnecting WebSocket for task {task_id}: {disconnect_error}")

# Root-level WebSocket catch-all with alternative pattern
@app.websocket("/{path:path}")
async def global_fallback_websocket_endpoint(websocket: WebSocket, path: str):
    """
    Fallback global WebSocket handler to catch all other connection attempts.
    Tries to extract task_id from the path using various methods.
    """
    logger.info(f"Fallback WebSocket connection attempt for path: {path}")
    
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
        await websocket.accept()
        await websocket.send_json({"error": "Invalid WebSocket path, could not extract task_id"})
        await websocket.close()
        return
    
    logger.info(f"Fallback handler extracted task_id '{task_id}' from path '{path}'")
    
    try:
        # Accept the connection
        await websocket_manager.connect(websocket, task_id)
        logger.info(f"Fallback WebSocket connection accepted for task {task_id}")
        
        from src.services.download_task_manager import download_task_manager
        
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
                
        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected for task {task_id} (fallback)")
        except Exception as ws_error:
            logger.error(f"Error in WebSocket communication for task {task_id}: {ws_error} (fallback)", exc_info=True)
        finally:
            await websocket_manager.disconnect(websocket, task_id)
            
    except Exception as e:
        logger.error(f"Error in fallback WebSocket handler for path {path}: {e}", exc_info=True)
        # Ensure connection is closed on error
        try:
            await websocket_manager.disconnect(websocket, task_id)
        except Exception:
            pass

# Include API router
app.include_router(api_router, prefix=settings.API_V1_STR)

@app.on_event("startup")
async def startup_db_client():
    # Log important environment variables (redacted for security)
    logger.info("Application starting with configuration:")
    logger.info(f"API base URL: {settings.API_V1_STR}")
    logger.info(f"CORS origins: {settings.CORS_ORIGINS}")
    
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
    logger.info("MongoDB connection closed")

@app.get("/")
async def root():
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "running"
    }

# Add a health check endpoint
@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    # Run the app
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    ) 