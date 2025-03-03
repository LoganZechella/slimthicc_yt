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
        
        # Determine Docker vs local environment
        in_docker = os.path.exists('/.dockerenv')
        container_path = '/app/downloads/'
        host_path = 'server/downloads/'
        base_path = container_path if in_docker else host_path
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
    """Download the completed file."""
    try:
        logger.info(f"Processing download file request for task {task_id}")
        
        # Get the task from the database
        task = await download_task_manager.get_task(task_id)
        if not task:
            logger.error(f"Task {task_id} not found")
            raise HTTPException(status_code=404, detail="Task not found")
            
        if task.status != DownloadStatus.COMPLETE:
            logger.warning(f"Task {task_id} is not complete (status={task.status})")
            raise HTTPException(status_code=400, detail="Download not complete")
        
        # Get the downloads directory
        downloads_dir = Path("server/downloads")
        
        # Check if it's a Spotify playlist
        is_spotify_task = False
        if hasattr(task, 'url') and task.url:
            is_spotify_task = 'spotify.com' in task.url or 'spotify:' in task.url
        
        logger.info(f"Processing download file request for task {task_id} (is_spotify_task: {is_spotify_task})")
        
        # Handle Spotify playlist (multiple files)
        if is_spotify_task:
            # Find the directory for this specific task
            spotify_dir = None
            task_dirs = list(downloads_dir.glob(f"*{task_id}*"))
            if task_dirs:
                for dir_path in task_dirs:
                    if dir_path.is_dir():
                        spotify_dir = dir_path
                        break
            
            if not spotify_dir:
                # Try to find a directory with "spotify" in the name
                spotify_dirs = list(downloads_dir.glob("*spotify*"))
                for dir_path in spotify_dirs:
                    if dir_path.is_dir() and task_id in dir_path.name:
                        spotify_dir = dir_path
                        break
            
            # If still no directory found, check recent directories
            if not spotify_dir and hasattr(task, 'created_at'):
                all_dirs = [d for d in downloads_dir.glob("*") if d.is_dir()]
                if all_dirs:
                    # Sort by modification time (newest first)
                    all_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                    task_created_time = task.created_at.timestamp()
                    
                    # Find directories created after task was created
                    for dir_path in all_dirs:
                        if dir_path.stat().st_mtime > task_created_time:
                            spotify_dir = dir_path
                            break
            
            if spotify_dir:
                logger.info(f"Found Spotify directory: {spotify_dir}")
                # Find all mp3 files in the directory
                mp3_files = list(spotify_dir.glob("*.mp3"))
                
                if mp3_files:
                    # Create a unique ZIP filename
                    playlist_name = task.title if hasattr(task, 'title') and task.title else "playlist"
                    if "Spotify Playlist:" in playlist_name:
                        playlist_name = playlist_name.replace("Spotify Playlist:", "").strip()
                    
                    # Create a safe filename
                    zip_filename = f"spotify_playlist_{playlist_name}_{task_id}.zip"
                    safe_filename = re.sub(r'[^\w\-\.]', '_', zip_filename)
                    zip_path = spotify_dir / safe_filename
                    
                    try:
                        # Create the ZIP file
                        with zipfile.ZipFile(str(zip_path), 'w', zipfile.ZIP_DEFLATED) as zip_file:
                            for mp3_path in mp3_files:
                                zip_file.write(mp3_path, arcname=mp3_path.name)
                        
                        # Get the file size for Content-Length header
                        file_size = zip_path.stat().st_size
                        
                        # Set headers explicitly
                        headers = {
                            "Content-Type": "application/zip",
                            "Content-Length": str(file_size),
                            "Content-Disposition": f'attachment; filename="{safe_filename}"'
                        }
                        
                        # Register background task to clean up the files
                        background_tasks.add_task(cleanup_after_download, str(zip_path), [str(f) for f in mp3_files])
                        
                        logger.info(f"Returning ZIP file: {zip_path} with size {file_size} bytes")
                        
                        # Return the ZIP file
                        return FileResponse(
                            path=str(zip_path),
                            filename=safe_filename,
                            media_type="application/zip",
                            headers=headers
                        )
                        
                    except Exception as zip_error:
                        logger.error(f"Error creating ZIP file: {zip_error}", exc_info=True)
                        raise HTTPException(status_code=500, detail="Failed to create ZIP file")
                else:
                    logger.error(f"No MP3 files found in Spotify directory: {spotify_dir}")
                    raise HTTPException(status_code=404, detail="No MP3 files found for download")
            else:
                logger.error(f"No Spotify directory found for task {task_id}")
                raise HTTPException(status_code=404, detail="Download directory not found")
        
        # Handle single file download
        file_path = None
        
        # First, check if the task has an output_path
        if task.output_path:
            file_path = task.output_path
            # Normalize the path if it's using Docker paths
            if file_path.startswith('/app/'):
                file_path = file_path.replace('/app/downloads/', 'server/downloads/')
            
            # Check if the file exists
            if not Path(file_path).exists():
                # Try to find the file in the downloads directory
                filename = os.path.basename(file_path)
                potential_files = list(downloads_dir.glob(f"*{filename}*"))
                if potential_files:
                    file_path = str(potential_files[0])
                else:
                    # Look for any file with the task ID in the name
                    potential_files = list(downloads_dir.glob(f"*{task_id}*.*"))
                    if potential_files:
                        file_path = str(potential_files[0])
                    else:
                        logger.error(f"File not found: {file_path}")
                        raise HTTPException(status_code=404, detail="File not found")
        else:
            # Try to find a file with the task ID in the name
            potential_files = list(downloads_dir.glob(f"*{task_id}*.*"))
            if potential_files:
                file_path = str(potential_files[0])
            else:
                # Look for recent files
                all_files = list(downloads_dir.glob("*.mp3")) + list(downloads_dir.glob("*.m4a")) + list(downloads_dir.glob("*.zip"))
                if all_files and hasattr(task, 'created_at'):
                    # Sort by modification time (newest first)
                    all_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                    task_created_time = task.created_at.timestamp()
                    
                    # Find files created after task was created
                    for file_path in all_files:
                        if file_path.stat().st_mtime > task_created_time:
                            file_path = str(file_path)
                            break
                
                if not file_path:
                    logger.error(f"No file found for task {task_id}")
                    raise HTTPException(status_code=404, detail="File not found")
        
        # At this point, we should have a valid file_path
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            logger.error(f"File not found at: {file_path}")
            raise HTTPException(status_code=404, detail="File not found")
        
        # Get file info for headers
        file_stats = file_path_obj.stat()
        filename = file_path_obj.name
        
        # Determine media type based on file extension
        media_type = "application/octet-stream"  # Default
        if filename.lower().endswith(".mp3"):
            media_type = "audio/mpeg"
        elif filename.lower().endswith(".m4a"):
            media_type = "audio/m4a"
        elif filename.lower().endswith(".zip"):
            media_type = "application/zip"
        elif filename.lower().endswith(".flac"):
            media_type = "audio/flac"
        elif filename.lower().endswith(".wav"):
            media_type = "audio/wav"
        
        # Set headers explicitly to ensure Content-Length is correct
        headers = {
            "Content-Type": media_type,
            "Content-Length": str(file_stats.st_size),
            "Content-Disposition": f'attachment; filename="{filename}"'
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
    try:
        logger.info(f"Main WebSocket connection request for task {task_id} from {websocket.client.host}")
        
        # Accept the connection
        await websocket_manager.connect(websocket, task_id)
        logger.info(f"WebSocket connection accepted for task {task_id}")
        
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
            logger.info(f"Sent initial status for task {task_id}: {task.status}, progress: {task.progress}")
        else:
            logger.warning(f"Task {task_id} not found when sending initial status")
            await websocket.send_json({"error": f"Task {task_id} not found"})
        
        # Keep the connection open and handle client messages
        try:
            while True:
                # Wait for any message from the client (ping/keepalive)
                data = await websocket.receive_text()
                logger.debug(f"Received message from client {task_id}: {data}")
                
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
                    logger.debug(f"Sent status update for task {task_id}: {task.status}, progress: {task.progress}")
                else:
                    logger.warning(f"Task {task_id} not found when sending status update")
                    await websocket.send_json({"error": f"Task {task_id} not found"})
                
        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected for task {task_id}")
        except Exception as ws_error:
            logger.error(f"Error in WebSocket communication for task {task_id}: {ws_error}", exc_info=True)
        finally:
            # Clean up the connection
            await websocket_manager.disconnect(websocket, task_id)
            logger.info(f"WebSocket connection closed for task {task_id}")
            
    except Exception as e:
        logger.error(f"Error in WebSocket connection setup for task {task_id}: {e}", exc_info=True)
        # Ensure connection is closed on error
        try:
            await websocket_manager.disconnect(websocket, task_id)
            logger.info(f"WebSocket connection force closed after error for task {task_id}")
        except Exception as disconnect_error:
            logger.error(f"Error disconnecting WebSocket for task {task_id}: {disconnect_error}")

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