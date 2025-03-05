from fastapi import APIRouter, HTTPException, WebSocket, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.websockets import WebSocketDisconnect
from typing import Optional, Dict, List, Any, Union
import logging
from src.models.download import (
    DownloadTaskCreate,
    DownloadTaskResponse,
    DownloadStatus,
    DownloadError
)
from src.services.download_task_manager import download_task_manager
from src.services.websocket_manager import websocket_manager
from datetime import datetime
import re
import os
from pathlib import Path
import zipfile
import io
import time
import asyncio
from fastapi.websockets import WebSocketState
from src.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

async def cleanup_after_download(zip_path: str, mp3_file_paths: List[str]):
    """
    Clean up files after a successful download.
    
    Args:
        zip_path: Path to the ZIP file that was served
        mp3_file_paths: List of MP3 file paths that were included in the ZIP
    """
    try:
        # Get configuration from environment or use defaults
        
        # Check if cleanup is enabled
        should_cleanup = os.environ.get("ENABLE_FILE_CLEANUP", "true").lower() == "true"
        if not should_cleanup:
            logger.info("File cleanup is disabled by configuration")
            return
            
        # Wait time before cleanup
        wait_time = int(os.environ.get("CLEANUP_WAIT_TIME", "120"))  # Default: 120 seconds (increased from 60)
        
        # Whether to remove source files (MP3s) after ZIP creation
        should_remove_source_files = os.environ.get("CLEANUP_SOURCE_FILES", "true").lower() == "true"
        
        logger.info(f"Scheduling cleanup of files after {wait_time} seconds (remove source: {should_remove_source_files})")
        logger.info(f"ZIP path: {zip_path}")
        logger.info(f"MP3 files: {mp3_file_paths}")
        
        # Wait longer to ensure the client has time to download the ZIP
        await asyncio.sleep(wait_time)
        
        # Use Render path for downloads
        base_path = '/project/src/server/downloads/'
        downloads_dir = Path(base_path)
        
        # Collect task-specific directories to check for cleanup
        task_dirs = set()
        
        # Clean up the ZIP file first
        zip_file = Path(zip_path)
        if zip_file.exists():
            logger.info(f"Cleaning up ZIP file: {zip_path}")
            try:
                zip_file.unlink()
                logger.info(f"Successfully removed ZIP file: {zip_path}")
                
                # Add the parent directory to check for emptiness later
                if str(zip_file.parent).startswith(str(downloads_dir)) and zip_file.parent != downloads_dir:
                    task_dirs.add(str(zip_file.parent))
            except Exception as e:
                logger.error(f"Error removing ZIP file {zip_path}: {e}")
        else:
            logger.warning(f"ZIP file not found for cleanup: {zip_path}")
        
        # Clean up the MP3 files if configured to do so
        if should_remove_source_files:
            for mp3_path in mp3_file_paths:
                mp3_file = Path(mp3_path)
                if mp3_file.exists():
                    logger.info(f"Cleaning up MP3 file: {mp3_path}")
                    try:
                        mp3_file.unlink()
                        logger.info(f"Successfully removed MP3 file: {mp3_path}")
                        
                        # Add the parent directory to check for emptiness later
                        if str(mp3_file.parent).startswith(str(downloads_dir)) and mp3_file.parent != downloads_dir:
                            task_dirs.add(str(mp3_file.parent))
                    except Exception as e:
                        logger.error(f"Error removing MP3 file {mp3_path}: {e}")
                else:
                    logger.warning(f"MP3 file not found for cleanup: {mp3_path}")
        
        # Clean up any empty task-specific directories
        if task_dirs:
            logger.info(f"Checking {len(task_dirs)} directories for cleanup")
            
            # Sort directories by depth (deeper directories first)
            sorted_dirs = sorted(task_dirs, key=lambda d: d.count(os.path.sep), reverse=True)
            
            for dir_path in sorted_dirs:
                dir_obj = Path(dir_path)
                try:
                    # Check if directory exists and is empty
                    if dir_obj.exists() and not any(dir_obj.iterdir()):
                        logger.info(f"Removing empty directory: {dir_obj}")
                        dir_obj.rmdir()
                        logger.info(f"Successfully removed empty directory: {dir_obj}")
                except Exception as e:
                    logger.error(f"Error checking/removing directory {dir_obj}: {e}")
        
        logger.info("Cleanup after download completed successfully")
    except Exception as e:
        logger.error(f"Error in cleanup process: {e}", exc_info=True)

