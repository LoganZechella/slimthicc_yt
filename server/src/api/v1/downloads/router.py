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
        # Define path mappings
        container_path = '/app/downloads/'  # Container path 
        host_path = 'server/downloads/'     # Host path for local development
        
        # Determine if we're running in Docker or locally
        in_docker = os.path.exists('/.dockerenv')
        
        # Use the appropriate base path based on environment
        base_path = container_path if in_docker else host_path
        download_path = Path(base_path)     # File system path object
        
        logger.info(f"Processing download file request for task {task_id}")
        
        task = await download_task_manager.get_task(task_id)
        if not task:
            logger.error(f"Task {task_id} not found")
            raise HTTPException(status_code=404, detail="Task not found")
            
        if task.status != DownloadStatus.COMPLETE:
            logger.warning(f"Task {task_id} is not complete (status={task.status})")
            raise HTTPException(status_code=400, detail="Download not complete")
        
        # Check for Spotify playlist downloads (multiple files)
        is_spotify_task = False
        if hasattr(task, 'url'):
            is_spotify_task = 'spotify.com' in task.url or 'spotify:' in task.url
        
        logger.info(f"Processing download file request for task {task_id} (is_spotify_task: {is_spotify_task})")
        
        # Special handling for Spotify playlist downloads which create multiple files
        if is_spotify_task:
            # IMPROVED SPOTIFY HANDLING
            logger.info(f"Processing Spotify download with ID: {task_id}")
            
            # Get Spotify output directory from task
            spotify_dir = None
            spotify_id = None
            
            # Try to find the specific directory for this task first
            # 1. First look for a directory containing the task_id in the name
            task_specific_dirs = list(download_path.glob(f"*{task_id}*"))
            if task_specific_dirs:
                # Find directories, prioritize ones with 'spotify' in the name
                task_dirs = [d for d in task_specific_dirs if d.is_dir()]
                spotify_task_dirs = [d for d in task_dirs if 'spotify' in d.name.lower()]
                
                if spotify_task_dirs:
                    spotify_dir = str(spotify_task_dirs[0])
                    logger.info(f"Found task-specific Spotify directory: {spotify_dir}")
                elif task_dirs:
                    spotify_dir = str(task_dirs[0])
                    logger.info(f"Found task-specific directory: {spotify_dir}")
            
            # 2. Parse from spotify_output_dir field if still not found - this is most reliable
            if not spotify_dir and hasattr(task, 'spotify_output_dir') and task.spotify_output_dir:
                spotify_output_info = task.spotify_output_dir.strip()
                # Handle the case where the string contains newlines and additional info
                if '\n' in spotify_output_info:
                    spotify_dir_part = spotify_output_info.split('\n')[0].strip()
                    logger.info(f"Extracted directory from spotify_output_dir first line: {spotify_dir_part}")
                    if spotify_dir_part.startswith(container_path):
                        # Convert from container path to appropriate base path
                        spotify_dir = spotify_dir_part.replace(container_path, base_path)
                else:
                    # Direct path
                    if spotify_output_info.startswith(container_path):
                        # Convert from container path to appropriate base path
                        spotify_dir = spotify_output_info.replace(container_path, base_path)
                
                logger.info(f"Found spotify_output_dir: {spotify_dir}")
            
            # 3. Check for directory info in error message as fallback
            if not spotify_dir and task.error and 'saved in' in task.error:
                dir_match = re.search(r'saved in (/app/downloads[^\.]*)', task.error)
                if dir_match:
                    container_spotify_dir = dir_match.group(1)
                    # Convert from container path to appropriate base path
                    spotify_dir = container_spotify_dir.replace(container_path, base_path)
                    logger.info(f"Extracted spotify output directory from error: {spotify_dir}")
            
            # 4. Extract Spotify ID from the task URL as fallback
            if not spotify_id and hasattr(task, 'url'):
                # Extract Spotify playlist ID from URL
                spotify_url = task.url
                id_match = re.search(r'(playlist|track|album)[:/]([a-zA-Z0-9]+)', spotify_url)
                if id_match:
                    spotify_id = id_match.group(2)
                    logger.info(f"Extracted Spotify ID from URL: {spotify_id}")
                    
                    # Look for a directory matching the pattern spotify_playlist_{spotify_id}_{task_id}
                    potential_dir = Path(base_path) / f"spotify_playlist_{spotify_id}_{task_id}"
                    if potential_dir.exists() and potential_dir.is_dir():
                        spotify_dir = str(potential_dir)
                        logger.info(f"Found task-specific directory: {spotify_dir}")
                    else:
                        # Check for any directory containing both spotify_id and task_id
                        potential_dirs = list(Path(base_path).glob(f"*{spotify_id}*{task_id}*"))
                        if not potential_dirs:
                            potential_dirs = list(Path(base_path).glob(f"*{spotify_id}*"))
                        
                        if potential_dirs:
                            for dir_path in potential_dirs:
                                if dir_path.is_dir():
                                    spotify_dir = str(dir_path)
                                    logger.info(f"Found directory matching Spotify ID: {spotify_dir}")
                                    break
            
            # Default to general download directory if no specific dir found
            if not spotify_dir:
                spotify_dir = base_path
                logger.info(f"Using default download directory: {spotify_dir}")
            
            # Find all mp3 files in the directory
            download_dir = Path(spotify_dir)
            mp3_files = list(download_dir.glob("*.mp3"))
            
            if not mp3_files and spotify_dir != base_path:
                # If no files found in the specific directory, check for files in subdirectories
                logger.info(f"No MP3 files found directly in {spotify_dir}, checking subdirectories")
                mp3_files = list(download_dir.glob("**/*.mp3"))
            
            # If still no files and we're using a specific directory, check for recent files
            # but ONLY if we have a specific context (like a Spotify ID)
            if not mp3_files and spotify_id:
                logger.info(f"No MP3 files found in {spotify_dir}, checking for recent files with context")
                
                # If we have a specific ID, look for a directory with that ID
                spotify_id_dirs = list(Path(base_path).glob(f"*{spotify_id}*"))
                if spotify_id_dirs:
                    for dir_path in spotify_id_dirs:
                        if dir_path.is_dir():
                            mp3_files = list(dir_path.glob("*.mp3"))
                            if mp3_files:
                                spotify_dir = str(dir_path)
                                logger.info(f"Found MP3 files in directory matching Spotify ID: {spotify_dir}")
                                break
                
                # If still no files, only then check recent files but try to filter by task ID or spotify ID
                if not mp3_files:
                    download_dir = Path(base_path)
                    
                    # Get all MP3 files by creation time (newest first)
                    all_mp3_files = list(download_dir.glob("**/*.mp3"))
                    if all_mp3_files:
                        all_mp3_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                        
                        # Take files created within the last 10 minutes (Spotify download should be recent)
                        current_time = time.time()
                        ten_minutes_ago = current_time - 600  # 10 minutes in seconds
                        
                        # Filter by recency AND by task creation time
                        # Only include files created AFTER the task was created
                        task_created_time = task.created_at.timestamp() if hasattr(task, 'created_at') else ten_minutes_ago
                        
                        # Apply both time and directory context filters
                        mp3_files = []
                        for f in all_mp3_files:
                            file_mtime = f.stat().st_mtime
                            # Only include files created after the task and within the last 10 minutes
                            if file_mtime > task_created_time and file_mtime > ten_minutes_ago:
                                # Prefer files in directories containing task ID or spotify ID
                                if task_id in str(f.parent) or (spotify_id and spotify_id in str(f.parent)):
                                    mp3_files.append(f)
            
            # If we have any MP3 files, create a zip file
            if mp3_files:
                logger.info(f"Creating zip file for {len(mp3_files)} Spotify tracks")
                
                # Create a unique ZIP filename based on task info
                playlist_name = task.title if hasattr(task, 'title') and task.title else "playlist"
                if "Spotify Playlist:" in playlist_name:
                    playlist_name = playlist_name.replace("Spotify Playlist:", "").strip()
                    
                # Add Spotify ID and task ID to filename for better identification
                if spotify_id:
                    # Use task ID in filename for unique identification
                    zip_filename = f"spotify_playlist_{playlist_name}_{spotify_id}_{task_id}.zip"
                else:
                    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                    zip_filename = f"spotify_playlist_{playlist_name}_{task_id}_{timestamp}.zip"
                
                safe_filename = re.sub(r'[^\w\-\.]', '_', zip_filename)  # Make filename safe
                
                # Create ZIP in the specific task directory if it exists and has files
                if mp3_files and spotify_dir != base_path and Path(spotify_dir).exists():
                    # Use the dedicated task directory for the ZIP
                    zip_path = Path(spotify_dir) / safe_filename
                else:
                    # Fallback to downloads directory with task ID in filename
                    zip_path = Path(base_path) / safe_filename
                
                # Create parent directory if it doesn't exist
                zip_path.parent.mkdir(parents=True, exist_ok=True)
                logger.info(f"Creating ZIP file at {zip_path}")
                
                # Create the ZIP file with all MP3 files
                try:
                    with zipfile.ZipFile(str(zip_path), 'w', zipfile.ZIP_DEFLATED) as zip_file:
                        for mp3_path in mp3_files:
                            # Add file to zip with its filename only (not full path)
                            mp3_filename = mp3_path.name
                            # Log each file being added
                            logger.info(f"Adding {mp3_filename} to zip file")
                            zip_file.write(mp3_path, arcname=mp3_filename)
                    
                    logger.info(f"Successfully created ZIP file at {zip_path}")
                    
                    # Update the task with the zip file path - store both paths for clarity
                    container_zip_path = str(zip_path).replace(base_path, container_path) if not in_docker else str(zip_path)
                    await download_task_manager.update_task(
                        task,
                        output_path=str(zip_path)  # Store the host path to the ZIP file
                    )
                    
                    # Register background task to clean up files after serving
                    background_tasks.add_task(cleanup_after_download, str(zip_path), [str(f) for f in mp3_files])
                    
                    # Return the zip file from disk
                    return FileResponse(
                        str(zip_path),
                        media_type="application/zip",
                        filename=safe_filename
                    )
                    
                except Exception as e:
                    logger.error(f"Error creating ZIP file: {e}", exc_info=True)
                    
                    # Fallback to memory ZIP if disk ZIP fails
                    try:
                        logger.info("Trying memory-based ZIP creation as fallback")
                        zip_buffer = io.BytesIO()
                        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                            for mp3_path in mp3_files:
                                zip_file.write(mp3_path, arcname=mp3_path.name)
                        
                        # Seek to beginning of buffer
                        zip_buffer.seek(0)
                        
                        # Return the zip file from memory
                        from fastapi.responses import Response
                        return Response(
                            content=zip_buffer.getvalue(),
                            media_type="application/zip",
                            headers={"Content-Disposition": f"attachment; filename={safe_filename}"}
                        )
                    except Exception as fallback_error:
                        logger.error(f"Memory ZIP fallback also failed: {fallback_error}", exc_info=True)
                        raise HTTPException(status_code=500, detail="Failed to create ZIP file")
            else:
                # No MP3 files found
                logger.error(f"No MP3 files found for Spotify download task {task_id}")
                raise HTTPException(status_code=404, detail="No MP3 files found for the Spotify playlist")
        
        # Standard single file download handling
        if not task.output_path:
            # Check for successful files directly if output_path not set
            logger.info(f"Task {task_id} has no output_path, attempting to locate file")
            
            # Check for files in the downloads directory
            file_path = None
            
            # First, check if there's a reference to a specific file in the error message
            if task.error and container_path in task.error:
                path_matches = re.findall(r'(/app/downloads/.*\.mp3)', task.error)
                if path_matches:
                    container_file_path = path_matches[0]
                    host_file_path = container_file_path.replace(container_path, host_path)
                    if Path(host_file_path).exists():
                        file_path = host_file_path
                        logger.info(f"Found file at extracted path: {file_path}")
            
            # If we still don't have a file, check for files matching the title
            if not file_path and task.title:
                potential_files = list(download_path.glob(f"*{task.title}*.mp3"))
                if potential_files:
                    file_path = str(potential_files[0])
                    logger.info(f"Found file matching title: {file_path}")
            
            # As a last resort, check for any recent MP3 files
            if not file_path:
                mp3_files = list(download_path.glob("*.mp3"))
                if mp3_files:
                    # Sort by creation time, newest first
                    mp3_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                    file_path = str(mp3_files[0])
                    logger.info(f"Using most recent MP3 file: {file_path}")
            
            if file_path:
                # Update the task with the correct path
                await download_task_manager.update_task(
                    task, 
                    output_path=file_path,
                    status=DownloadStatus.COMPLETE,
                    error=None
                )
                
                logger.info(f"Serving file from: {file_path}")
                
                # Get file info
                file_stats = Path(file_path).stat()
                filename = os.path.basename(file_path)
                
                # Register background task to clean up file after serving
                background_tasks.add_task(cleanup_after_download, file_path, [file_path])
                
                # Return file response with cleanup scheduled
                return FileResponse(
                    file_path,
                    media_type="audio/mpeg",
                    filename=filename
                )
            
            # If we still couldn't find a file
            logger.error(f"Could not locate any file for task {task_id}")
            raise HTTPException(status_code=404, detail="File not found")
            
        # Normal case where output_path is set correctly
        logger.info(f"Task output_path is set to: {task.output_path}")
        
        # Handle Docker container path mapping
        file_path = task.output_path
        original_path = file_path
        
        # Check for container path and convert to host path if needed
        if file_path.startswith('/app/downloads/'):
            # Convert container path to host path
            host_file_path = file_path.replace('/app/downloads/', 'server/downloads/')
            logger.info(f"Converting container path {file_path} to host path {host_file_path}")
            
            if Path(host_file_path).exists():
                file_path = host_file_path
                logger.info(f"Using remapped host path: {file_path}")
            else:
                logger.warning(f"Remapped host path {host_file_path} does not exist, attempting to find file")
                
                # Try to find the file by basename in host downloads directory
                base_filename = os.path.basename(file_path)
                potential_path = Path(host_path) / base_filename
                if potential_path.exists():
                    file_path = str(potential_path)
                    logger.info(f"Found file by basename at: {file_path}")
                else:
                    logger.warning(f"File not found by basename either: {base_filename}")
        elif not file_path.startswith('/') and not Path(file_path).exists():
            # If it's a relative path, make sure it exists
            # Try prepending the host path
            potential_path = Path(host_path) / file_path
            if potential_path.exists():
                file_path = str(potential_path)
                logger.info(f"Converting relative path to full path: {file_path}")
        
        # Double-check if the file exists at the resolved path
        if not Path(file_path).exists():
            logger.error(f"File not found at path: {file_path}")
            
            # Try to search for the file by name in the downloads directory
            filename = os.path.basename(file_path)
            
            # Search for any file with a similar name
            potential_files = list(Path(host_path).glob(f"*{filename}*"))
            if potential_files:
                # Use the most recently modified file
                potential_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                file_path = str(potential_files[0])
                logger.info(f"Found similar file at: {file_path}")
            else:
                # Try searching for recent files of the right type
                extensions = ['.mp3', '.m4a', '.zip']
                for ext in extensions:
                    recent_files = list(Path(host_path).glob(f"*{ext}"))
                    if recent_files:
                        recent_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                        file_path = str(recent_files[0])
                        logger.info(f"Using most recent {ext} file: {file_path}")
                        break
                
                # If we still can't find anything, give up
                if not Path(file_path).exists():
                    logger.error(f"All attempts to find file failed. Original path: {original_path}")
                    raise HTTPException(status_code=404, detail=f"File not found at {file_path}")
        
        # Get filename from path
        filename = os.path.basename(file_path)
        
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
        
        logger.info(f"Serving file {filename} with media type {media_type} from path {file_path}")
        
        # Update the task with the correct path if it changed
        if file_path != original_path:
            await download_task_manager.update_task(
                task, 
                output_path=file_path
            )
        
        # Register background task to clean up file after serving
        background_tasks.add_task(cleanup_after_download, file_path, [file_path])
        
        # Return the file response
        return FileResponse(
            path=file_path,
            media_type=media_type,
            filename=filename
        )
        
    except Exception as e:
        logger.error(f"Error in download file endpoint: {e}")
        # Format error message for better client feedback
        error_message = str(e)
        if "No such file or directory" in error_message:
            error_message = "File not found on server. It may have been cleaned up or moved."
        elif "Permission denied" in error_message:
            error_message = "Server doesn't have permission to access the file."
            
        raise HTTPException(status_code=500, detail=error_message)

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