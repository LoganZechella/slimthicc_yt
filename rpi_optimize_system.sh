#!/bin/bash
# System optimization script for Slim Thicc YouTube Downloader on Raspberry Pi

# Must be run with sudo
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (use sudo)"
  exit 1
fi

echo "======================================================"
echo "Slim Thicc YouTube Downloader - Raspberry Pi Optimizer"
echo "======================================================"
echo "This script will optimize your Raspberry Pi system for better performance with the Slim Thicc YouTube Downloader."
echo ""
echo "WARNING: This script modifies system settings. It is recommended to create a backup before proceeding."
echo ""
read -p "Do you want to continue? (y/n): " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "Operation cancelled."
  exit 1
fi

# Create a backup directory for configuration files
BACKUP_DIR="/home/pi/slimthicc_config_backup_$(date +%Y%m%d%H%M%S)"
mkdir -p "$BACKUP_DIR"
echo "Creating backup directory at $BACKUP_DIR"

# Increase file descriptors limit
echo "Optimizing file descriptors limit..."
if [ -f /etc/sysctl.conf ]; then
  cp /etc/sysctl.conf "$BACKUP_DIR/"
  if ! grep -q "fs.file-max" /etc/sysctl.conf; then
    echo "fs.file-max = 65535" >> /etc/sysctl.conf
  fi
fi

# Optimize network settings
echo "Optimizing network settings..."
cat << 'NETWORK' >> /etc/sysctl.conf
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
net.ipv4.tcp_rmem = 4096 87380 16777216
net.ipv4.tcp_wmem = 4096 65536 16777216
net.ipv4.tcp_window_scaling = 1
net.ipv4.tcp_moderate_rcvbuf = 1
NETWORK

# Apply sysctl changes
sysctl -p

# Optimize CPU governor if available
echo "Optimizing CPU governor..."
if [ -f /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor ]; then
  # Save current governor settings
  for cpu in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
    echo "$(cat $cpu) - $cpu" >> "$BACKUP_DIR/cpu_governors.txt"
  done
  
  # Set performance governor
  echo "Setting CPU governor to performance..."
  for cpu in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
    echo "performance" > $cpu
  done
else
  echo "CPU governor control not available on this system."
fi

# Optimize memory
echo "Optimizing memory settings..."
# Disable swap if memory is sufficient
total_mem=$(free -m | awk '/^Mem:/{print $2}')
if [ "$total_mem" -ge 4000 ]; then
  echo "Disabling swap for better performance (you have $total_mem MB RAM)..."
  swapoff -a
  # Backup fstab
  cp /etc/fstab "$BACKUP_DIR/"
  # Comment out swap in fstab
  sed -i '/swap/s/^/#/' /etc/fstab
else
  echo "System has less than 4GB RAM ($total_mem MB). Keeping swap enabled."
  # Optimize swap settings
  echo "Optimizing swap settings..."
  if [ -f /etc/sysctl.conf ]; then
    echo "vm.swappiness = 10" >> /etc/sysctl.conf
    echo "vm.vfs_cache_pressure = 50" >> /etc/sysctl.conf
    sysctl -p
  fi
fi

# Set up a dedicated downloads directory on external storage if available
echo "Checking for external storage..."
external_storage=""
if [ -d "/mnt/usbdrive" ]; then
  external_storage="/mnt/usbdrive"
elif [ -d "/media/pi" ] && [ "$(ls -A /media/pi 2>/dev/null)" ]; then
  # Use the first mounted media directory
  external_storage=$(find /media/pi -maxdepth 1 -type d | head -1)
fi

if [ -n "$external_storage" ]; then
  echo "External storage found at $external_storage"
  echo "Setting up dedicated downloads directory..."
  mkdir -p "$external_storage/SlimThicc_Downloads"
  chown pi:pi "$external_storage/SlimThicc_Downloads"
  
  # Create a symlink in the user's home directory
  if [ -L "/home/pi/Downloads/SlimThicc" ]; then
    rm "/home/pi/Downloads/SlimThicc"
  fi
  mkdir -p "/home/pi/Downloads"
  ln -sf "$external_storage/SlimThicc_Downloads" "/home/pi/Downloads/SlimThicc"
  chown -h pi:pi "/home/pi/Downloads/SlimThicc"
  
  echo "Downloads directory set up at $external_storage/SlimThicc_Downloads"
  echo "(Linked from /home/pi/Downloads/SlimThicc)"
else
  echo "No external storage found. Using internal storage."
  mkdir -p "/home/pi/Downloads/SlimThicc"
  chown pi:pi "/home/pi/Downloads/SlimThicc"
fi

# Create a restore script
cat > "$BACKUP_DIR/restore.sh" << 'EOF'
#!/bin/bash
# Restore script for Slim Thicc YouTube Downloader optimizations

# Must be run with sudo
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (use sudo)"
  exit 1
fi

BACKUP_DIR="$(dirname "$0")"

# Restore sysctl.conf if it exists in backup
if [ -f "$BACKUP_DIR/sysctl.conf" ]; then
  cp "$BACKUP_DIR/sysctl.conf" /etc/sysctl.conf
  sysctl -p
  echo "Restored /etc/sysctl.conf"
fi

# Restore fstab if it exists in backup
if [ -f "$BACKUP_DIR/fstab" ]; then
  cp "$BACKUP_DIR/fstab" /etc/fstab
  echo "Restored /etc/fstab"
fi

# Restore CPU governors if backup exists
if [ -f "$BACKUP_DIR/cpu_governors.txt" ]; then
  while read -r line; do
    governor=$(echo "$line" | awk '{print $1}')
    file=$(echo "$line" | awk '{print $3}')
    if [ -f "$file" ]; then
      echo "$governor" > "$file"
      echo "Restored $file to $governor"
    fi
  done < "$BACKUP_DIR/cpu_governors.txt"
fi

echo "System settings restored from $BACKUP_DIR"
EOF

chmod +x "$BACKUP_DIR/restore.sh"

echo ""
echo "======================================================"
echo "Optimization completed!"
echo "A backup of your previous configuration has been saved to:"
echo "$BACKUP_DIR"
echo ""
echo "To restore your previous settings, run:"
echo "sudo $BACKUP_DIR/restore.sh"
echo ""
echo "Please reboot your Raspberry Pi for all changes to take effect:"
echo "sudo reboot"
echo "======================================================" 