@router.post("/", response_model=DownloadTaskResponse)
async def create_download(request: DownloadTaskCreate):
    """Create a new download task."""
    try:
        logger.info(f"Received download request: {request.model_dump_json()}")
        task = await download_task_manager.create_task(request.url, request.quality)
        logger.info(f"Created download task: {task.id} for URL: {task.url}")
        
        # Return the response with task_id field for frontend compatibility
        response_data = DownloadTaskResponse(
            id=task.id,
            url=task.url,
            title=task.title,
            author=task.author,
            status=task.status,
            progress=task.progress,
            error=task.error,
            created_at=task.created_at,
            updated_at=task.updated_at,
            quality=task.quality,
            output_path=task.output_path
        )
        
        # Add task_id field for legacy frontend support
        response_dict = response_data.model_dump()
        response_dict["task_id"] = task.id
        
        logger.info(f"Returning download task response: {response_dict}")
        return response_dict
    except DownloadError as e:
        logger.error(f"Download task creation failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error creating download task: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/{task_id}", response_model=DownloadTaskResponse)
async def get_download_status(task_id: str):
    """Get the status of a download task."""
    try:
        task = await download_task_manager.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
            
        return DownloadTaskResponse(
            id=task.id,
            url=task.url,
            title=task.title,
            author=task.author,
            status=task.status,
            progress=task.progress,
            error=task.error,
            created_at=task.created_at,
            updated_at=task.updated_at,
            quality=task.quality,
            output_path=task.output_path
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting task status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.delete("/{task_id}")
async def cancel_download(task_id: str):
    """Cancel a download task."""
    try:
        success = await download_task_manager.cancel_task(task_id)
        if not success:
            raise HTTPException(status_code=404, detail="Task not found or already completed")
        return {"message": "Task cancelled successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling task: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/{task_id}/file")
async def download_file(task_id: str, background_tasks: BackgroundTasks):
    """Download a file for a specific task."""
    try:
        logger.info(f"Download file request for task: {task_id}")
        task = await download_task_manager.get_task(task_id)
        
        if not task:
            logger.error(f"Task not found: {task_id}")
            raise HTTPException(status_code=404, detail="Task not found")
        
        if task.status != DownloadStatus.COMPLETE:
            logger.error(f"Task not ready for download: {task_id} (status: {task.status})")
            raise HTTPException(status_code=400, detail=f"Task not ready for download (status: {task.status})")
        
        logger.info(f"Processing download for task: {task_id}, reported path: {task.output_path}")
        
        # Fix for Spotify playlists which may specify a path in the downloads directory
        # Check if this is a Spotify task with a special directory format
        if hasattr(task, 'spotify_output_dir') and task.spotify_output_dir:
            # Use the spotify_output_dir from the task, which should be using Render paths
            logger.info(f"Found Spotify task with output dir: {task.spotify_output_dir}")
            
            # Use the direct path from the task
            file_path = Path(task.spotify_output_dir)
            logger.info(f"Using Spotify output directory: {file_path}")
            
            # If it's a directory, we need to create a ZIP of all files
            if file_path.is_dir():
                logger.info(f"Found Spotify playlist directory: {file_path}")
                
                # Try multiple file extensions (mp3, m4a, etc.)
                audio_files = []
                for ext in ["*.mp3", "*.m4a", "*.flac", "*.wav"]:
                    audio_files.extend(list(file_path.glob(ext)))
                
                logger.info(f"Found {len(audio_files)} audio files in directory")
                
                if not audio_files:
                    logger.warning(f"No files found at {file_path}")
                    raise HTTPException(status_code=404, detail="No audio files found in the download directory. Please try downloading again.")
                
                # If only one file, return it directly
                if len(audio_files) == 1:
                    file_path = audio_files[0]
                    logger.info(f"Only one audio file found, returning it directly: {file_path}")
                else:
                    # Create a ZIP file for multiple files
                    zip_path = Path(f"/project/src/server/downloads/{task_id}_playlist.zip")
                    logger.info(f"Creating ZIP file for multiple audio files: {zip_path}")
                    
                    # Create a ZIP file containing all audio files
                    with zipfile.ZipFile(zip_path, 'w') as zipf:
                        for audio_file in audio_files:
                            zipf.write(audio_file, arcname=audio_file.name)
                    
                    file_path = zip_path
                    logger.info(f"ZIP file created: {file_path}")
                    
                    # Add cleanup task for the ZIP file
                    background_tasks.add_task(cleanup_after_download, str(zip_path), [str(zip_path)])
            
        # For standard downloads with output_path specified
        elif task.output_path:
            # Check for various possible file formats
            possible_paths = [
                Path(f"{settings.DOWNLOADS_DIR}/{task_id}.mp3"),  # Local MP3
                Path(f"{settings.DOWNLOADS_DIR}/{task_id}.m4a"),  # Local M4A
                Path(f"{settings.DOWNLOADS_DIR}/{task_id}.zip"),  # Local ZIP
                Path(f"/project/src/server/downloads/{task_id}.mp3"),  # Render MP3
                Path(f"/project/src/server/downloads/{task_id}.m4a"),  # Render M4A
                Path(f"/project/src/server/downloads/{task_id}.zip")   # Render ZIP
            ]
            
            # Find the first existing path
            file_path = None
            for path in possible_paths:
                if path.exists() and path.is_file() and path.stat().st_size > 0:
                    file_path = path
                    logger.info(f"Found existing file at: {file_path}")
                    break
            
            if not file_path:
                logger.error(f"File not found for task {task_id}. Tried paths: {possible_paths}")
                raise HTTPException(status_code=404, detail="File not found")
        else:
            logger.error(f"No output path specified for task {task_id}")
            raise HTTPException(status_code=400, detail="No output path specified")
        
        # Extract file info
        filename = file_path.name
        file_stats = file_path.stat()
        
        # Determine media type based on extension
        extension = file_path.suffix.lower()
        if extension == '.mp3':
            media_type = 'audio/mpeg'
        elif extension == '.m4a':
            media_type = 'audio/mp4'
        elif extension == '.zip':
            media_type = 'application/zip'
        elif extension == '.flac':
            media_type = 'audio/flac'
        elif extension == '.wav':
            media_type = 'audio/wav'
        else:
            media_type = 'application/octet-stream'
        
        # Set response headers
        headers = {
            'Content-Length': str(file_stats.st_size),
            'Content-Type': media_type,
            'Content-Disposition': f'attachment; filename="{filename}"'
        }
        
        # Update the task with the correct path if needed
        if file_path != task.output_path:
            await download_task_manager.update_task(
                task, 
                output_path=file_path
            )
        
        # Register background task to clean up file after serving
        background_tasks.add_task(cleanup_after_download, file_path, [file_path])
        
        logger.info(f"Returning file: {filename} with size {file_stats.st_size} bytes and type {media_type}")
        
        # Return the file
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type=media_type,
            headers=headers
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in download_file: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.websocket("/{task_id}/ws")
async def main_websocket_endpoint(websocket: WebSocket, task_id: str):
    """Main WebSocket endpoint for real-time task updates."""
    logger.error("THE ROUTER VERSION OF THE WEBSOCKET ENDPOINT IS CALLED - THIS SHOULD NOT HAPPEN")
    logger.error("Please use the main.py WebSocket endpoint instead")
    try:
        logger.info(f"Main WebSocket router endpoint reached for task {task_id} from {websocket.client.host}")
        
        # This function is no longer directly called. It's handled by main.py's endpoint instead.
        # If we do get here, check if the connection needs to be accepted
        if websocket.client_state != WebSocketState.CONNECTED:
            logger.info(f"Accepting WebSocket connection for task {task_id}")
            await websocket.accept()
        
        # We'll still handle the connection if we get here
        await websocket_manager.connect(websocket, task_id)
        logger.info(f"WebSocket connection established and registered for task {task_id}")
        
        # Send initial status
        task = await download_task_manager.get_task(task_id)
        if task:
            initial_status = {
                "type": "status",
                "task_id": task_id,
                "status": task.status,
                "progress": task.progress,
                "title": task.title,
                "error": task.error,
                "timestamp": time.time()
            }
            try:
                await websocket.send_json(initial_status)
                logger.info(f"Sent initial status for task {task_id}")
            except Exception as e:
                logger.error(f"Error sending initial status for task {task_id}: {e}")
        
        # Handle messages from client
        while True:
            try:
                # Wait for a message with a timeout
                message_json = await asyncio.wait_for(websocket.receive_json(), timeout=60)
                
                # Handle client message - usually "hello" or heartbeat
                msg_type = message_json.get("type", "unknown")
                logger.info(f"Received {msg_type} message from client for task {task_id}")
                
                # Send acknowledgment
                if msg_type == "hello":
                    await websocket.send_json({
                        "type": "welcome",
                        "task_id": task_id,
                        "timestamp": time.time()
                    })
                    logger.debug(f"Sent welcome response to client for task {task_id}")
                
                # Other message types can be handled here
                
            except asyncio.TimeoutError:
                # Check if connection is still valid
                if websocket.client_state.name.lower() != "connected":
                    logger.warning(f"WebSocket connection for task {task_id} is no longer connected, exiting loop")
                    break
                
                # Connection still valid, just a timeout with no messages
                logger.debug(f"No messages received from client for task {task_id} in 60s, continuing to listen")
                continue
                
            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected for task {task_id}")
                await websocket_manager.disconnect(websocket, task_id)
                break
                
            except Exception as e:
                logger.error(f"Error processing WebSocket message for task {task_id}: {e}")
                # Try to continue if possible
                if websocket.client_state.name.lower() != "connected":
                    logger.warning(f"WebSocket connection for task {task_id} is no longer connected after error")
                    break
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected during setup for task {task_id}")
        await websocket_manager.disconnect(websocket, task_id)
        
    except Exception as e:
        logger.error(f"Error in WebSocket endpoint for task {task_id}: {e}", exc_info=True)
        try:
            await websocket_manager.disconnect(websocket, task_id)
        except Exception:
            pass

@router.websocket("/ws/{task_id}")
async def alt_websocket_endpoint(websocket: WebSocket, task_id: str):
    """
    Alternative WebSocket endpoint that matches the path format /ws/{task_id}
    This is a fallback to handle alternative WebSocket connection formats.
    """
    logger.info(f"Alternative WebSocket path connection request for task {task_id} from {websocket.client.host}")
    logger.info(f"This connection used the /ws/{task_id} format instead of /{task_id}/ws")
    
    # Accept the connection
    await websocket_manager.connect(websocket, task_id)
    logger.info(f"WebSocket connection accepted for task {task_id} (alt path)")
    
    # Send initial status
    task = await download_task_manager.get_task(task_id)
    if task:
        initial_status = {
            "id": task.id,
            "status": task.status,
            "progress": task.progress,
            "title": task.title,
            "author": task.author,
            "error": task.error
        }
        await websocket.send_json(initial_status)
        logger.info(f"Sent initial status for task {task_id}: {task.status}, progress: {task.progress} (alt path)")
    else:
        logger.warning(f"Task {task_id} not found when sending initial status (alt path)")
        await websocket.send_json({"error": f"Task {task_id} not found"})
    
    # Keep the connection open and handle client messages
    try:
        while True:
            # Wait for any message from the client (ping/keepalive)
            data = await websocket.receive_text()
            logger.debug(f"Received message from client {task_id}: {data} (alt path)")
            
            # Send current status on any client message
            task = await download_task_manager.get_task(task_id)
            if task:
                status_update = {
                    "id": task.id,
                    "status": task.status,
                    "progress": task.progress,
                    "title": task.title,
                    "author": task.author,
                    "error": task.error
                }
                await websocket.send_json(status_update)
                logger.debug(f"Sent status update for task {task_id}: {task.status}, progress: {task.progress} (alt path)")
            else:
                logger.warning(f"Task {task_id} not found when sending status update (alt path)")
                await websocket.send_json({"error": f"Task {task_id} not found"})
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for task {task_id} (alt path)")
    except Exception as ws_error:
        logger.error(f"Error in WebSocket communication for task {task_id}: {ws_error} (alt path)", exc_info=True)
    finally:
        # Clean up the connection
        await websocket_manager.disconnect(websocket, task_id)
        logger.info(f"WebSocket connection closed for task {task_id} (alt path)")

# Add another fallback WebSocket endpoint for the most general case
@router.websocket("/{path:path}")
async def fallback_websocket_endpoint(websocket: WebSocket, path: str):
    """
    Fallback WebSocket endpoint that can handle any path format
    Attempts to extract task_id from the path
    """
    # Try to extract the task_id from the path
    # This is a catch-all to handle various formats the client might use
    path_parts = path.strip('/').split('/')
    
    # Extract task_id - it's likely either the first or last part of the path
    # The task_id is typically a UUID which is 36 characters long
    task_id = None
    for part in path_parts:
        if len(part) > 30:  # Likely a UUID (task_id)
            task_id = part
            break
    
    if not task_id and len(path_parts) > 0:
        # If we can't identify by length, just use the first part
        task_id = path_parts[0]
    
    if not task_id:
        logger.error(f"Could not extract task_id from WebSocket path: {path}")
        await websocket.accept()
        await websocket.send_json({"error": "Invalid WebSocket path, could not extract task_id"})
        await websocket.close()
        return
    
    logger.info(f"Fallback WebSocket connection with path '{path}' mapped to task_id: {task_id}")
    
    try:
        # Accept the connection
        await websocket_manager.connect(websocket, task_id)
        logger.info(f"WebSocket connection accepted for task {task_id} via fallback handler")
        
        # Send initial status
        task = await download_task_manager.get_task(task_id)
        if task:
            initial_status = {
                "id": task.id,
                "status": task.status,
                "progress": task.progress,
                "title": task.title,
                "author": task.author,
                "error": task.error
            }
            await websocket.send_json(initial_status)
            logger.info(f"Sent initial status for task {task_id}: {task.status}, progress: {task.progress} (fallback)")
        else:
            logger.warning(f"Task {task_id} not found when sending initial status (fallback)")
            await websocket.send_json({"error": f"Task {task_id} not found"})
        
        # Handle messages same as other endpoints
        try:
            while True:
                data = await websocket.receive_text()
                logger.debug(f"Received message from client {task_id}: {data} (fallback)")
                
                task = await download_task_manager.get_task(task_id)
                if task:
                    status_update = {
                        "id": task.id,
                        "status": task.status,
                        "progress": task.progress,
                        "title": task.title,
                        "author": task.author,
                        "error": task.error
                    }
                    await websocket.send_json(status_update)
                else:
                    await websocket.send_json({"error": f"Task {task_id} not found"})
                
        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected for task {task_id} (fallback)")
        except Exception as ws_error:
            logger.error(f"Error in WebSocket communication for task {task_id}: {ws_error} (fallback)", exc_info=True)
        finally:
            await websocket_manager.disconnect(websocket, task_id)
            
    except Exception as e:
        logger.error(f"Error in fallback WebSocket handler for path {path}: {e}", exc_info=True)
        try:
            await websocket_manager.disconnect(websocket, task_id)
        except Exception as disconnect_error:
            logger.error(f"Error disconnecting fallback WebSocket: {disconnect_error}") 