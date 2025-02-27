import logging
from fastapi import WebSocket
from typing import Dict, List, Any, Optional
import asyncio

logger = logging.getLogger(__name__)

class WebsocketManager:
    """
    WebSocket manager for handling real-time connections
    """
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.connection_lock = asyncio.Lock()
        logger.info("Initialized WebSocket manager")
    
    async def connect(self, websocket: WebSocket, client_id: str):
        """
        Accept and store a websocket connection
        
        Args:
            websocket: The WebSocket instance
            client_id: The client ID to associate with the connection
        """
        try:
            # Accept the connection before acquiring lock to prevent deadlock
            await websocket.accept()
            
            # Use lock to prevent race conditions during connection management
            async with self.connection_lock:
                if client_id not in self.active_connections:
                    self.active_connections[client_id] = []
                
                # Check if this WebSocket instance is already in the list
                # This can happen if there are multiple connect calls for the same WebSocket
                for existing_ws in self.active_connections[client_id]:
                    if id(existing_ws) == id(websocket):
                        logger.warning(f"WebSocket for {client_id} already connected (same instance)")
                        return True
                
                self.active_connections[client_id].append(websocket)
                logger.info(f"WebSocket connected: {client_id} (total connections: {len(self.active_connections[client_id])})")
                
                # Debug connection info
                logger.info(f"Active clients: {list(self.active_connections.keys())}")
                total_connections = sum(len(connections) for connections in self.active_connections.values())
                logger.info(f"Total active connections: {total_connections}")
            
            return True
        except Exception as e:
            logger.error(f"Error connecting WebSocket for {client_id}: {e}", exc_info=True)
            # Try to accept again if not accepted
            try:
                if websocket.client_state.name.lower() != "connected":
                    await websocket.accept()
            except Exception:
                pass
            return False
    
    async def disconnect(self, websocket: WebSocket, client_id: str):
        """
        Remove a websocket connection
        
        Args:
            websocket: The WebSocket instance
            client_id: The client ID associated with the connection
        """
        try:
            async with self.connection_lock:
                if client_id in self.active_connections:
                    if websocket in self.active_connections[client_id]:
                        self.active_connections[client_id].remove(websocket)
                        logger.info(f"WebSocket removed for {client_id} (remaining: {len(self.active_connections[client_id])})")
                    
                    # Clean up empty client entries
                    if not self.active_connections[client_id]:
                        del self.active_connections[client_id]
                        logger.info(f"Removed empty client entry for {client_id}")
                    
                    # Debug connection info
                    logger.info(f"Active clients after disconnect: {list(self.active_connections.keys())}")
                    total_connections = sum(len(connections) for connections in self.active_connections.values())
                    logger.info(f"Total active connections after disconnect: {total_connections}")
                else:
                    logger.warning(f"Attempted to disconnect non-existent client: {client_id}")
            
            # Close the WebSocket if still open
            try:
                if websocket.client_state.name.lower() == "connected":
                    await websocket.close()
            except Exception as close_error:
                logger.warning(f"Error closing WebSocket for {client_id}: {close_error}")
            
            return True
        except Exception as e:
            logger.error(f"Error disconnecting WebSocket for {client_id}: {e}", exc_info=True)
            return False
    
    async def send_message(self, client_id: str, message: Dict[str, Any]):
        """
        Send a message to a specific client
        
        Args:
            client_id: The client ID to send to
            message: The message to send
        """
        sent_count = 0
        error_count = 0
        
        if client_id in self.active_connections:
            logger.debug(f"Sending message to {client_id} (connections: {len(self.active_connections[client_id])})")
            
            # Create a list to store WebSockets to remove due to errors
            to_remove = []
            
            for connection in self.active_connections[client_id]:
                try:
                    await connection.send_json(message)
                    sent_count += 1
                    logger.debug(f"Sent message to {client_id}: {message}")
                except Exception as e:
                    error_count += 1
                    logger.error(f"Error sending message to {client_id}: {e}")
                    # Mark this connection for removal
                    to_remove.append(connection)
            
            # Remove any failed connections
            if to_remove:
                async with self.connection_lock:
                    for connection in to_remove:
                        if connection in self.active_connections[client_id]:
                            self.active_connections[client_id].remove(connection)
                            logger.info(f"Removed failed connection for {client_id}")
                    
                    # Clean up empty client entries
                    if not self.active_connections[client_id]:
                        del self.active_connections[client_id]
                        logger.info(f"Removed empty client entry for {client_id}")
        else:
            logger.warning(f"No active connections for client {client_id}")
        
        return sent_count > 0
    
    async def broadcast(self, message: Dict[str, Any]):
        """
        Broadcast a message to all connected clients
        
        Args:
            message: The message to broadcast
        """
        sent_count = 0
        error_count = 0
        clients_to_clean = []
        
        # Copy the keys to avoid modification during iteration
        client_ids = list(self.active_connections.keys())
        
        for client_id in client_ids:
            # Create a list to store WebSockets to remove due to errors
            to_remove = []
            
            for connection in self.active_connections.get(client_id, []):
                try:
                    await connection.send_json(message)
                    sent_count += 1
                except Exception as e:
                    error_count += 1
                    logger.error(f"Error broadcasting to {client_id}: {e}")
                    # Mark this connection for removal
                    to_remove.append(connection)
            
            # Schedule this client for cleanup if there are failed connections
            if to_remove:
                clients_to_clean.append((client_id, to_remove))
        
        # Clean up failed connections
        if clients_to_clean:
            async with self.connection_lock:
                for client_id, connections in clients_to_clean:
                    if client_id in self.active_connections:
                        for connection in connections:
                            if connection in self.active_connections[client_id]:
                                self.active_connections[client_id].remove(connection)
                        
                        # Clean up empty client entries
                        if not self.active_connections[client_id]:
                            del self.active_connections[client_id]
        
        return sent_count > 0
        
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
            connections = self.active_connections.get(task_id, [])
            connection_count = len(connections)
            
            logger.debug(f"Broadcasting progress for task {task_id}: {progress}% ({status}) to {connection_count} connections")
            logger.debug(f"Message content: {message}")
            
            if connection_count == 0:
                logger.warning(f"No active connections for client {task_id}")
            
            return await self.send_message(task_id, message)
        except Exception as e:
            logger.error(f"Error broadcasting progress for task {task_id}: {e}", exc_info=True)
            return False


# Create a global instance
websocket_manager = WebsocketManager() 