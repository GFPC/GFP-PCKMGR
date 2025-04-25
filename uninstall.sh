#!/bin/bash

# Exit on error
set -e

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root"
    exit 1
fi

# Stop and disable service
systemctl stop gfp-pckmgr
systemctl disable gfp-pckmgr

# Remove service file
rm -f /etc/systemd/system/gfp-pckmgr.service

# Remove installation directory
rm -rf /opt/gfp-pckmgr

# Reload systemd
systemctl daemon-reload

echo "Uninstallation completed successfully!" 