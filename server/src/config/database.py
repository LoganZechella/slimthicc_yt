from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.database import Database
from .settings import settings
import logging
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)

class DatabaseClient:
    def __init__(self):
        self._client = None
        self._db = None
        self.connected = False
        logger.info("Initialized database client")
    
    @property
    def client(self):
        return self._client
    
    @client.setter
    def client(self, value):
        self._client = value
    
    @property
    def db(self) -> Database:
        return self._db
    
    @db.setter
    def db(self, value):
        self._db = value
    
    @property
    def is_connected(self):
        return self.connected and self._client is not None

# Create a database instance
db = DatabaseClient()

async def connect_to_mongo():
    try:
        # Ensure we're running in an event loop
        loop = asyncio.get_running_loop()
        
        # Close existing connection if any
        if db.client:
            await close_mongo_connection()
        
        # Use the MongoDB Atlas URL directly
        mongo_url = settings.MONGODB_URL
        logger.info(f"Connecting to MongoDB Atlas cluster")
        
        # Create new client with proper settings
        db.client = AsyncIOMotorClient(
            mongo_url,
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
        db.connected = True
        
        logger.info(f"Connected to MongoDB Atlas at {mongo_url.split('@')[1] if '@' in mongo_url else 'mongodb atlas'}")
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
            db.connected = False
            logger.info("Closed MongoDB connection")
    except Exception as e:
        logger.error(f"Error closing MongoDB connection: {e}")

async def ensure_connection():
    """Ensure MongoDB connection is active."""
    if not db.is_connected:
        await connect_to_mongo()
    return db.db 