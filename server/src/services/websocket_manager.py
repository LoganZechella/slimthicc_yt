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
        self.ping_interval = 10  # seconds
        self.ping_task = None
        self.total_connections = 0
        self.ping_timeout = 10  # seconds
        self.ping_service_running = False
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
            # Accept the connection
            await websocket.accept()
            logger.info(f"WebSocket connected: {client_id} (total connections: {self.total_connections + 1})")
            
            # Initialize client connections list if not exists
            if client_id not in self.active_connections:
                self.active_connections[client_id] = []
            
            # Track connection with timestamp
            self.active_connections[client_id].append(websocket)
            
            # Initialize timestamp tracking for this client
            if client_id not in self.connection_timestamps:
                self.connection_timestamps[client_id] = {}
            
            # Set initial timestamp for this connection
            self.connection_timestamps[client_id][websocket] = time.time()
            
            # Start the ping service if not already running
            if not self.ping_service_running:
                asyncio.create_task(self._ping_service())
                logger.info(f"Starting ping service with {self.ping_interval}s interval")
                self.ping_service_running = True
            
            # Log active clients for debugging
            client_ids = list(self.active_connections.keys())
            logger.info(f"Active clients: {client_ids}")
            
            # Log total connections
            self.total_connections += 1
            logger.info(f"Total active connections: {self.total_connections}")
            
            return True
        except Exception as e:
            logger.error(f"Error connecting WebSocket for client {client_id}: {e}", exc_info=True)
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
        try:
            if client_id in self.active_connections:
                connections = self.active_connections[client_id]
                
                if not connections:
                    logger.warning(f"No active connections for client {client_id} - broadcast will be skipped")
                    return False
                
                connection_count = len(connections)
                logger.debug(f"Broadcasting to {connection_count} connections for client {client_id}")
                
                # Track problematic connections to remove
                problematic_connections = []
                
                # Loop through connections and send message
                for connection in connections:
                    try:
                        # Check if connection is still open
                        if connection.client_state.name.lower() != "connected":
                            logger.warning(f"Connection for {client_id} is not in connected state ({connection.client_state.name})")
                            problematic_connections.append(connection)
                            continue
                        
                        # Send message
                        await connection.send_json(message)
                        
                        # Update last activity timestamp
                        if client_id in self.connection_timestamps:
                            self.connection_timestamps[client_id][connection] = time.time()
                    except Exception as e:
                        logger.error(f"Error sending to specific connection for {client_id}: {e}")
                        problematic_connections.append(connection)
                
                # Remove problematic connections
                if problematic_connections:
                    for prob_conn in problematic_connections:
                        if client_id in self.active_connections and prob_conn in self.active_connections[client_id]:
                            self.active_connections[client_id].remove(prob_conn)
                            self.total_connections -= 1
                            
                            if client_id in self.connection_timestamps and prob_conn in self.connection_timestamps[client_id]:
                                del self.connection_timestamps[client_id][prob_conn]
                            logger.info(f"Removed problematic connection for {client_id}")
                    
                    # Clean up empty client entries
                    if client_id in self.active_connections and not self.active_connections[client_id]:
                        del self.active_connections[client_id]
                        if client_id in self.connection_timestamps:
                            del self.connection_timestamps[client_id]
                        logger.info(f"Removed empty client entry for {client_id}")
                
                # Return success if at least one message was sent
                return len(problematic_connections) < connection_count
            else:
                logger.warning(f"No active connections for client {client_id} - broadcast will be skipped")
                return False
        except Exception as e:
            logger.error(f"Error in broadcast for client {client_id}: {e}", exc_info=True)
            return False
    
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
        """Send periodic pings to keep WebSocket connections alive."""
        try:
            self.ping_service_running = True
            logger.info("Starting WebSocket ping service")
            
            while True:
                try:
                    # Wait for the ping interval
                    await asyncio.sleep(self.ping_interval)
                    
                    # Current time for checking connection age
                    current_time = time.time()
                    
                    # Track clients with no active connections
                    empty_clients = []
                    
                    # Send ping to all connected clients
                    for client_id, connections in list(self.active_connections.items()):
                        if not connections:
                            empty_clients.append(client_id)
                            continue
                        
                        # Problematic connections that need removal
                        problematic_connections = []
                        
                        # Track if any ping was sent successfully
                        ping_success = False
                        
                        # Send ping to each connection
                        for connection in connections:
                            try:
                                # Check if connection is already closed
                                if connection.client_state.name.lower() != "connected":
                                    logger.warning(f"Found closed connection for {client_id} ({connection.client_state.name})")
                                    problematic_connections.append(connection)
                                    continue
                                
                                # Check connection age
                                if client_id in self.connection_timestamps and connection in self.connection_timestamps[client_id]:
                                    last_time = self.connection_timestamps[client_id][connection]
                                    if current_time - last_time > self.ping_timeout:
                                        logger.warning(f"Connection for {client_id} timed out (no activity for {current_time - last_time:.1f}s)")
                                        problematic_connections.append(connection)
                                        continue
                                
                                # Send ping message
                                ping_message = {
                                    "type": "ping", 
                                    "timestamp": current_time,
                                    "taskId": client_id
                                }
                                await connection.send_json(ping_message)
                                
                                # Update timestamp
                                if client_id in self.connection_timestamps:
                                    self.connection_timestamps[client_id][connection] = current_time
                                
                                ping_success = True
                                logger.debug(f"Sent ping to client {client_id}")
                            except Exception as e:
                                logger.warning(f"Failed to ping connection for {client_id}: {e}")
                                problematic_connections.append(connection)
                        
                        # Remove problematic connections
                        if problematic_connections:
                            for prob_conn in problematic_connections:
                                if client_id in self.active_connections and prob_conn in self.active_connections[client_id]:
                                    self.active_connections[client_id].remove(prob_conn)
                                    self.total_connections -= 1
                                    
                                    if client_id in self.connection_timestamps and prob_conn in self.connection_timestamps[client_id]:
                                        del self.connection_timestamps[client_id][prob_conn]
                                    
                                    logger.info(f"Removed problematic connection during ping for {client_id}")
                            
                            # If no connections successfully pinged, mark client for removal
                            if not ping_success and client_id in self.active_connections and not self.active_connections[client_id]:
                                empty_clients.append(client_id)
                    
                    # Remove empty clients
                    for client_id in empty_clients:
                        if client_id in self.active_connections:
                            del self.active_connections[client_id]
                        if client_id in self.connection_timestamps:
                            del self.connection_timestamps[client_id]
                        logger.info(f"Removed empty client {client_id} during ping cycle")
                    
                    logger.debug(f"Ping cycle completed, {len(self.active_connections)} active clients remaining")
                    
                except Exception as e:
                    logger.error(f"Error in ping cycle: {e}", exc_info=True)
                    # Continue the loop even if there's an error
            
        except Exception as e:
            logger.error(f"Ping service crashed: {e}", exc_info=True)
            self.ping_service_running = False


# Create a global instance
websocket_manager = WebsocketManager() 