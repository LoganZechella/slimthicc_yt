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
        self.active_connections = {}  # client_id -> list of websocket connections
        self.connection_timestamps = {}  # client_id -> {websocket: timestamp}
        self.connection_lock = asyncio.Lock()  # Lock for thread-safe operations
        self.service_task = None  # Background task for ping service
        self.logger = logging.getLogger("services.websocket_manager")
        self.ping_interval = 30  # seconds
        self.ping_task = None
        logger.info("Initialized WebSocket manager with improved resilience")
    
    async def connect(self, websocket: WebSocket, client_id: str) -> bool:
        """
        Register a new WebSocket connection for a specific client
        
        Args:
            websocket: The WebSocket connection
            client_id: A unique identifier for the client
            
        Returns:
            bool: True if connection successfully registered, False otherwise
        """
        try:
            async with self.connection_lock:
                # Initialize if this is the first connection for this client
                if client_id not in self.active_connections:
                    self.active_connections[client_id] = []
                    self.connection_timestamps[client_id] = {}
                
                # Add the connection to the client's list if not already present
                if websocket not in self.active_connections[client_id]:
                    self.active_connections[client_id].append(websocket)
                    self.connection_timestamps[client_id][websocket] = time.time()
            
            # Start the ping service if not already running
            if self.service_task is None or self.service_task.done():
                self.service_task = asyncio.create_task(self._ping_service())
                self.logger.info("Starting WebSocket ping service")
            
            # Log connection info
            total_connections = sum(len(connections) for connections in self.active_connections.values())
            self.logger.info(f"WebSocket connected: {client_id} (total connections: {total_connections})")
            self.logger.info(f"Active clients: {list(self.active_connections.keys())}")
            self.logger.info(f"Total active connections: {total_connections}")
            
            return True
        except Exception as e:
            self.logger.error(f"Error connecting WebSocket for client {client_id}: {e}", exc_info=True)
            return False
    
    async def disconnect(self, websocket: WebSocket, client_id: str) -> bool:
        """
        Unregister a WebSocket connection
        
        Args:
            websocket: The WebSocket connection to remove
            client_id: The client's unique identifier
            
        Returns:
            bool: True if successfully removed, False otherwise
        """
        try:
            async with self.connection_lock:
                if client_id in self.active_connections:
                    if websocket in self.active_connections[client_id]:
                        self.active_connections[client_id].remove(websocket)
                        if websocket in self.connection_timestamps[client_id]:
                            del self.connection_timestamps[client_id][websocket]
                        
                        self.logger.info(f"WebSocket removed for {client_id} (remaining: {len(self.active_connections[client_id])})")
                        
                        # If this was the last connection for this client, remove the client
                        if not self.active_connections[client_id]:
                            del self.active_connections[client_id]
                            del self.connection_timestamps[client_id]
                            self.logger.info(f"Removed empty client entry for {client_id}")
                    
                    self.logger.info(f"Active clients after disconnect: {list(self.active_connections.keys())}")
                    total_connections = sum(len(connections) for connections in self.active_connections.values())
                    self.logger.info(f"Total active connections after disconnect: {total_connections}")
                    
                    # Stop ping service if no connections left
                    if not self.active_connections and self.service_task and not self.service_task.done():
                        self.service_task.cancel()
                        self.logger.info("Stopping WebSocket ping service - no active connections")
                        
                    return True
                return False
        except Exception as e:
            self.logger.error(f"Error disconnecting WebSocket for client {client_id}: {e}", exc_info=True)
            return False
    
    async def broadcast(self, client_id: str, message: dict):
        """
        Broadcast a message to all active connections for a specific client
        
        Args:
            client_id: The client's unique identifier
            message: The message to broadcast
        """
        disconnected_websockets = []
        
        async with self.connection_lock:
            # Check if there are active connections for this client
            if client_id not in self.active_connections or not self.active_connections[client_id]:
                self.logger.warning(f"No active connections for client {client_id} - broadcast will be skipped")
                return
                
            # Broadcast the message to all active connections
            for websocket in self.active_connections[client_id]:
                try:
                    # Add broadcast timestamp for debugging latency
                    message_with_timestamp = {
                        **message,
                        "server_broadcast_timestamp": time.time()
                    }
                    await websocket.send_json(message_with_timestamp)
                except Exception as e:
                    self.logger.error(f"Error broadcasting to WebSocket: {e}")
                    disconnected_websockets.append(websocket)
        
        # Remove any disconnected websockets
        if disconnected_websockets:
            async with self.connection_lock:
                if client_id in self.active_connections:
                    for websocket in disconnected_websockets:
                        if websocket in self.active_connections[client_id]:
                            self.active_connections[client_id].remove(websocket)
                            if websocket in self.connection_timestamps[client_id]:
                                del self.connection_timestamps[client_id][websocket]
                            self.logger.warning(f"Removed disconnected WebSocket for client {client_id}")
                    
                    # If this was the last connection for this client, remove the client
                    if not self.active_connections[client_id]:
                        del self.active_connections[client_id]
                        del self.connection_timestamps[client_id]
                        self.logger.info(f"Removed empty client entry for {client_id} after failed broadcast")
    
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
            # Check if the connection is established before attempting to send
            async with self.connection_lock:
                connections = self.active_connections.get(task_id, [])
                connection_count = len(connections)
                
                # Log connection status
                logger.debug(f"Broadcasting progress for task {task_id}: {progress}% ({status}) to {connection_count} connections")
                logger.debug(f"Message content: {message}")
                
                if connection_count == 0:
                    # Instead of just warning, add to a queue for later delivery or retry
                    logger.warning(f"No active connections for client {task_id} - broadcast will be skipped")
                    # Store last message to be sent when connection is established
                    # This could be expanded into a more robust queuing system if needed
                    logger.debug(f"Would be broadcasting message: {message}")
                    return False
                
                # Only proceed if we have connections to avoid unnecessary processing
                if connection_count > 0:
                    # Create a list to track connections with issues
                    problematic_connections = []
                    
                    # Send to each connection
                    for connection in connections:
                        try:
                            # Verify the connection is still valid
                            if connection.client_state.name.lower() != "connected":
                                logger.warning(f"Connection for {task_id} is not in connected state ({connection.client_state.name})")
                                problematic_connections.append(connection)
                                continue
                            
                            # Send message
                            await connection.send_json(message)
                            
                            # Update last activity timestamp
                            if task_id in self.connection_timestamps:
                                self.connection_timestamps[task_id][connection] = time.time()
                        except Exception as e:
                            logger.error(f"Error sending to specific connection for {task_id}: {e}")
                            problematic_connections.append(connection)
                    
                    # Remove problematic connections
                    if problematic_connections:
                        for prob_conn in problematic_connections:
                            if task_id in self.active_connections and prob_conn in self.active_connections[task_id]:
                                self.active_connections[task_id].remove(prob_conn)
                                if task_id in self.connection_timestamps and prob_conn in self.connection_timestamps[task_id]:
                                    del self.connection_timestamps[task_id][prob_conn]
                                logger.info(f"Removed problematic connection for {task_id}")
                        
                        # Clean up empty client entries
                        if task_id in self.active_connections and not self.active_connections[task_id]:
                            del self.active_connections[task_id]
                            if task_id in self.connection_timestamps:
                                del self.connection_timestamps[task_id]
                            logger.info(f"Removed empty client entry for {task_id}")
                    
                    # Return success if at least one message was sent
                    return len(problematic_connections) < connection_count
                
                return False
        except Exception as e:
            logger.error(f"Error in broadcast_progress for task {task_id}: {e}", exc_info=True)
            return False
    
    async def _ping_service(self):
        """Background service to ping all connections periodically to keep them alive"""
        try:
            ping_interval = 10  # seconds
            self.logger.info(f"Starting ping service with {ping_interval}s interval")
            
            while True:
                await asyncio.sleep(ping_interval)
                
                # Make a copy of active_connections to avoid modification during iteration
                async with self.connection_lock:
                    clients_to_ping = {
                        client_id: list(connections) 
                        for client_id, connections in self.active_connections.items()
                    }
                
                # Track websockets that failed to respond to ping
                disconnected_websockets = {}
                
                # Send ping to all active connections
                for client_id, websockets in clients_to_ping.items():
                    for websocket in websockets:
                        try:
                            ping_message = {
                                "type": "ping",
                                "timestamp": time.time()
                            }
                            await websocket.send_json(ping_message)
                        except Exception as e:
                            if client_id not in disconnected_websockets:
                                disconnected_websockets[client_id] = []
                            disconnected_websockets[client_id].append(websocket)
                            self.logger.warning(f"Ping failed for client {client_id}: {e}")
                
                # Clean up disconnected websockets
                if disconnected_websockets:
                    async with self.connection_lock:
                        for client_id, websockets in disconnected_websockets.items():
                            if client_id in self.active_connections:
                                for websocket in websockets:
                                    if websocket in self.active_connections[client_id]:
                                        self.active_connections[client_id].remove(websocket)
                                        if websocket in self.connection_timestamps[client_id]:
                                            del self.connection_timestamps[client_id][websocket]
                                        self.logger.warning(f"Removed disconnected WebSocket for client {client_id} after ping failure")
                                
                                # If this was the last connection for this client, remove the client
                                if not self.active_connections[client_id]:
                                    del self.active_connections[client_id]
                                    del self.connection_timestamps[client_id]
                                    self.logger.info(f"Removed empty client entry for {client_id} after ping failures")
                
                # If no connections left, stop the service
                async with self.connection_lock:
                    if not self.active_connections:
                        self.logger.info("No active connections remaining, stopping ping service")
                        break
                        
        except asyncio.CancelledError:
            self.logger.info("Ping service cancelled")
        except Exception as e:
            self.logger.error(f"Unexpected error in ping service: {e}", exc_info=True)


# Create a global instance
websocket_manager = WebsocketManager() 