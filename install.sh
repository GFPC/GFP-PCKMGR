#!/bin/bash

# Exit on error
set -e

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root"
    exit 1
fi

# Create installation directory
INSTALL_DIR="/opt/gfp-pckmgr"
mkdir -p $INSTALL_DIR

# Install Python dependencies
pip3 install -r requirements.txt

# Copy files to installation directory
cp gfp_pckmgr.py $INSTALL_DIR/
cp .env $INSTALL_DIR/
cp requirements.txt $INSTALL_DIR/

# Copy service file
cp gfp-pckmgr.service /etc/systemd/system/

# Set permissions
chmod 755 $INSTALL_DIR/gfp_pckmgr.py
chmod 644 /etc/systemd/system/gfp-pckmgr.service

# Reload systemd
systemctl daemon-reload

# Enable and start service
systemctl enable gfp-pckmgr
systemctl start gfp-pckmgr

echo "Installation completed successfully!"
echo "The bot is now running as a systemd service."
echo "You can check its status with: systemctl status gfp-pckmgr" 