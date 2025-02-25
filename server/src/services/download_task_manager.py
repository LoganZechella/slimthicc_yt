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
            
            # Get appropriate strategy
            result = await self.strategy_selector.get_strategy(url_str)
            if not result:
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
                
                # Prepare output path
                output_dir = Path(settings.DOWNLOADS_DIR)
                output_dir.mkdir(parents=True, exist_ok=True)
                output_path = output_dir / f"{task.id}.mp3"
                logger.info(f"Output path set to {output_path}")
                
                # Start download with progress tracking
                try:
                    logger.info(f"Starting download with strategy {strategy_name} for task {task.id}")
                    strategy_attempts = 0
                    
                    async for progress in strategy.download(task.url, output_path, task.quality):
                        if task.status == DownloadStatus.CANCELLED:
                            # Clean up if cancelled
                            logger.info(f"Task {task.id} was cancelled, cleaning up")
                            if output_path.exists():
                                output_path.unlink()
                                logger.info(f"Deleted output file {output_path} for cancelled task")
                            return
                            
                        if progress['status'] == 'error':
                            # Try next strategy on error
                            logger.error(f"Strategy {strategy_name} failed for task {task.id}: {progress['error']}")
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
                                    error=f"All download strategies failed: {progress['error']}"
                                )
                                raise DownloadError(f"All download strategies failed: {progress['error']}")
                                
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
                        if progress['status'] == 'downloading':
                            status_message = f"Downloading audio using {strategy_name} ({progress['progress']:.1f}%)"
                        elif progress['status'] == 'processing':
                            status_message = f"Processing audio file with {strategy_name}"
                        elif progress['status'] == 'complete':
                            status_message = f"Download complete! File size: {file_info.get('size', 0) / 1024 / 1024:.1f} MB"
                        
                        # Update progress
                        logger.debug(f"Task {task.id} progress update: {progress['status']} - {progress['progress']:.2f}%")
                        await websocket_manager.broadcast_progress(
                            task_id=task.id,
                            progress=progress['progress'],
                            status=progress['status'],
                            details={
                                'strategy': strategy_name,
                                'statusMessage': status_message,
                                'fileInfo': file_info
                            }
                        )
                        
                        # Update task in database
                        await self.update_task(
                            task,
                            progress=progress['progress'],
                            status=DownloadStatus.DOWNLOADING if progress['status'] == 'downloading'
                            else DownloadStatus.PROCESSING if progress['status'] == 'processing'
                            else DownloadStatus.COMPLETE if progress['status'] == 'complete'
                            else task.status
                        )
                        
                        if progress['status'] == 'complete':
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
                                        }
                                    }
                                )
                                
                                await self.update_task(
                                    task,
                                    status=DownloadStatus.COMPLETE,
                                    output_path=str(output_path)
                                )
                                return
                            else:
                                logger.error(f"Download reported complete but file not found or empty: {output_path}")
                                await self.update_task(
                                    task,
                                    status=DownloadStatus.ERROR,
                                    error="Download completed but file not found or is empty"
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
        """Clean up resources."""
        await self.strategy_selector.cleanup()
        
# Create a global instance
download_task_manager = DownloadTaskManager() 