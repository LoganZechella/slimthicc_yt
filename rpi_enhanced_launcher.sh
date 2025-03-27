#!/bin/bash
# Enhanced launcher script for Slim Thicc YouTube Downloader on Raspberry Pi

# Change to the application directory
cd "$(dirname "$0")"

# Create logs directory if it doesn't exist
mkdir -p logs

# Get current date and time for log filename
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="logs/app_${TIMESTAMP}.log"

# Check if system dependencies are installed
echo "Checking dependencies..." | tee -a "$LOG_FILE"

if ! command -v ffmpeg &> /dev/null; then
    echo "FFmpeg is not installed. Please install it with: sudo apt install ffmpeg" | tee -a "$LOG_FILE"
    echo "Would you like to install FFmpeg now? (y/n)"
    read -r response
    if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        echo "Installing FFmpeg..." | tee -a "$LOG_FILE"
        sudo apt update && sudo apt install -y ffmpeg
        if [ $? -ne 0 ]; then
            echo "Failed to install FFmpeg. Please install it manually." | tee -a "$LOG_FILE"
            exit 1
        fi
    else
        echo "FFmpeg is required for audio conversion. Please install it manually." | tee -a "$LOG_FILE"
        exit 1
    fi
fi

# Check for Qt dependencies
if ! dpkg -l | grep -q libqt6gui6; then
    echo "Qt6 GUI libraries not found. Please install them with: sudo apt install libqt6gui6 libqt6widgets6" | tee -a "$LOG_FILE"
    echo "Would you like to install Qt6 libraries now? (y/n)"
    read -r response
    if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        echo "Installing Qt6 libraries..." | tee -a "$LOG_FILE"
        sudo apt update && sudo apt install -y libqt6gui6 libqt6widgets6
        if [ $? -ne 0 ]; then
            echo "Failed to install Qt6 libraries. Trying to install Qt5 libraries instead..." | tee -a "$LOG_FILE"
            sudo apt install -y libqt5gui5 libqt5widgets5
            if [ $? -ne 0 ]; then
                echo "Failed to install Qt libraries. Please install them manually." | tee -a "$LOG_FILE"
                exit 1
            fi
        fi
    else
        echo "Qt libraries are required for the GUI. Please install them manually." | tee -a "$LOG_FILE"
        exit 1
    fi
fi

# Check memory and CPU status
echo "System status:" | tee -a "$LOG_FILE"
echo "Memory:" | tee -a "$LOG_FILE"
free -h | tee -a "$LOG_FILE"
echo "CPU:" | tee -a "$LOG_FILE"
cat /proc/cpuinfo | grep "model name" | head -1 | tee -a "$LOG_FILE"
echo "Temperature:" | tee -a "$LOG_FILE"
vcgencmd measure_temp 2>/dev/null | tee -a "$LOG_FILE" || echo "Temperature check not available" | tee -a "$LOG_FILE"

# Set environment variables
export QT_QPA_PLATFORM=xcb
export PYTHONUNBUFFERED=1

# Create config directory if it doesn't exist
mkdir -p config

# Create default settings file if it doesn't exist
if [ ! -f config/settings.json ]; then
    echo "Creating default settings file..." | tee -a "$LOG_FILE"
    cat > config/settings.json << 'EOF'
{
  "download_directory": "/home/pi/Downloads/SlimThicc",
  "max_concurrent_downloads": 2,
  "default_audio_quality": "high",
  "use_system_ffmpeg": true,
  "log_level": "info",
  "optimize_for_raspberry_pi": true
}
EOF
fi

# Create downloads directory if it doesn't exist
mkdir -p ~/Downloads/SlimThicc

# Run the application with logging
echo "Starting Slim Thicc YouTube Downloader at $(date)" | tee -a "$LOG_FILE"
chmod +x ./slim_thicc_yt
./slim_thicc_yt "$@" 2>&1 | tee -a "$LOG_FILE"

# Check exit status
EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo "Application exited with code $EXIT_CODE at $(date)" | tee -a "$LOG_FILE"
    
    # Write more detailed error information if available
    if [ -f ~/.xsession-errors ]; then
        echo "X session errors:" | tee -a "$LOG_FILE"
        tail -n 20 ~/.xsession-errors | tee -a "$LOG_FILE"
    fi
else
    echo "Application closed normally at $(date)" | tee -a "$LOG_FILE"
fi

# Clean up old logs (keep only the latest 10)
find logs -name "app_*.log" -type f -printf '%T@ %p\n' | sort -n | head -n -10 | cut -d' ' -f2- | xargs rm -f

echo "Session completed. Log file: $LOG_FILE" 