import logging
from fastapi import WebSocket
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

class WebsocketManager:
    """
    WebSocket manager for handling real-time connections
    """
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        logger.info("Initialized WebSocket manager")
    
    async def connect(self, websocket: WebSocket, client_id: str):
        """
        Accept and store a websocket connection
        
        Args:
            websocket: The WebSocket instance
            client_id: The client ID to associate with the connection
        """
        await websocket.accept()
        if client_id not in self.active_connections:
            self.active_connections[client_id] = []
        self.active_connections[client_id].append(websocket)
        logger.info(f"WebSocket connected: {client_id}")
        return True
    
    async def disconnect(self, websocket: WebSocket, client_id: str):
        """
        Remove a websocket connection
        
        Args:
            websocket: The WebSocket instance
            client_id: The client ID associated with the connection
        """
        if client_id in self.active_connections:
            if websocket in self.active_connections[client_id]:
                self.active_connections[client_id].remove(websocket)
            if not self.active_connections[client_id]:
                del self.active_connections[client_id]
        logger.info(f"WebSocket disconnected: {client_id}")
        return True
    
    async def send_message(self, client_id: str, message: Dict[str, Any]):
        """
        Send a message to a specific client
        
        Args:
            client_id: The client ID to send to
            message: The message to send
        """
        if client_id in self.active_connections:
            for connection in self.active_connections[client_id]:
                try:
                    await connection.send_json(message)
                    logger.debug(f"Sent message to {client_id}: {message}")
                except Exception as e:
                    logger.error(f"Error sending message to {client_id}: {e}")
        else:
            logger.warning(f"No active connections for client {client_id}")
        return True
    
    async def broadcast(self, message: Dict[str, Any]):
        """
        Broadcast a message to all connected clients
        
        Args:
            message: The message to broadcast
        """
        for client_id, connections in self.active_connections.items():
            for connection in connections:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Error broadcasting to {client_id}: {e}")
        return True
        
    async def broadcast_progress(self, task_id: str, progress: float, status: str, details: Optional[Any] = None, error: Optional[str] = None):
        """
        Broadcast download progress for a specific task
        
        Args:
            task_id: The task ID
            progress: Progress percentage (0-100)
            status: Task status (downloading, processing, complete, error)
            details: Optional details to include in the message (string or dict)
            error: Optional error message if status is 'error'
        """
        message = {
            "progress": progress,
            "status": status
        }
        
        if details is not None:
            message["details"] = details
            
        if error:
            message["error"] = error
        
        try:
            logger.debug(f"Broadcasting progress for task {task_id}: {progress}% ({status})")
            logger.debug(f"Message content: {message}")
            return await self.send_message(task_id, message)
        except Exception as e:
            logger.error(f"Error broadcasting progress for task {task_id}: {e}")
            return False


# Create a global instance
websocket_manager = WebsocketManager() 