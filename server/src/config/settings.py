from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv
import os
import logging
from typing import Optional, List, Dict, Union, Any
from pathlib import Path

# Load environment variables before initializing settings
load_dotenv()

# Setup logging for settings initialization
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("settings")

class Settings(BaseSettings):
    """
    Application settings that can be loaded from environment variables.
    """
    # General application settings
    APP_NAME: str = "SlimThicc YT"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    
    # Paths
    APP_TEMP_DIR: str = "tmp"  # Use a local temp directory instead of /app
    CONFIG_DIR: str = "config"
    
    # API settings
    API_PREFIX: str = "/api"
    API_V1_PREFIX: str = "/api/v1"
    API_V1_STR: str = "/api/v1"  # Added for compatibility with FastAPI convention
    
    # FFmpeg settings
    FFMPEG_PATH: str = "ffmpeg"  # Default to system path
    FFMPEG_THREADS: int = 2
    FFMPEG_LOGLEVEL: str = "warning"
    
    # Download settings
    DEFAULT_AUDIO_QUALITY: str = "192k"
    OUTPUT_DIR: str = "downloads"
    
    # YouTube settings
    YOUTUBE_INNERTUBE_KEY: str = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"
    
    # Invidious settings
    INVIDIOUS_FALLBACK_INSTANCES: List[str] = [
        "https://invidious.snopyta.org",
        "https://invidious.kavin.rocks",
        "https://vid.puffyan.us",
        "https://yt.artemislena.eu",
        "https://invidious.nerdvpn.de",
        "https://inv.riverside.rocks",
        "https://invidious.protokolla.fi",
        "https://invidious.esmailelbob.xyz",
        "https://invidious.projectsegfau.lt",
        "https://y.com.sb"
    ]
    
    # Proxy settings
    DEFAULT_PROXIES: Dict[str, str] = {}
    
    # API Settings
    PROJECT_NAME: str = "SlimThicc Music Downloader"
    VERSION: str = "1.0.0"
    
    # Server Settings
    HOST: str = "localhost"
    PORT: int = 8000
    
    # MongoDB Settings
    MONGODB_URL: str = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    MONGODB_DB_NAME: str = os.getenv("MONGODB_DB_NAME", "slimthicc_command_center")
    
    # CORS Settings
    # Read from environment or use defaults
    # Parse comma-separated list from environment variable if present
    CORS_ORIGINS: List[str] = []  # Initialize empty, will be populated in __init__
    # Add wildcard for any origin in production
    CORS_ALLOW_ALL: bool = os.getenv("CORS_ALLOW_ALL", "false").lower() == "true"
    CORS_ORIGINS_REGEX: str = r"https?://localhost:\d+"  # Allow any localhost port
    
    # WebSocket Settings
    WS_URL: str = "ws://localhost:8000/ws"
    
    # Security
    SECRET_KEY: str = "your-secret-key-here"  # TODO: Change in production
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    # Spotify
    SPOTIFY_CLIENT_ID: Optional[str] = os.getenv("SPOTIFY_CLIENT_ID", None)
    SPOTIFY_CLIENT_SECRET: Optional[str] = os.getenv("SPOTIFY_CLIENT_SECRET", None)
    
    # YouTube settings
    YOUTUBE_PO_TOKEN: Optional[str] = None
    YOUTUBE_SESSION_TOKEN: Optional[str] = None
    YOUTUBE_COOKIE_FILE: Optional[str] = "youtube.cookies"
    
    # Strategy settings
    STRATEGY_MAX_FAILURES: int = 3
    STRATEGY_FAILURE_RESET_TIME: int = 300  # seconds
    STRATEGY_RETRY_DELAY: int = 1  # seconds
    
    # Logging settings
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Download settings
    DOWNLOADS_DIR: Path = Path(os.getenv("DOWNLOADS_DIR", "downloads"))
    TEMP_DIR: Path = Path(os.getenv("TEMP_DIR", "temp"))
    MAX_CONCURRENT_DOWNLOADS: int = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "3"))
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        env_nested_delimiter="__",
        extra="allow"  # Allow extra fields from environment variables
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Handle CORS origins parsing more robustly
        cors_env = os.getenv("CORS_ORIGINS")
        if cors_env:
            try:
                # Try to parse as JSON first
                import json
                self.CORS_ORIGINS = json.loads(cors_env)
                logger.info("Parsed CORS_ORIGINS as JSON")
            except json.JSONDecodeError:
                # If not valid JSON, try comma-separated format
                self.CORS_ORIGINS = [origin.strip() for origin in cors_env.split(",") if origin.strip()]
                logger.info("Parsed CORS_ORIGINS as comma-separated string")
        else:
            # Default origins
            self.CORS_ORIGINS = [
                "http://localhost:5173",  # Vite dev server
                "http://localhost:8000",  # FastAPI server
                "http://localhost:3000",  # Alternative frontend port
                "https://slimthicc-commandcenter.netlify.app",  # Production Netlify domain
            ]
            logger.info("Using default CORS_ORIGINS")
        
        # Clean up CORS origins (remove empty strings)
        self.CORS_ORIGINS = [origin for origin in self.CORS_ORIGINS if origin and isinstance(origin, str)]
        
        # Log CORS settings
        if self.CORS_ALLOW_ALL:
            logger.warning("CORS is configured to allow all origins (*)! This is not recommended for production.")
            # Add wildcard to origins if allowing all
            if "*" not in self.CORS_ORIGINS:
                self.CORS_ORIGINS.append("*")
        
        logger.info(f"CORS origins: {self.CORS_ORIGINS}")
        
        # Log Spotify credentials status
        if self.SPOTIFY_CLIENT_ID and self.SPOTIFY_CLIENT_SECRET:
            logger.info("Spotify API credentials found")
            # Mask credentials in logs
            client_id_masked = f"{self.SPOTIFY_CLIENT_ID[:4]}...{self.SPOTIFY_CLIENT_ID[-4:]}" if len(self.SPOTIFY_CLIENT_ID) > 8 else "***"
            client_secret_masked = f"{self.SPOTIFY_CLIENT_SECRET[:4]}...{self.SPOTIFY_CLIENT_SECRET[-4:]}" if len(self.SPOTIFY_CLIENT_SECRET) > 8 else "***"
            logger.debug(f"Spotify client ID: {client_id_masked}")
            logger.debug(f"Spotify client secret: {client_secret_masked}")
        else:
            missing = []
            if not self.SPOTIFY_CLIENT_ID:
                missing.append("SPOTIFY_CLIENT_ID")
            if not self.SPOTIFY_CLIENT_SECRET:
                missing.append("SPOTIFY_CLIENT_SECRET")
            logger.warning(f"Spotify API credentials incomplete. Missing: {', '.join(missing)}")
        
        # Ensure download directories exist
        logger.info(f"Setting up download directories: {self.DOWNLOADS_DIR}, {self.TEMP_DIR}")
        self.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        self.TEMP_DIR.mkdir(parents=True, exist_ok=True)
        
        # Convert relative paths to absolute if needed
        if not self.DOWNLOADS_DIR.is_absolute():
            self.DOWNLOADS_DIR = Path.cwd() / self.DOWNLOADS_DIR
            logger.debug(f"Using absolute downloads directory: {self.DOWNLOADS_DIR}")
        if not self.TEMP_DIR.is_absolute():
            self.TEMP_DIR = Path.cwd() / self.TEMP_DIR
            logger.debug(f"Using absolute temp directory: {self.TEMP_DIR}")
            
        # Load YouTube tokens from environment if available
        if not self.YOUTUBE_PO_TOKEN:
            self.YOUTUBE_PO_TOKEN = os.getenv("YOUTUBE_PO_TOKEN")
        if not self.YOUTUBE_SESSION_TOKEN:
            self.YOUTUBE_SESSION_TOKEN = os.getenv("YOUTUBE_SESSION_TOKEN")
            
        # Convert cookie file path to absolute if specified
        if self.YOUTUBE_COOKIE_FILE and not Path(self.YOUTUBE_COOKIE_FILE).is_absolute():
            self.YOUTUBE_COOKIE_FILE = str(Path.cwd() / self.YOUTUBE_COOKIE_FILE)
            
        logger.info("Settings initialized successfully")

settings = Settings() 