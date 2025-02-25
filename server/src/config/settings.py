from pydantic_settings import BaseSettings
from dotenv import load_dotenv
import os
from typing import Optional, List
from pathlib import Path

load_dotenv()

class Settings(BaseSettings):
    # API Settings
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "SlimThicc Music Downloader"
    VERSION: str = "1.0.0"
    
    # Server Settings
    HOST: str = "localhost"
    PORT: int = 8000
    DEBUG: bool = True  # Changed from 'WARN' to True
    
    # MongoDB Settings
    MONGODB_URL: str = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    MONGODB_DB_NAME: str = os.getenv("MONGODB_DB_NAME", "slimthicc_command_center")
    
    # CORS Settings
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",  # Vite dev server
        "http://localhost:8000",  # FastAPI server
        "http://localhost:3000",  # Alternative frontend port
    ]
    CORS_ORIGINS_REGEX: str = r"https?://localhost:\d+"  # Allow any localhost port
    
    # WebSocket Settings
    WS_URL: str = "ws://localhost:8000/ws"
    
    # Security
    SECRET_KEY: str = "your-secret-key-here"  # TODO: Change in production
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    # Spotify
    SPOTIFY_CLIENT_ID: Optional[str] = None
    SPOTIFY_CLIENT_SECRET: Optional[str] = None
    
    # YouTube settings
    YOUTUBE_PO_TOKEN: Optional[str] = None
    YOUTUBE_SESSION_TOKEN: Optional[str] = None
    YOUTUBE_COOKIE_FILE: Optional[str] = "youtube.cookies"
    
    # Invidious settings
    INVIDIOUS_API_URL: str = "https://invidious.snopyta.org"  # Default instance
    INVIDIOUS_FALLBACK_INSTANCES: list[str] = [
        "https://invidious.kavin.rocks",
        "https://invidious.namazso.eu",
        "https://inv.riverside.rocks",
        "https://yt.artemislena.eu",
        "https://invidious.flokinet.to",
        "https://invidious.projectsegfau.lt"
    ]
    INVIDIOUS_REQUEST_TIMEOUT: int = 30
    INVIDIOUS_MIN_REQUEST_INTERVAL: float = 2.0
    
    # Strategy settings
    STRATEGY_MAX_FAILURES: int = 3
    STRATEGY_FAILURE_RESET_TIME: int = 300  # seconds
    STRATEGY_RETRY_DELAY: int = 1  # seconds
    
    # FFmpeg settings
    FFMPEG_PATH: Optional[str] = None
    FFMPEG_THREADS: int = 0  # 0 means auto
    FFMPEG_LOGLEVEL: str = "warning"
    
    # Logging settings
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Download settings
    DOWNLOADS_DIR: Path = Path("downloads")
    TEMP_DIR: Path = Path("temp")
    DEFAULT_AUDIO_QUALITY: str = "192k"
    MAX_CONCURRENT_DOWNLOADS: int = 3
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"  # Allow extra fields from environment variables

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Ensure download directories exist
        self.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        self.TEMP_DIR.mkdir(parents=True, exist_ok=True)
        
        # Convert relative paths to absolute if needed
        if not self.DOWNLOADS_DIR.is_absolute():
            self.DOWNLOADS_DIR = Path.cwd() / self.DOWNLOADS_DIR
        if not self.TEMP_DIR.is_absolute():
            self.TEMP_DIR = Path.cwd() / self.TEMP_DIR
            
        # Set FFmpeg path if not specified
        if not self.FFMPEG_PATH:
            self.FFMPEG_PATH = "ffmpeg"  # Use system FFmpeg
            
        # Load YouTube tokens from environment if available
        if not self.YOUTUBE_PO_TOKEN:
            self.YOUTUBE_PO_TOKEN = os.getenv("YOUTUBE_PO_TOKEN")
        if not self.YOUTUBE_SESSION_TOKEN:
            self.YOUTUBE_SESSION_TOKEN = os.getenv("YOUTUBE_SESSION_TOKEN")
            
        # Convert cookie file path to absolute if specified
        if self.YOUTUBE_COOKIE_FILE and not Path(self.YOUTUBE_COOKIE_FILE).is_absolute():
            self.YOUTUBE_COOKIE_FILE = str(Path.cwd() / self.YOUTUBE_COOKIE_FILE)

settings = Settings() 