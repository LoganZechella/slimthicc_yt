import asyncio
import logging
from pathlib import Path
from typing import Dict, Optional, AsyncGenerator
from src.models.download import DownloadTask, DownloadStatus, DownloadError
from src.services.download_strategies.strategy_selector import StrategySelector
from src.services.websocket_manager import websocket_manager
from src.config.settings import settings
from src.config.database import db, ensure_connection
from datetime import datetime
from uuid import uuid4
import os
import re

logger = logging.getLogger(__name__)

class DownloadTaskManager:
    """Manages download tasks and their execution."""
    
    def __init__(self):
        self.active_downloads: Dict[str, DownloadTask] = {}
        self.strategy_selector = StrategySelector()
        self.download_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_DOWNLOADS)
        
    async def create_task(self, url: str, quality: str = None) -> DownloadTask:
        """Create a new download task."""
        try:
            # Generate a unique task ID
            task_id = str(uuid4())
            logger.info(f"Creating download task {task_id} for URL: {url}")
            
            # Ensure MongoDB connection
            mongo_db = await ensure_connection()
            
            # Convert URL to string if needed
            url_str = str(url)
            
            # Check if this is a Spotify URL
            is_spotify_url = False
            if 'spotify.com' in url_str or 'spotify:' in url_str:
                is_spotify_url = True
                logger.info(f"Spotify URL detected for task {task_id}")
                # Check if Spotify credentials are set
                if not settings.SPOTIFY_CLIENT_ID or not settings.SPOTIFY_CLIENT_SECRET:
                    logger.error("Spotify API credentials are not set. Please set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET environment variables.")
                    raise DownloadError("Spotify API credentials are not set. Please set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET environment variables.")
            
            # Get appropriate strategy
            result = await self.strategy_selector.get_strategy(url_str)
            if not result:
                if is_spotify_url:
                    logger.error("Spotify URL detected but Spotify API credentials are not configured.")
                    raise DownloadError("Spotify URL detected but Spotify API credentials are not configured. Please set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET environment variables.")
                else:
                    logger.error(f"No suitable download strategy found for URL: {url_str}")
                    raise DownloadError("No suitable download strategy found for URL")
                
            strategy, _ = result
            logger.info(f"Selected strategy {strategy.__class__.__name__} for URL: {url_str}")
            
            # Get video info
            logger.info(f"Getting video info for URL: {url_str}")
            info = await strategy.get_info(url_str)
            if not info:
                logger.error(f"Failed to get video information for URL: {url_str}")
                raise DownloadError("Failed to get video information")
                
            # Create task
            task = DownloadTask(
                id=task_id,
                url=url_str,
                title=info.get('title', 'Unknown'),
                author=info.get('author', 'Unknown'),
                status=DownloadStatus.PENDING,
                quality=quality or settings.DEFAULT_AUDIO_QUALITY,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            # Store task in memory and database
            self.active_downloads[task.id] = task
            await mongo_db.downloads.insert_one(task.model_dump())
            
            # Start download in background
            asyncio.create_task(self._process_download(task))
            
            # Log task creation
            logger.info(f"Created download task: {task.id} for URL: {url_str}, title: {task.title}")
            
            return task
            
        except Exception as e:
            logger.error(f"Error creating download task: {e}")
            raise DownloadError(f"Failed to create download task: {str(e)}")
            
    async def get_task(self, task_id: str) -> Optional[DownloadTask]:
        """Get task by ID."""
        # Check memory first
        if task_id in self.active_downloads:
            return self.active_downloads[task_id]
            
        # Check database
        try:
            mongo_db = await ensure_connection()
            task_data = await mongo_db.downloads.find_one({"id": task_id})
            if task_data:
                task = DownloadTask(**task_data)
                if task.status in [DownloadStatus.PENDING, DownloadStatus.DOWNLOADING, DownloadStatus.PROCESSING]:
                    self.active_downloads[task.id] = task
                return task
        except Exception as e:
            logger.error(f"Error retrieving task from database: {e}")
            
        return None
        
    async def update_task(self, task: DownloadTask, **updates) -> DownloadTask:
        """Update task status and persist to database."""
        try:
            mongo_db = await ensure_connection()
            
            # Update task attributes
            for key, value in updates.items():
                setattr(task, key, value)
            task.updated_at = datetime.utcnow()
            
            # Update in database
            await mongo_db.downloads.update_one(
                {"id": task.id},
                {"$set": task.model_dump()}
            )
            
            # Update in memory if active
            if task.id in self.active_downloads:
                self.active_downloads[task.id] = task
                
            return task
            
        except Exception as e:
            logger.error(f"Error updating task in database: {e}")
            raise
            
    async def _process_download(self, task: DownloadTask):
        """Process a download task."""
        try:
            logger.info(f"Starting download process for task {task.id} - URL: {task.url}")
            
            # Check if this is a Spotify URL
            is_spotify_url = 'spotify.com' in task.url or 'spotify:' in task.url
            
            async with self.download_semaphore:
                # Update task status
                await self.update_task(task, status=DownloadStatus.DOWNLOADING)
                logger.info(f"Task {task.id} status updated to DOWNLOADING")
                
                # Get strategy
                result = await self.strategy_selector.get_strategy(task.url)
                if not result:
                    logger.error(f"No suitable download strategy found for task {task.id}")
                    raise DownloadError("No suitable download strategy found")
                    
                strategy, strategy_index = result
                strategy_name = strategy.__class__.__name__
                logger.info(f"Using strategy {strategy_name} for task {task.id}")
                
                # Check for SpotifyStrategy which returns multiple files
                handle_spotify_separately = is_spotify_url and strategy_name == "SpotifyStrategy"
                
                # Prepare output path
                output_dir = Path(settings.DOWNLOADS_DIR)
                output_dir.mkdir(parents=True, exist_ok=True)
                output_path = output_dir / f"{task.id}.mp3"
                logger.info(f"Output path set to {output_path}")
                
                # Special handling for Spotify downloads
                if handle_spotify_separately:
                    # Inform frontend this is a special strategy
                    await websocket_manager.broadcast_progress(
                        task_id=task.id,
                        progress=0,
                        status='downloading',
                        details={
                            'strategy': strategy_name,
                            'isSpotifyPlaylist': True,
                            'statusMessage': "Starting Spotify playlist download with YouTube backing"
                        }
                    )
                
                # Start download with progress tracking
                try:
                    logger.info(f"Starting download with strategy {strategy_name} for task {task.id}")
                    strategy_attempts = 0
                    last_error = None
                    
                    async for progress in strategy.download(task.url, output_path, task.quality):
                        if task.status == DownloadStatus.CANCELLED:
                            # Clean up if cancelled
                            logger.info(f"Task {task.id} was cancelled, cleaning up")
                            if output_path.exists():
                                output_path.unlink()
                                logger.info(f"Deleted output file {output_path} for cancelled task")
                            return
                            
                        # Extract progress information
                        progress_status = progress.get('status', 'downloading')
                        progress_percent = progress.get('progress', 0)
                        progress_details = progress.get('details', '')
                        progress_error = progress.get('error', None)
                        
                        logger.debug(f"Progress update for task {task.id}: {progress_status} - {progress_percent}% - Details: {progress_details}")
                            
                        if progress_status == 'error':
                            # Check for specific YouTube signature extraction failures
                            error_message = progress_error or ''
                            last_error = error_message
                            logger.error(f"Strategy {strategy_name} failed for task {task.id}: {error_message}")
                            
                            # Quickly switch to Invidious if YouTube has signature issues
                            if any(x in error_message.lower() for x in ["signature", "cipher", "unable to extract", "youtube said: error", "precondition check"]):
                                logger.warning(f"YouTube signature issue detected, switching to Invidious strategy for task {task.id}")
                                
                                # Force switch to Invidious (index 1)
                                if strategy_index == 0 and len(self.strategy_selector.strategies) > 1:
                                    next_strategy = self.strategy_selector.strategies[1]  # Invidious is at index 1
                                    next_strategy_name = next_strategy.__class__.__name__
                                    logger.info(f"Switching directly to {next_strategy_name} for task {task.id}")
                                    
                                    # Send strategy change notification to frontend
                                    await websocket_manager.broadcast_progress(
                                        task_id=task.id,
                                        progress=0,
                                        status='downloading',
                                        details={
                                            'strategy': next_strategy_name,
                                            'statusMessage': f"Trying different download method: {next_strategy_name}"
                                        }
                                    )
                                    
                                    # Use Invidious strategy
                                    if output_path.exists():
                                        try:
                                            output_path.unlink()
                                            logger.info(f"Removed partial file before strategy switch: {output_path}")
                                        except Exception as e:
                                            logger.error(f"Error removing partial file: {e}")
                                            
                                    # Try with new strategy
                                    async for new_progress in next_strategy.download(task.url, output_path, task.quality):
                                        # Forward progress updates
                                        await websocket_manager.broadcast_progress(
                                            task_id=task.id,
                                            progress=new_progress.get('progress', 0),
                                            status=new_progress.get('status', 'downloading'),
                                            details={'strategy': next_strategy_name}
                                        )
                                        
                                        # Update task progress
                                        await self.update_task(
                                            task,
                                            progress=new_progress.get('progress', 0),
                                            status=DownloadStatus(new_progress.get('status', 'downloading'))
                                        )
                                        
                                        # Handle errors in fallback strategy
                                        if new_progress['status'] == 'error':
                                            logger.error(f"Fallback strategy {next_strategy_name} also failed: {new_progress.get('error', '')}")
                                            break
                                            
                                        # Handle completion
                                        if new_progress['status'] == 'complete':
                                            logger.info(f"Fallback strategy {next_strategy_name} succeeded for task {task.id}")
                                            await self.update_task(
                                                task,
                                                status=DownloadStatus.COMPLETE,
                                                progress=100,
                                                output_path=str(output_path),
                                                updated_at=datetime.utcnow()
                                            )
                                            return
                                
                            # Try next strategy (normal flow)
                            await self.strategy_selector._mark_strategy_failure(strategy_index)
                            
                            strategy_attempts += 1
                            if strategy_attempts >= 3:
                                logger.warning(f"Maximum strategy attempts reached for task {task.id}")
                                break
                                
                            next_result = await self.strategy_selector.try_next_strategy(task.url)
                            if next_result:
                                strategy, strategy_index = next_result
                                strategy_name = strategy.__class__.__name__
                                logger.info(f"Switching to next strategy {strategy_name} for task {task.id}")
                                
                                # Send strategy change notification to frontend
                                await websocket_manager.broadcast_progress(
                                    task_id=task.id,
                                    progress=0,
                                    status='downloading',
                                    details={
                                        'strategy': strategy_name,
                                        'statusMessage': f"Trying different download method: {strategy_name}"
                                    }
                                )
                                continue
                            else:
                                logger.error(f"All download strategies failed for task {task.id}")
                                await self.update_task(
                                    task,
                                    status=DownloadStatus.ERROR,
                                    error=f"All download strategies failed: {error_message}"
                                )
                                raise DownloadError(f"All download strategies failed: {error_message}")
                                
                        # Get file information if available
                        file_info = {}
                        if output_path.exists():
                            try:
                                file_info = {
                                    'size': output_path.stat().st_size,
                                    'path': str(output_path),
                                }
                                # Try to get file type
                                if os.path.exists('/usr/bin/file'):
                                    import subprocess
                                    try:
                                        file_type = subprocess.check_output(['file', '-b', str(output_path)], text=True).strip()
                                        file_info['type'] = file_type
                                    except Exception as e:
                                        logger.error(f"Error getting file type: {e}")
                            except Exception as e:
                                logger.error(f"Error getting file info: {e}")
                        
                        # Create detailed status message
                        status_message = None
                        if progress_status == 'downloading':
                            status_message = f"Downloading audio using {strategy_name} ({progress_percent:.1f}%)"
                        elif progress_status == 'processing':
                            status_message = f"Processing audio file with {strategy_name}"
                        elif progress_status == 'complete':
                            status_message = f"Download complete! File size: {file_info.get('size', 0) / 1024 / 1024:.1f} MB"
                            
                        # Special handling for Spotify detailed progress messages
                        if is_spotify_url and progress_details:
                            # Use Spotify's own progress details as status message
                            status_message = progress_details
                        
                        # Prepare WebSocket message details
                        ws_details = {
                            'strategy': strategy_name,
                            'statusMessage': status_message or progress_details  # Use progress_details as fallback
                        }
                        
                        # Add file info if available
                        if file_info:
                            ws_details['fileInfo'] = file_info
                            
                        # Add special Spotify flag if needed
                        if is_spotify_url:
                            ws_details['isSpotifyPlaylist'] = True
                        
                        # Update progress
                        logger.debug(f"Task {task.id} progress update: {progress_status} - {progress_percent:.2f}% - Details: {status_message}")
                        await websocket_manager.broadcast_progress(
                            task_id=task.id,
                            progress=progress_percent,
                            status=progress_status,
                            details=ws_details,
                            error=progress_error
                        )
                        
                        # Update task in database
                        await self.update_task(
                            task,
                            progress=progress_percent,
                            status=DownloadStatus.DOWNLOADING if progress_status == 'downloading'
                            else DownloadStatus.PROCESSING if progress_status == 'processing'
                            else DownloadStatus.COMPLETE if progress_status == 'complete'
                            else task.status
                        )
                        
                        # Handling Spotify playlists that return track details in progress updates
                        if is_spotify_url and progress_details:
                            # Check for successful file paths mentions
                            if 'tracks saved to' in progress_details.lower() and '/app/downloads' in progress_details:
                                logger.info(f"Found Spotify output directory in progress details: {progress_details}")
                                # Store this information for later
                                spotify_output_dir = progress_details.split('saved to')[-1].strip()
                                await self.update_task(
                                    task,
                                    spotify_output_dir=spotify_output_dir,
                                    status=DownloadStatus.COMPLETE if progress_status == 'complete' else task.status
                                )
                                
                                # Add output directory to WebSocket message
                                await websocket_manager.broadcast_progress(
                                    task_id=task.id,
                                    progress=progress_percent,
                                    status=progress_status,
                                    details={
                                        'strategy': strategy_name,
                                        'statusMessage': progress_details,
                                        'isSpotifyPlaylist': True,
                                        'spotifyOutputDir': spotify_output_dir,
                                        # Add download URL for frontend
                                        'downloadUrl': f"/api/v1/downloads/{task.id}/file"
                                    }
                                )
                        
                        if progress_status == 'complete':
                            # Verify file exists and has content
                            if output_path.exists() and output_path.stat().st_size > 0:
                                file_size = output_path.stat().st_size
                                logger.info(f"Download complete for task {task.id}, file saved at {output_path} ({file_size} bytes)")
                                
                                # Send final success message with file details
                                await websocket_manager.broadcast_progress(
                                    task_id=task.id,
                                    progress=100,
                                    status='complete',
                                    details={
                                        'strategy': strategy_name,
                                        'statusMessage': f"Download complete! File size: {file_size / 1024 / 1024:.1f} MB",
                                        'fileInfo': {
                                            'size': file_size,
                                            'path': str(output_path),
                                            'type': file_info.get('type', 'audio/mpeg')
                                        },
                                        # Add download URL for frontend
                                        'downloadUrl': f"/api/v1/downloads/{task.id}/file"
                                    }
                                )
                                
                                await self.update_task(
                                    task,
                                    status=DownloadStatus.COMPLETE,
                                    output_path=str(output_path)
                                )
                                
                                # Schedule cleanup of temporary resources
                                asyncio.create_task(self.cleanup_task(task.id))
                                
                                return
                            else:
                                # Check for Spotify multiple files
                                if is_spotify_url and strategy_name == "SpotifyStrategy":
                                    # Check the output message for file paths
                                    files_found = False
                                    
                                    # Look for the Spotify file directory
                                    spotify_output_dir = "/app/downloads" 
                                    
                                    # Log the possible success differently for Spotify
                                    logger.info(f"Spotify download reported complete. Checking for files in {spotify_output_dir}")
                                    
                                    # Include the directory in the error message for the file endpoint to use
                                    success_message = f"Download completed but tracks saved in {spotify_output_dir}. Use the download button to access files."
                                    
                                    await self.update_task(
                                        task,
                                        status=DownloadStatus.COMPLETE,
                                        spotify_output_dir=spotify_output_dir,
                                        error=success_message,  # This is not really an error but a message to the endpoint
                                        output_path="/app/downloads/playlist_files.mp3"  # Placeholder to mark as completed with files
                                    )
                                    
                                    # Send a final success message with download instructions
                                    await websocket_manager.broadcast_progress(
                                        task_id=task.id,
                                        progress=100,
                                        status='complete',
                                        details={
                                            'strategy': strategy_name,
                                            'statusMessage': "Spotify playlist download complete! Click the download button to get all tracks as a ZIP file.",
                                            'isSpotifyPlaylist': True,
                                            'spotifyOutputDir': spotify_output_dir,
                                            # Add direct download URL for frontend
                                            'downloadUrl': f"/api/v1/downloads/{task.id}/file",
                                            'fileType': 'zip'
                                        }
                                    )
                                    
                                    logger.info(f"Task {task.id} marked complete, tracks saved in {spotify_output_dir}")
                                    
                                    # Schedule cleanup of temporary resources for Spotify
                                    asyncio.create_task(self.cleanup_task(task.id))
                                    
                                    return
                                    
                                # Regular single file error
                                logger.error(f"Download reported complete but file not found or empty: {output_path}")
                                await self.update_task(
                                    task,
                                    status=DownloadStatus.ERROR,
                                    error=f"Download completed but file not found or is empty: {output_path}"
                                )
                                return
                            
                except Exception as e:
                    logger.error(f"Error during download for task {task.id}: {e}")
                    
                    # Check if file was partially downloaded
                    if output_path.exists():
                        file_size = output_path.stat().st_size
                        logger.info(f"Partial download exists for task {task.id}, size: {file_size} bytes")
                        
                        # Send error with file details
                        await websocket_manager.broadcast_progress(
                            task_id=task.id,
                            progress=0,
                            status='error',
                            error=f"Download failed: {str(e)}",
                            details={
                                'strategy': strategy_name,
                                'statusMessage': f"Download failed but partial file exists ({file_size / 1024 / 1024:.1f} MB)",
                                'fileInfo': {
                                    'size': file_size,
                                    'path': str(output_path),
                                    'partial': True
                                }
                            }
                        )
                        
                    await self.update_task(
                        task,
                        status=DownloadStatus.ERROR,
                        error=f"Download failed: {str(e)}"
                    )
                    raise DownloadError(f"Download failed: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Error processing download task {task.id}: {e}")
            await self.update_task(
                task,
                status=DownloadStatus.ERROR,
                error=str(e)
            )
            
    async def cleanup(self):
        """Clean up resources for all strategies."""
        await self.strategy_selector.cleanup()
        
    async def cleanup_task(self, task_id: str):
        """
        Clean up resources for a specific task.
        
        Args:
            task_id: ID of the task to clean up
        """
        logger.info(f"Cleaning up resources for task {task_id}")
        try:
            # Get the task from memory or database
            task = await self.get_task(task_id)
            
            if not task:
                logger.warning(f"Task {task_id} not found for cleanup")
                return
            
            # Only clean up temporary resources, not the final output files
            # Those will be handled by the router's cleanup_after_download function
            
            # Get the strategy used for the download
            url = task.url if hasattr(task, 'url') else None
            if url:
                strategy_result = await self.strategy_selector.get_strategy(url)
                if strategy_result:
                    strategy, _ = strategy_result
                    
                    # Ask the strategy to clean up its temporary resources
                    # This won't delete the final output files
                    await strategy.cleanup()
                    
            logger.info(f"Cleanup completed for task {task_id}")
                
        except Exception as e:
            logger.error(f"Error cleaning up task {task_id}: {e}")
        
# Create a global instance
download_task_manager = DownloadTaskManager() 