from datetime import datetime
from enum import Enum
from typing import Optional, Any, Dict, List
from pydantic import BaseModel, Field, HttpUrl
import uuid

class DownloadStatus(str, Enum):
    """Download task status."""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    COMPLETE = "complete"
    ERROR = "error"
    CANCELLED = "cancelled"

class DownloadFormat(str, Enum):
    MP3 = "mp3"
    M4A = "m4a"

class AudioQuality(str, Enum):
    """Audio quality options."""
    HIGH = "320k"
    MEDIUM = "192k"
    LOW = "128k"

class DownloadRequest(BaseModel):
    url: str
    format: DownloadFormat = Field(default=DownloadFormat.MP3)
    quality: AudioQuality = Field(default=AudioQuality.HIGH)

class DownloadResponse(BaseModel):
    task_id: str

class DownloadError(Exception):
    """Custom exception for download errors."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

class DownloadTaskCreate(BaseModel):
    """Download task creation model."""
    url: str
    quality: Optional[str] = None

class DownloadTaskResponse(BaseModel):
    """Download task response."""
    id: str
    url: str
    title: str
    author: str
    status: DownloadStatus
    progress: float = 0
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    quality: Optional[str] = None
    output_path: Optional[str] = None

class DownloadTask(BaseModel):
    """Download task model."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    url: str
    title: str
    author: str
    status: DownloadStatus = Field(default=DownloadStatus.PENDING)
    quality: Optional[str] = None
    progress: float = Field(default=0.0, ge=0.0, le=100.0)
    error: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None
    output_path: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    retry_count: int = Field(default=0)
    strategy_attempts: List[Dict[str, Any]] = Field(default_factory=list)

    def to_response(self) -> DownloadTaskResponse:
        """Convert to response model."""
        return DownloadTaskResponse(
            id=self.id,
            url=self.url,
            title=self.title,
            author=self.author,
            status=self.status,
            progress=self.progress,
            error=self.error,
            created_at=self.created_at,
            updated_at=self.updated_at,
            quality=self.quality,
            output_path=self.output_path
        )

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        
        # Allow population by field name for MongoDB
        populate_by_name = True
        
        # Additional MongoDB-specific configuration
        extra = "allow"  # Allow extra fields from MongoDB
        
        # Custom JSON schema
        schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "title": "Never Gonna Give You Up",
                "author": "Rick Astley",
                "status": "pending",
                "quality": "192k",
                "progress": 0.0,
                "created_at": "2024-02-23T12:34:56.789Z",
                "updated_at": "2024-02-23T12:34:56.789Z"
            }
        } 