import logging
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List, Any, Optional
import asyncio
import time
import json

logger = logging.getLogger(__name__)

class WebsocketManager:
    """
    WebSocket manager for handling real-time connections with improved resilience
    """
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.connection_timestamps: Dict[str, Dict[WebSocket, float]] = {}
        self.connection_lock = asyncio.Lock()
        self.ping_interval = 30  # seconds
        self.ping_task = None
        logger.info("Initialized WebSocket manager with improved resilience")
    
    async def connect(self, websocket: WebSocket, client_id: str):
        """
        Accept and store a websocket connection
        
        Args:
            websocket: The WebSocket instance
            client_id: The client ID to associate with the connection
        """
        try:
            # Accept the connection before acquiring lock to prevent deadlock
            try:
                if websocket.client_state.name.lower() != "connected":
                    await websocket.accept()
                    logger.debug(f"WebSocket connection accepted for client {client_id}")
            except Exception as accept_error:
                logger.error(f"Error accepting WebSocket for {client_id}: {accept_error}", exc_info=True)
                return False
            
            # Use lock to prevent race conditions during connection management
            async with self.connection_lock:
                # Initialize client connections list if not exists
                if client_id not in self.active_connections:
                    self.active_connections[client_id] = []
                    self.connection_timestamps[client_id] = {}
                
                # Check if this WebSocket instance is already in the list
                # This can happen if there are multiple connect calls for the same WebSocket
                for existing_ws in self.active_connections[client_id]:
                    if id(existing_ws) == id(websocket):
                        logger.warning(f"WebSocket for {client_id} already connected (same instance)")
                        return True
                
                # Add new connection
                self.active_connections[client_id].append(websocket)
                self.connection_timestamps[client_id][websocket] = time.time()
                
                logger.info(f"WebSocket connected: {client_id} (total connections: {len(self.active_connections[client_id])})")
                
                # Log connection info
                logger.info(f"Active clients: {list(self.active_connections.keys())}")
                total_connections = sum(len(connections) for connections in self.active_connections.values())
                logger.info(f"Total active connections: {total_connections}")
                
                # Start ping task if not already running
                if self.ping_task is None or self.ping_task.done():
                    self.ping_task = asyncio.create_task(self._ping_connections())
            
            # Send a welcome message to confirm connection
            try:
                await websocket.send_json({
                    "type": "connection_status",
                    "status": "connected",
                    "message": f"Connected to task {client_id}"
                })
                logger.debug(f"Welcome message sent to client {client_id}")
            except Exception as welcome_error:
                logger.error(f"Error sending welcome message to {client_id}: {welcome_error}")
            
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
                        
                        # Clean up timestamp entry
                        if client_id in self.connection_timestamps and websocket in self.connection_timestamps[client_id]:
                            del self.connection_timestamps[client_id][websocket]
                    
                    # Clean up empty client entries
                    if not self.active_connections[client_id]:
                        del self.active_connections[client_id]
                        if client_id in self.connection_timestamps:
                            del self.connection_timestamps[client_id]
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
                    logger.debug(f"WebSocket connection closed for {client_id}")
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
                    
                    # Update last activity timestamp
                    if client_id in self.connection_timestamps:
                        self.connection_timestamps[client_id][connection] = time.time()
                except Exception as e:
                    error_count += 1
                    logger.error(f"Error sending message to {client_id}: {e}")
                    # Mark this connection for removal
                    to_remove.append(connection)
            
            # Remove any failed connections
            if to_remove:
                async with self.connection_lock:
                    for connection in to_remove:
                        if client_id in self.active_connections and connection in self.active_connections[client_id]:
                            self.active_connections[client_id].remove(connection)
                            # Clean up timestamp entry
                            if client_id in self.connection_timestamps and connection in self.connection_timestamps[client_id]:
                                del self.connection_timestamps[client_id][connection]
                            logger.info(f"Removed failed connection for {client_id}")
                    
                    # Clean up empty client entries
                    if client_id in self.active_connections and not self.active_connections[client_id]:
                        del self.active_connections[client_id]
                        if client_id in self.connection_timestamps:
                            del self.connection_timestamps[client_id]
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
                    
                    # Update last activity timestamp
                    if client_id in self.connection_timestamps:
                        self.connection_timestamps[client_id][connection] = time.time()
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
                                # Clean up timestamp entry
                                if client_id in self.connection_timestamps and connection in self.connection_timestamps[client_id]:
                                    del self.connection_timestamps[client_id][connection]
                        
                        # Clean up empty client entries
                        if not self.active_connections[client_id]:
                            del self.active_connections[client_id]
                            if client_id in self.connection_timestamps:
                                del self.connection_timestamps[client_id]
        
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
    
    async def _ping_connections(self):
        """
        Periodically ping active connections to keep them alive
        """
        logger.info("Starting WebSocket ping service")
        
        try:
            while True:
                # Wait between pings
                await asyncio.sleep(self.ping_interval)
                
                # Skip if no connections
                if not self.active_connections:
                    continue
                
                logger.debug("Sending ping to active WebSocket connections")
                
                # Create a ping message
                ping_message = {
                    "type": "ping",
                    "timestamp": time.time()
                }
                
                # Store pending disconnect operations
                to_disconnect = []
                
                # Loop through all clients
                for client_id, connections in list(self.active_connections.items()):
                    if not connections:
                        continue
                    
                    # Loop through all connections for this client
                    for connection in list(connections):
                        try:
                            # Check if connection is still alive
                            if connection.client_state.name.lower() != "connected":
                                logger.warning(f"Found dead connection for {client_id}, will remove")
                                to_disconnect.append((connection, client_id))
                                continue
                            
                            # Send ping message
                            await connection.send_json(ping_message)
                            
                            # Update timestamp
                            if client_id in self.connection_timestamps:
                                self.connection_timestamps[client_id][connection] = time.time()
                            
                            logger.debug(f"Sent ping to client {client_id}")
                        except Exception as e:
                            logger.warning(f"Error pinging WebSocket for {client_id}: {e}")
                            to_disconnect.append((connection, client_id))
                
                # Disconnect failed connections
                for connection, client_id in to_disconnect:
                    logger.info(f"Disconnecting failed WebSocket for {client_id}")
                    try:
                        await self.disconnect(connection, client_id)
                    except Exception as e:
                        logger.error(f"Error disconnecting WebSocket for {client_id}: {e}")
                
                # Log active connections
                total_connections = sum(len(connections) for connections in self.active_connections.values())
                if total_connections > 0:
                    logger.info(f"Active WebSocket connections after ping: {total_connections} across {len(self.active_connections)} clients")
        
        except asyncio.CancelledError:
            logger.info("WebSocket ping service was cancelled")
        except Exception as e:
            logger.error(f"Error in WebSocket ping service: {e}", exc_info=True)


# Create a global instance
websocket_manager = WebsocketManager() 