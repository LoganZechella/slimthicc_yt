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
from fastapi.responses import JSONResponse
import traceback
import time

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

# Always allow all origins for WebSocket connections
# WebSocket connections must come directly from the browser to the server
logger.warning("WebSocket connections require direct access - allowing all origins")
cors_origins = ["*"]  # This ensures WebSocket connections work from any origin
settings.CORS_ALLOW_ALL = True

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
    try:
        response = await call_next(request)
        
        # Add CORS headers to every response
        if request.method == "OPTIONS":
            # Log the response headers for debugging
            logger.info(f"Responding to OPTIONS request with headers: {dict(response.headers)}")
        
        # Log 404 responses for debugging
        if response.status_code == 404:
            logger.warning(f"404 Not Found: {request.method} {request.url.path}")
            
        return response
    except Exception as e:
        logger.error(f"Unhandled exception in middleware: {str(e)}")
        logger.error(traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"}
        )

# Global error handler for all routes
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {str(exc)}")
    logger.error(traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"}
    )

# Root-level WebSocket catch-all
@app.websocket("/api/v1/downloads/{task_id}/ws")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    """
    WebSocket endpoint for real-time task updates
    
    Args:
        websocket: The WebSocket connection
        task_id: The task ID to subscribe to
    """
    client_host = getattr(websocket.client, 'host', 'unknown')
    logger.info(f"WebSocket connection request for task {task_id} from {client_host}")
    logger.debug(f"WebSocket headers: {websocket.headers}")
    
    try:
        # Log the connection attempt with extra debugging info
        origin = websocket.headers.get('origin', 'unknown')
        user_agent = websocket.headers.get('user-agent', 'unknown')
        logger.info(f"WebSocket connection for task {task_id} from origin: {origin}, client: {client_host}, agent: {user_agent}")
        
        # Accept the connection through the websocket_manager
        connection_accepted = await websocket_manager.connect(websocket, task_id)
        
        if not connection_accepted:
            logger.error(f"Failed to accept WebSocket connection for task {task_id}")
            await websocket.close(code=1011, reason="Failed to establish connection")
            return
            
        logger.info(f"WebSocket connection established for task {task_id}")
        
        # Send initial connection status
        try:
            await websocket.send_json({
                "type": "connection_status",
                "status": "connected",
                "task_id": task_id,
                "timestamp": time.time()
            })
        except Exception as e:
            logger.error(f"Error sending initial connection status: {e}")
        
        # Keep the connection alive
        try:
            while True:
                # Wait for messages from the client
                data = await websocket.receive_text()
                
                try:
                    message = json.loads(data)
                    logger.debug(f"Received message from client for task {task_id}: {message}")
                    
                    # Handle ping messages
                    if message.get("type") == "ping":
                        await websocket.send_json({
                            "type": "pong",
                            "timestamp": message.get("timestamp"),
                            "server_timestamp": time.time()
                        })
                        continue
                    
                    # Handle other message types
                    message_type = message.get("type", "unknown")
                    logger.debug(f"Processing message type: {message_type} for task {task_id}")
                    
                    # Get task status and send update
                    from src.models.task import Task
                    task = await Task.get_by_id(task_id)
                    
                    if task:
                        status_update = {
                            "status": task.status,
                            "progress": task.progress,
                            "timestamp": time.time()
                        }
                        
                        # Include details if available
                        if hasattr(task, 'details') and task.details:
                            status_update["details"] = task.details
                            
                        # Include error if there is one
                        if hasattr(task, 'error') and task.error:
                            status_update["error"] = task.error
                            
                        await websocket.send_json(status_update)
                        logger.debug(f"Sent status update for task {task_id}: {task.status}, progress: {task.progress}")
                    else:
                        logger.warning(f"Task {task_id} not found when sending status update")
                        await websocket.send_json({"error": f"Task {task_id} not found"})
                    
                except json.JSONDecodeError:
                    logger.warning(f"Received invalid JSON from client for task {task_id}: {data}")
                except Exception as msg_error:
                    logger.error(f"Error processing message for task {task_id}: {msg_error}", exc_info=True)
                
        except WebSocketDisconnect as disconnect_error:
            logger.info(f"WebSocket disconnected for task {task_id}: code={getattr(disconnect_error, 'code', 'unknown')}")
        except Exception as ws_error:
            logger.error(f"Error in WebSocket communication for task {task_id}: {ws_error}", exc_info=True)
        finally:
            # Clean up the connection
            await websocket_manager.disconnect(websocket, task_id)
            logger.info(f"WebSocket connection closed for task {task_id}")
            
    except Exception as e:
        logger.error(f"Error in WebSocket connection setup for task {task_id}: {e}", exc_info=True)
        # Ensure connection is closed on error
        try:
            await websocket.close(code=1011, reason=f"Connection error: {str(e)[:50]}")
            logger.info(f"WebSocket connection force closed after error for task {task_id}")
        except Exception as disconnect_error:
            logger.error(f"Error disconnecting WebSocket for task {task_id}: {disconnect_error}")

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
    logger.info("Disconnected from MongoDB")

@app.get("/")
async def root():
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "running"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    # Run the app
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    ) 