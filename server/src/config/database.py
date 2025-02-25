from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.database import Database
from .settings import settings
import logging
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)

class MongoDB:
    client: Optional[AsyncIOMotorClient] = None
    db: Optional[Database] = None
    
    @property
    def is_connected(self) -> bool:
        return self.client is not None and self.db is not None

db = MongoDB()

async def connect_to_mongo():
    try:
        # Ensure we're running in an event loop
        loop = asyncio.get_running_loop()
        
        # Close existing connection if any
        if db.client:
            await close_mongo_connection()
        
        # Create new client with proper settings
        db.client = AsyncIOMotorClient(
            settings.MONGODB_URL,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=10000,
            socketTimeoutMS=None,  # No timeout for operations
            maxPoolSize=50,
            minPoolSize=10,
            maxIdleTimeMS=50000,
            waitQueueTimeoutMS=10000
        )
        
        # Test connection
        await db.client.admin.command('ping')
        
        # Set database
        db.db = db.client[settings.MONGODB_DB_NAME]
        
        logger.info(f"Connected to MongoDB at {settings.MONGODB_URL}")
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        if db.client:
            await close_mongo_connection()
        raise

async def close_mongo_connection():
    try:
        if db.client:
            db.client.close()
            db.client = None
            db.db = None
            logger.info("Closed MongoDB connection")
    except Exception as e:
        logger.error(f"Error closing MongoDB connection: {e}")

async def ensure_connection():
    """Ensure MongoDB connection is active."""
    if not db.is_connected:
        await connect_to_mongo()
    return db.db 