import asyncio
import logging
import re
from pathlib import Path
from typing import Optional, Dict, List, Tuple
import json
from src.config.settings import settings

logger = logging.getLogger(__name__)

class FFmpegManager:
    """Manages FFmpeg operations for audio processing."""
    
    def __init__(self):
        self.ffmpeg_path = settings.FFMPEG_PATH
        self.threads = settings.FFMPEG_THREADS
        self.loglevel = settings.FFMPEG_LOGLEVEL
        
    async def _run_ffmpeg_command(self, args: List[str]) -> Tuple[bool, str]:
        """
        Run an FFmpeg command and capture output.
        
        Args:
            args: List of command arguments
            
        Returns:
            Tuple of (success, error_message)
        """
        try:
            process = await asyncio.create_subprocess_exec(
                self.ffmpeg_path,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            success = process.returncode == 0
            
            if not success:
                error_msg = stderr.decode().strip() if stderr else "Unknown FFmpeg error"
                logger.error(f"FFmpeg command failed: {error_msg}")
                return False, error_msg
            
            return True, ""
            
        except Exception as e:
            logger.error(f"Error running FFmpeg command: {e}")
            return False, str(e)
            
    async def validate_audio_file(self, file_path: str) -> Tuple[bool, Optional[Dict]]:
        """
        Validate an audio file using FFprobe.
        
        Args:
            file_path: Path to audio file
            
        Returns:
            Tuple of (is_valid, metadata)
        """
        try:
            args = [
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                file_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                "ffprobe",
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"FFprobe validation failed: {stderr.decode().strip()}")
                return False, None
                
            metadata = json.loads(stdout)
            
            # Check if file has audio stream
            has_audio = any(
                stream.get("codec_type") == "audio" 
                for stream in metadata.get("streams", [])
            )
            
            if not has_audio:
                logger.error("No audio stream found in file")
                return False, metadata
                
            return True, metadata
            
        except Exception as e:
            logger.error(f"Error validating audio file: {e}")
            return False, None
            
    async def get_audio_duration(self, file_path: str) -> Optional[float]:
        """
        Get audio file duration in seconds.
        
        Args:
            file_path: Path to audio file
            
        Returns:
            Duration in seconds or None if error
        """
        try:
            valid, metadata = await self.validate_audio_file(file_path)
            if not valid or not metadata:
                return None
                
            duration = metadata.get("format", {}).get("duration")
            return float(duration) if duration else None
            
        except Exception as e:
            logger.error(f"Error getting audio duration: {e}")
            return None
            
    async def convert_audio(
        self,
        input_path: str,
        output_path: str,
        bitrate: str = "192k",
        normalize: bool = True
    ) -> bool:
        """
        Convert audio file to specified format with optional normalization.
        
        Args:
            input_path: Path to input file
            output_path: Path to output file
            bitrate: Audio bitrate (default: 192k)
            normalize: Whether to normalize audio (default: True)
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Validate input file
            valid, _ = await self.validate_audio_file(input_path)
            if not valid:
                logger.error("Input file validation failed")
                return False
                
            # Prepare FFmpeg arguments
            args = [
                "-y",  # Overwrite output file
                "-i", input_path,
                "-threads", str(self.threads),
                "-loglevel", self.loglevel
            ]
            
            if normalize:
                # Add audio normalization filter
                args.extend([
                    "-af", "loudnorm=I=-16:LRA=11:TP=-1.5"
                ])
            
            # Add output options
            args.extend([
                "-vn",  # No video
                "-ar", "44100",  # Sample rate
                "-ac", "2",  # Stereo
                "-b:a", bitrate,  # Bitrate
                "-f", "mp3",  # Force MP3 format
                output_path
            ])
            
            # Run conversion
            success, error = await self._run_ffmpeg_command(args)
            
            if success:
                # Validate output file
                valid, _ = await self.validate_audio_file(output_path)
                if not valid:
                    logger.error("Output file validation failed")
                    return False
                    
                # Check if output file has reasonable size
                output_size = Path(output_path).stat().st_size
                if output_size < 1024:  # Less than 1KB
                    logger.error("Output file is suspiciously small")
                    return False
                    
                return True
            else:
                logger.error(f"Conversion failed: {error}")
                return False
                
        except Exception as e:
            logger.error(f"Error converting audio: {e}")
            return False
            
    async def cleanup(self):
        """Cleanup any resources."""
        pass  # No cleanup needed currently

ffmpeg_manager = FFmpegManager() 