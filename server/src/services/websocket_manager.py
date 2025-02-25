from typing import Dict, Set, Any, Optional
from fastapi import WebSocket
import json
import logging

logger = logging.getLogger(__name__)

class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    @staticmethod
    async def connect(websocket: WebSocket, task_id: str):
        """
        Connect a WebSocket client and subscribe it to a task
        """
        try:
            await websocket.accept()
            if task_id not in websocket_manager.active_connections:
                websocket_manager.active_connections[task_id] = set()
            websocket_manager.active_connections[task_id].add(websocket)
            logger.info(f"WebSocket connected for task {task_id}")
        except Exception as e:
            logger.error(f"Error connecting WebSocket for task {task_id}: {e}")
            raise

    @staticmethod
    async def disconnect(websocket: WebSocket, task_id: str):
        """
        Disconnect a WebSocket client and remove it from task subscriptions
        """
        try:
            if task_id in websocket_manager.active_connections:
                websocket_manager.active_connections[task_id].remove(websocket)
                if not websocket_manager.active_connections[task_id]:
                    del websocket_manager.active_connections[task_id]
                logger.info(f"WebSocket disconnected for task {task_id}")
        except Exception as e:
            logger.error(f"Error disconnecting WebSocket for task {task_id}: {e}")

    async def subscribe_to_task(self, websocket: WebSocket, task_id: str):
        if task_id not in self.active_connections:
            self.active_connections[task_id] = set()
        self.active_connections[task_id].add(websocket)

    async def unsubscribe_from_task(self, websocket: WebSocket, task_id: str):
        await self.disconnect(websocket, task_id)

    async def broadcast_progress(self, task_id: str, progress: float, status: str, error: str = None, details: Optional[Dict[str, Any]] = None):
        """
        Broadcast progress update to all connected clients for a specific task
        
        Args:
            task_id: The ID of the task
            progress: The progress percentage (0-100)
            status: The status of the task (downloading, processing, complete, error)
            error: Optional error message
            details: Optional dictionary with additional details about the download
        """
        if task_id in self.active_connections:
            message = {
                "type": "progress",
                "task_id": task_id,
                "progress": progress,
                "status": status
            }
            if error:
                message["error"] = error
                
            # Add additional details if provided
            if details:
                message.update(details)

            # Log the message being sent (excluding large data)
            log_message = message.copy()
            if 'fileInfo' in log_message and isinstance(log_message['fileInfo'], dict):
                log_message['fileInfo'] = {k: v for k, v in log_message['fileInfo'].items() if k != 'path'}
            logger.debug(f"Broadcasting to task {task_id}: {log_message}")

            for connection in self.active_connections[task_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Error sending progress update: {e}")
                    # Remove failed connection
                    await self.disconnect(connection, task_id)

# Create a global instance
websocket_manager = WebSocketManager() 