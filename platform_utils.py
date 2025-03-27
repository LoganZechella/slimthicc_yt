import os
import platform
import subprocess
import sys

def get_base_path():
    """Get the base path of the application."""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

def is_raspberry_pi():
    """Detect if running on Raspberry Pi"""
    # Check for Raspberry Pi-specific files
    if os.path.exists('/proc/device-tree/model'):
        with open('/proc/device-tree/model') as f:
            model = f.read()
            if 'Raspberry Pi' in model:
                return True
    
    # Alternative detection method
    try:
        with open('/proc/cpuinfo', 'r') as f:
            for line in f:
                if line.startswith('Hardware') and 'BCM' in line:
                    return True
    except:
        pass
    
    return False

def get_ffmpeg_path():
    """Get appropriate FFmpeg path based on platform"""
    # For Raspberry Pi, always use the system path
    if is_raspberry_pi():
        return '/usr/bin/ffmpeg'
    
    base_path = get_base_path()
    
    # For non-Raspberry Pi ARM64
    if platform.machine() == 'arm64' or platform.machine() == 'aarch64':
        arm_path = os.path.join(base_path, 'ffmpeg_bin', 'arm64', 'ffmpeg')
        if os.path.exists(arm_path):
            return arm_path
    
    # Default for x86_64
    return os.path.join(base_path, 'ffmpeg_bin', 'x86_64', 'ffmpeg')

def get_ffprobe_path():
    """Get appropriate FFprobe path based on platform"""
    # For Raspberry Pi, always use the system path
    if is_raspberry_pi():
        return '/usr/bin/ffprobe'
    
    base_path = get_base_path()
    
    # For non-Raspberry Pi ARM64
    if platform.machine() == 'arm64' or platform.machine() == 'aarch64':
        arm_path = os.path.join(base_path, 'ffmpeg_bin', 'arm64', 'ffprobe')
        if os.path.exists(arm_path):
            return arm_path
    
    # Default for x86_64
    return os.path.join(base_path, 'ffmpeg_bin', 'x86_64', 'ffprobe')

def get_app_data_dir():
    """Get platform-specific data directory"""
    if is_raspberry_pi():
        # Use Raspberry Pi standard locations
        base_dir = os.path.expanduser('~/.local/share/slimthicc')
    elif platform.system() == 'Darwin':
        # macOS
        base_dir = os.path.expanduser('~/Library/Application Support/SlimThicc')
    elif platform.system() == 'Windows':
        # Windows
        base_dir = os.path.join(os.environ.get('APPDATA', ''), 'SlimThicc')
    else:
        # Linux and others
        base_dir = os.path.expanduser('~/.slimthicc')
    
    os.makedirs(base_dir, exist_ok=True)
    return base_dir

def configure_gui_for_platform():
    """Apply platform-specific GUI settings"""
    from PyQt5.QtWidgets import QApplication
    
    app = QApplication.instance()
    if app is None:
        return  # No application instance
        
    if is_raspberry_pi():
        # Set appropriate font size for Raspberry Pi display
        font = app.font()
        font.setPointSize(12)  # Larger font for touchscreens
        app.setFont(font)
        
        # Set style sheet for better visibility on Raspberry Pi
        app.setStyleSheet("""
            QPushButton { 
                min-height: 30px; 
                padding: 5px; 
            }
            QLineEdit { 
                min-height: 30px; 
                padding: 5px; 
            }
        """) 