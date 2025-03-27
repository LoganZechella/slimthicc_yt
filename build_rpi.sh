#!/bin/bash
set -e

# Clean previous builds
rm -rf dist/raspberry-pi
mkdir -p dist/raspberry-pi

# Activate virtual environment
source slimthicc_rpi_venv/bin/activate

# Install dependencies if needed
pip install -r requirements_rpi.txt

# Build with PyInstaller for Raspberry Pi
# Using spec file directly since it already has target_arch='arm64' configured
pyinstaller --clean --distpath dist/raspberry-pi playlist_run_qt_rpi.spec

# Copy enhanced launcher script
cp rpi_enhanced_launcher.sh dist/raspberry-pi/slim_thicc_yt_rpi/run.sh
chmod +x dist/raspberry-pi/slim_thicc_yt_rpi/run.sh

# Copy system optimization script
cp rpi_optimize_system.sh dist/raspberry-pi/slim_thicc_yt_rpi/
chmod +x dist/raspberry-pi/slim_thicc_yt_rpi/rpi_optimize_system.sh

# Copy troubleshooting guide
cp TROUBLESHOOTING_RPI.md dist/raspberry-pi/slim_thicc_yt_rpi/TROUBLESHOOTING.md

# Create desktop entry file
cat > dist/raspberry-pi/slim_thicc_yt_rpi/SlimThicc.desktop << 'DESKTOP'
[Desktop Entry]
Name=Slim Thicc YouTube Downloader
Comment=Download YouTube and Spotify playlists
Exec=/home/pi/SlimThicc/run.sh
Icon=/home/pi/SlimThicc/icons/app_icon.png
Terminal=false
Type=Application
Categories=Utility;AudioVideo;
DESKTOP

# Create README for Raspberry Pi
cat > dist/raspberry-pi/README_RASPBERRY_PI.md << 'README'
# Slim Thicc YouTube Downloader for Raspberry Pi 5

## Installation Instructions

1. Extract the archive to your home directory:
   ```
   mkdir -p ~/SlimThicc
   cp -r slim_thicc_yt_rpi/* ~/SlimThicc/
   ```

2. Make scripts executable:
   ```
   chmod +x ~/SlimThicc/run.sh
   chmod +x ~/SlimThicc/slim_thicc_yt
   chmod +x ~/SlimThicc/rpi_optimize_system.sh
   ```

3. Create desktop shortcut:
   ```
   cp ~/SlimThicc/SlimThicc.desktop ~/Desktop/
   chmod +x ~/Desktop/SlimThicc.desktop
   ```

4. Install required system packages if not already installed:
   ```
   sudo apt update
   sudo apt install -y ffmpeg libqt6gui6 libqt6widgets6
   ```
   
   If Qt6 is not available on your Raspberry Pi OS, try Qt5 instead:
   ```
   sudo apt install -y libqt5gui5 libqt5widgets5
   ```

5. Optimize your Raspberry Pi (optional but recommended):
   ```
   sudo ~/SlimThicc/rpi_optimize_system.sh
   ```

6. Run the application:
   ```
   ~/SlimThicc/run.sh
   ```

## Features

- Download YouTube videos and playlists as MP3
- Download Spotify playlists through YouTube search
- Optimized for Raspberry Pi 5 and touchscreens
- Automatic error handling and dependency checking
- Performance optimizations for Raspberry Pi

## Troubleshooting

If you encounter any issues, please check the troubleshooting guide:
~/SlimThicc/TROUBLESHOOTING.md

Log files are stored in:
~/SlimThicc/logs/

For further assistance, visit: https://github.com/LoganZechella/slimthicc_yt/issues
README

# Create logs and config directory structure in the package
mkdir -p dist/raspberry-pi/slim_thicc_yt_rpi/logs
mkdir -p dist/raspberry-pi/slim_thicc_yt_rpi/config
mkdir -p dist/raspberry-pi/slim_thicc_yt_rpi/icons

# Create default settings file
cat > dist/raspberry-pi/slim_thicc_yt_rpi/config/settings.json << 'SETTINGS'
{
  "download_directory": "/home/pi/Downloads/SlimThicc",
  "max_concurrent_downloads": 2,
  "default_audio_quality": "high",
  "use_system_ffmpeg": true,
  "log_level": "info",
  "optimize_for_raspberry_pi": true
}
SETTINGS

# Create an archive for distribution
cd dist/raspberry-pi
tar -czvf ../slim_thicc_yt_rpi.tar.gz slim_thicc_yt_rpi README_RASPBERRY_PI.md
cd ../..

echo "Build for Raspberry Pi completed successfully."
echo "Final package is available at: dist/slim_thicc_yt_rpi.tar.gz" 