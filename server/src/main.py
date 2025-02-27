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

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format=settings.LOG_FORMAT
)
logger = logging.getLogger(__name__)

# Ensure .env is loaded
load_dotenv()

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Music Download API",
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# Log CORS settings
logger.info(f"Configuring CORS with origins: {settings.CORS_ORIGINS}")
if "*" in settings.CORS_ORIGINS:
    logger.warning("Allowing all origins with CORS wildcard '*'")

# Set up CORS middleware with improved handling of preflight requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
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

    # Process the request and get the response
    response = await call_next(request)

    # Add CORS headers to every response
    if request.method == "OPTIONS":
        # Log the response headers for debugging
        logger.info(f"Responding to OPTIONS request with headers: {dict(response.headers)}")
    
    return response

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