#!/usr/bin/env python3
import asyncio
import logging
import os
import sys
import subprocess
import json
from pathlib import Path
import shutil

# Add the server directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), "server"))

# Import our download strategy
from src.services.download_strategies.ytdlp_strategy import YtdlpStrategy

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("test_download")

# Test URLs - we'll try this with the strategy
TEST_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # Rick Astley - Never Gonna Give You Up

# Output directory for downloaded files
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)


def verify_file_content(file_path):
    """
    Verify that the file is a valid MP3 with audio content using ffprobe
    """
    if not file_path.exists():
        logger.error(f"File does not exist: {file_path}")
        return False
    
    # Get file size
    file_size = file_path.stat().st_size
    if file_size < 1000:  # Less than 1KB
        logger.error(f"File is too small to be valid: {file_size} bytes")
        return False
    
    logger.info(f"File size: {file_size} bytes")
    
    # Use ffprobe to check audio stream
    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", 
               "-of", "default=noprint_wrappers=1:nokey=1", str(file_path)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if "audio" in result.stdout:
            logger.info(f"File contains valid audio stream: {file_path}")
            return True
        else:
            logger.error(f"No audio stream found in file: {file_path}")
            return False
    except Exception as e:
        logger.error(f"Error verifying file with ffprobe: {e}")
        return False


async def test_ytdlp_strategy():
    """Test downloading with YtdlpStrategy"""
    logger.info("Testing YtdlpStrategy...")
    
    # Ensure no cookie file exists that might interfere with the test
    cookie_file = Path('youtube.cookies')
    if cookie_file.exists():
        logger.info(f"Renaming existing cookie file temporarily")
        shutil.move(cookie_file, cookie_file.with_suffix('.bak'))
    
    strategy = YtdlpStrategy()
    
    try:
        # Get video info
        logger.info(f"Getting info for {TEST_URL}")
        try:
            info = await strategy.get_info(TEST_URL)
            logger.info(f"Video title: {info.get('title', 'Unknown')}")
        except Exception as e:
            logger.error(f"Error getting video info: {e}")
            # Continue with download even if info fails
            info = {"title": "test_video"}
        
        # Create safe filename
        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in info["title"])
        output_path = OUTPUT_DIR / f"ytdlp_{safe_title}.mp3"
        
        # Download audio
        logger.info(f"Downloading audio for {info['title']}")
        try:
            result = await strategy.download(TEST_URL, output_path)
            logger.info(f"Download result: {result}")
            
            # Verify the file
            if result and Path(result).exists():
                is_valid = verify_file_content(Path(result))
                return is_valid
        except Exception as e:
            logger.error(f"Error during download: {e}")
            
        # Restore cookie file if it was renamed
        cookie_bak = Path('youtube.cookies.bak')
        if cookie_bak.exists():
            shutil.move(cookie_bak, cookie_file)
            
        return False
    except Exception as e:
        logger.error(f"Error testing YtdlpStrategy: {e}")
        return False
    finally:
        # Cleanup
        await strategy.cleanup()


async def main():
    """Run the test"""
    logger.info("Starting YouTube download test")
    
    try:
        logger.info("Testing YtdlpStrategy...")
        ytdlp_success = await test_ytdlp_strategy()
        
        # Display summary
        logger.info("")
        logger.info("-----------------------------------")
        logger.info("Verification Summary:")
        
        if ytdlp_success:
            logger.info("✅ YtdlpStrategy: Download successful and verified")
            return 0
        else:
            logger.error("❌ No files were downloaded successfully.")
            return 1
    except Exception as e:
        logger.error(f"Error in test execution: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code) 