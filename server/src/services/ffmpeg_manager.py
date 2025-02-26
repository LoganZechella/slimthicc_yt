import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from src.config.settings import settings

logger = logging.getLogger(__name__)


class FFmpegManager:
    """
    Manages FFmpeg operations for audio processing
    """
    
    def __init__(self):
        """Initialize FFmpeg manager with settings"""
        self.ffmpeg_path = settings.FFMPEG_PATH
        self.threads = settings.FFMPEG_THREADS
        self.loglevel = settings.FFMPEG_LOGLEVEL
        
        logger.info(f"Initialized FFmpeg manager with path: {self.ffmpeg_path}")
    
    async def _run_ffmpeg_command(self, command: List[str]) -> Tuple[bool, Optional[str]]:
        """
        Run an FFmpeg command asynchronously
        
        Args:
            command: The FFmpeg command to run
            
        Returns:
            Tuple of (success, error message)
        """
        try:
            logger.debug(f"Running FFmpeg command: {' '.join(command)}")
            
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode().strip()
                logger.error(f"FFmpeg error (code {process.returncode}): {error_msg}")
                return False, error_msg
            
            return True, None
        
        except Exception as e:
            logger.error(f"Failed to run FFmpeg command: {e}")
            return False, str(e)
    
    async def validate_audio_file(self, file_path: Union[str, Path]) -> Tuple[bool, Optional[Dict]]:
        """
        Validate an audio file using FFprobe
        
        Args:
            file_path: Path to the audio file
            
        Returns:
            Tuple of (is_valid, metadata)
        """
        try:
            file_path = Path(file_path)
            
            if not file_path.exists():
                logger.error(f"File not found: {file_path}")
                return False, None
            
            # Use ffprobe to get file info
            command = [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(file_path)
            ]
            
            result = subprocess.run(command, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"FFprobe error: {result.stderr}")
                return False, None
            
            metadata = json.loads(result.stdout)
            
            # Check if file has audio streams
            has_audio = False
            for stream in metadata.get("streams", []):
                if stream.get("codec_type") == "audio":
                    has_audio = True
                    break
            
            if not has_audio:
                logger.error(f"No audio streams found in file: {file_path}")
                return False, metadata
            
            return True, metadata
        
        except Exception as e:
            logger.error(f"Error validating audio file: {e}")
            return False, None
    
    async def get_audio_duration(self, file_path: Union[str, Path]) -> Optional[float]:
        """
        Get the duration of an audio file
        
        Args:
            file_path: Path to the audio file
            
        Returns:
            Duration in seconds, or None if unsuccessful
        """
        is_valid, metadata = await self.validate_audio_file(file_path)
        
        if not is_valid or not metadata:
            return None
        
        # Get duration from format section
        try:
            return float(metadata.get("format", {}).get("duration", 0))
        except (ValueError, TypeError):
            logger.error(f"Could not parse duration from metadata: {metadata}")
            return None
    
    async def convert_audio(
        self, 
        input_path: Union[str, Path], 
        output_path: Union[str, Path], 
        format: str = "mp3",
        bitrate: str = "320k",
        normalize: bool = True
    ) -> bool:
        """
        Convert an audio file to the specified format
        
        Args:
            input_path: Path to the input file
            output_path: Path to save the output file
            format: Output format (default: mp3)
            bitrate: Output bitrate (default: 320k)
            normalize: Whether to normalize audio (default: True)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            input_path = Path(input_path)
            output_path = Path(output_path)
            
            # Ensure input file exists
            if not input_path.exists():
                logger.error(f"Input file not found: {input_path}")
                return False
            
            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Validate input file has audio
            is_valid, _ = await self.validate_audio_file(input_path)
            if not is_valid:
                logger.error(f"Input file is not a valid audio file: {input_path}")
                return False
            
            # Prepare FFmpeg arguments
            ffmpeg_args = [
                self.ffmpeg_path,
                "-y",  # Overwrite output files
                "-i", str(input_path),
                "-c:a", "libmp3lame" if format == "mp3" else "copy",
                "-b:a", bitrate,
                "-threads", str(self.threads),
                "-loglevel", self.loglevel
            ]
            
            # Add normalization if requested
            if normalize:
                ffmpeg_args.extend([
                    "-af", "loudnorm=I=-16:LRA=11:TP=-1.5"
                ])
            
            # Add output path
            ffmpeg_args.append(str(output_path))
            
            # Run conversion
            success, error_msg = await self._run_ffmpeg_command(ffmpeg_args)
            
            if not success:
                logger.error(f"Failed to convert audio: {error_msg}")
                return False
            
            # Verify output file exists and has content
            if not output_path.exists():
                logger.error(f"Output file not created: {output_path}")
                return False
            
            # Check file size (should be at least 1KB)
            if output_path.stat().st_size < 1024:
                logger.warning(f"Output file is suspiciously small: {output_path.stat().st_size} bytes")
            
            logger.info(f"Successfully converted audio to {format}: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error converting audio: {e}")
            return False
    
    async def cleanup(self):
        """
        Clean up resources (placeholder for now)
        """
        # Currently no resources to clean up
        pass


# Create a global instance
ffmpeg_manager = FFmpegManager() 