# Troubleshooting Guide for Slim Thicc YouTube Downloader on Raspberry Pi

This guide aims to help you diagnose and fix common issues when running Slim Thicc YouTube Downloader on Raspberry Pi.

## Table of Contents
1. [Application Won't Start](#application-wont-start)
2. [GUI Issues](#gui-issues)
3. [Download Issues](#download-issues)
4. [Performance Problems](#performance-problems)
5. [Audio Conversion Problems](#audio-conversion-problems)
6. [System Requirements](#system-requirements)
7. [Logs and Diagnostics](#logs-and-diagnostics)
8. [Updating the Application](#updating-the-application)

## Application Won't Start

### Missing Dependencies

If the application fails to start, first check for missing dependencies:

```bash
sudo apt update
sudo apt install -y ffmpeg libqt6gui6 libqt6widgets6
```

If Qt6 is not available on your Raspberry Pi OS, try Qt5 instead:

```bash
sudo apt install -y libqt5gui5 libqt5widgets5
```

### Environment Issues

If you get "Cannot connect to X server" or similar errors:

1. Make sure you're running the application in a desktop environment, not just from SSH
2. Try setting the display explicitly:
   ```bash
   export DISPLAY=:0
   ~/SlimThicc/run.sh
   ```

### Permission Problems

Check file permissions:

```bash
cd ~/SlimThicc
ls -la
```

Make sure executable files have the right permissions:

```bash
chmod +x ~/SlimThicc/run.sh
chmod +x ~/SlimThicc/slim_thicc_yt
```

### Corrupt Installation

Try reinstalling:

```bash
# Backup your settings
cp -r ~/SlimThicc/config ~/slimthicc_config_backup

# Reinstall
rm -rf ~/SlimThicc
mkdir -p ~/SlimThicc
# Extract from the original archive again...

# Restore your settings
cp -r ~/slimthicc_config_backup/* ~/SlimThicc/config/
```

## GUI Issues

### Display Too Small or Large

If the GUI elements are too small or large:

```bash
# For larger GUI elements
export QT_SCALE_FACTOR=1.5
~/SlimThicc/run.sh

# For smaller GUI elements
export QT_SCALE_FACTOR=0.8
~/SlimThicc/run.sh
```

### Touchscreen Issues

If using a touchscreen and having problems with touch precision:

1. Edit the Qt configuration:
   ```bash
   mkdir -p ~/.config/QtProject
   echo "[Bridge::EglFSFunctions]" > ~/.config/QtProject/qtconfig
   echo "TouchDevices=1" >> ~/.config/QtProject/qtconfig
   ```

2. Run with touch-specific environment:
   ```bash
   export QT_QPA_EGLFS_HIDECURSOR=1
   export QT_QPA_PLATFORM=eglfs
   ~/SlimThicc/run.sh
   ```

### Blank/Black Screen Issues

If you get a black screen when starting:

```bash
# Try using X11 platform
export QT_QPA_PLATFORM=xcb
~/SlimThicc/run.sh

# Alternative, try framebuffer
export QT_QPA_PLATFORM=linuxfb
~/SlimThicc/run.sh
```

## Download Issues

### YouTube Downloads Fail

If YouTube videos fail to download:

1. Check your internet connection:
   ```bash
   ping -c 3 youtube.com
   ```

2. Make sure yt-dlp is up to date by running the enhanced launcher script which checks this.

3. Check for YouTube blocks by examining the log file:
   ```bash
   cat ~/SlimThicc/logs/app_*.log | grep -i "error\|failed"
   ```

4. Try with a different user agent:
   ```bash
   # Create a temporary test download script
   cat > ~/test_youtube_dl.sh << 'EOF'
   #!/bin/bash
   cd ~/SlimThicc
   yt-dlp --user-agent "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.82 Safari/537.36" -x --audio-format mp3 "https://www.youtube.com/watch?v=dQw4w9WgXcQ" -o "test_download.%(ext)s"
   EOF
   chmod +x ~/test_youtube_dl.sh
   ~/test_youtube_dl.sh
   ```

### Spotify Authentication Issues

If Spotify playlist retrieval fails:

1. Check your Spotify credentials:
   ```bash
   # Look for credential errors in the log
   cat ~/SlimThicc/logs/app_*.log | grep -i "spotify\|credential\|auth"
   ```

2. Re-enter your Spotify API credentials in the application.

3. Make sure your Spotify Developer Application has the correct callback URLs set.

## Performance Problems

### Slow Downloads

If downloads are too slow:

1. Run the optimization script:
   ```bash
   sudo ~/SlimThicc/rpi_optimize_system.sh
   ```

2. Reduce concurrent downloads in the settings:
   Edit `~/SlimThicc/config/settings.json` and set `max_concurrent_downloads` to 1 or 2.

3. Check your memory and CPU usage during downloads:
   ```bash
   # Open a terminal and monitor
   watch -n 2 'free -h; echo ""; top -b -n 1 | head -n 20'
   ```

### Application Freezes

If the application becomes unresponsive:

1. Check if the system is running out of memory:
   ```bash
   free -h
   ```

2. Increase swap space if needed:
   ```bash
   sudo dphys-swapfile swapoff
   sudo nano /etc/dphys-swapfile
   # Change CONF_SWAPSIZE to 1024
   sudo dphys-swapfile setup
   sudo dphys-swapfile swapon
   ```

3. Monitor CPU temperature during usage:
   ```bash
   watch -n 2 vcgencmd measure_temp
   ```

4. If overheating, improve cooling or reduce CPU frequency:
   ```bash
   # To set conservative governor
   echo "conservative" | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
   ```

## Audio Conversion Problems

### FFmpeg Issues

If audio conversion fails:

1. Make sure ffmpeg is installed and working:
   ```bash
   ffmpeg -version
   ```

2. Try reinstalling ffmpeg:
   ```bash
   sudo apt remove --purge ffmpeg
   sudo apt update
   sudo apt install -y ffmpeg
   ```

3. Test a simple conversion:
   ```bash
   # Download a test file
   wget -O test.mp4 "https://filesamples.com/samples/video/mp4/sample_960x540.mp4"
   # Convert to mp3
   ffmpeg -i test.mp4 -vn -ar 44100 -ac 2 -b:a 192k test.mp3
   ```

### Format Conversion Problems

If specific formats fail to convert:

1. Check codec support in your ffmpeg build:
   ```bash
   ffmpeg -codecs | grep mp3
   ```

2. Install additional codec support if needed:
   ```bash
   sudo apt install -y libavcodec-extra
   ```

## System Requirements

Slim Thicc YouTube Downloader is optimized for Raspberry Pi 5 but will work on:

- Raspberry Pi 4 (2GB+ RAM) with Raspberry Pi OS Bookworm (64-bit recommended)
- Raspberry Pi 5 with Raspberry Pi OS Bookworm (64-bit recommended)

Minimum requirements:
- 2GB RAM (4GB+ recommended)
- Raspberry Pi OS Bookworm or newer
- At least 1GB free disk space
- Active internet connection

## Logs and Diagnostics

### Finding Logs

Log files are stored in:
```
~/SlimThicc/logs/
```

### Generating Diagnostic Report

If you're experiencing issues, generate a diagnostic report to share:

```bash
cat > ~/generate_diagnostic.sh << 'EOF'
#!/bin/bash
# Generate diagnostic report for troubleshooting

REPORT_FILE="~/slimthicc_diagnostic_$(date +%Y%m%d%H%M%S).txt"

echo "Slim Thicc YouTube Downloader - Diagnostic Report" > $REPORT_FILE
echo "Generated: $(date)" >> $REPORT_FILE
echo "Hostname: $(hostname)" >> $REPORT_FILE
echo "" >> $REPORT_FILE

echo "==== System Information ====" >> $REPORT_FILE
echo "Raspberry Pi Model:" >> $REPORT_FILE
cat /proc/device-tree/model >> $REPORT_FILE
echo "" >> $REPORT_FILE

echo "OS Version:" >> $REPORT_FILE
cat /etc/os-release | grep "PRETTY_NAME" >> $REPORT_FILE
echo "" >> $REPORT_FILE

echo "Kernel:" >> $REPORT_FILE
uname -a >> $REPORT_FILE
echo "" >> $REPORT_FILE

echo "Memory:" >> $REPORT_FILE
free -h >> $REPORT_FILE
echo "" >> $REPORT_FILE

echo "Disk Space:" >> $REPORT_FILE
df -h >> $REPORT_FILE
echo "" >> $REPORT_FILE

echo "CPU Info:" >> $REPORT_FILE
lscpu >> $REPORT_FILE
echo "" >> $REPORT_FILE

echo "Temperature:" >> $REPORT_FILE
vcgencmd measure_temp >> $REPORT_FILE
echo "" >> $REPORT_FILE

echo "==== Package Information ====" >> $REPORT_FILE
echo "FFmpeg:" >> $REPORT_FILE
ffmpeg -version | head -n 1 >> $REPORT_FILE
echo "" >> $REPORT_FILE

echo "Qt Packages:" >> $REPORT_FILE
dpkg -l | grep -E 'qt5|qt6' | grep -v "not installed" >> $REPORT_FILE
echo "" >> $REPORT_FILE

echo "Python:" >> $REPORT_FILE
python3 --version >> $REPORT_FILE
echo "" >> $REPORT_FILE

echo "==== Application Files ====" >> $REPORT_FILE
echo "Files in SlimThicc directory:" >> $REPORT_FILE
ls -la ~/SlimThicc >> $REPORT_FILE
echo "" >> $REPORT_FILE

echo "Permissions of executables:" >> $REPORT_FILE
ls -la ~/SlimThicc/slim_thicc_yt >> $REPORT_FILE
ls -la ~/SlimThicc/run.sh >> $REPORT_FILE
echo "" >> $REPORT_FILE

echo "==== Recent Logs ====" >> $REPORT_FILE
echo "Latest log file:" >> $REPORT_FILE
LATEST_LOG=$(ls -t ~/SlimThicc/logs/app_*.log | head -n 1)
echo $LATEST_LOG >> $REPORT_FILE
echo "Log contents:" >> $REPORT_FILE
tail -n 100 $LATEST_LOG >> $REPORT_FILE
echo "" >> $REPORT_FILE

echo "==== Network Information ====" >> $REPORT_FILE
echo "IP Address:" >> $REPORT_FILE
hostname -I >> $REPORT_FILE
echo "" >> $REPORT_FILE

echo "Internet Connectivity:" >> $REPORT_FILE
ping -c 3 youtube.com >> $REPORT_FILE 2>&1
echo "" >> $REPORT_FILE

echo "==== Configuration ====" >> $REPORT_FILE
echo "Settings file:" >> $REPORT_FILE
if [ -f ~/SlimThicc/config/settings.json ]; then
  cat ~/SlimThicc/config/settings.json >> $REPORT_FILE
else
  echo "Settings file not found" >> $REPORT_FILE
fi
echo "" >> $REPORT_FILE

echo "Diagnostic report generated at $REPORT_FILE"
EOF

chmod +x ~/generate_diagnostic.sh
~/generate_diagnostic.sh
```

## Updating the Application

To update to a newer version:

1. Backup your settings and download history:
   ```bash
   cp -r ~/SlimThicc/config ~/slimthicc_config_backup
   ```

2. Download and extract the new version.

3. Restore your settings:
   ```bash
   cp -r ~/slimthicc_config_backup/* ~/SlimThicc/config/
   ```

## Additional Resources

If you continue to experience issues:
- Check the GitHub repository for updates: https://github.com/LoganZechella/slimthicc_yt
- Submit an issue with your diagnostic report attached
- Check the Raspberry Pi forums for Qt and Python application troubleshooting 