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

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cp env.example .env
    echo "Please edit .env file and add your bot token and allowed users"
    echo "Then run the installation script again"
    exit 1
fi

# Copy files to installation directory
cp gfp_pckmgr.py $INSTALL_DIR/
cp .env $INSTALL_DIR/
cp requirements.txt $INSTALL_DIR/

# Copy service file
cp gfp-pckmgr.service /etc/systemd/system/

# Set permissions
chmod 755 $INSTALL_DIR/gfp_pckmgr.py
chmod 644 /etc/systemd/system/gfp-pckmgr.service
chmod 600 $INSTALL_DIR/.env

# Reload systemd
systemctl daemon-reload

# Stop service if it's running
if systemctl is-active --quiet gfp-pckmgr; then
    echo "Stopping existing service..."
    systemctl stop gfp-pckmgr
fi

# Enable and start service
systemctl enable gfp-pckmgr
systemctl start gfp-pckmgr

# Check service status
echo "Checking service status..."
sleep 2  # Give the service some time to start
systemctl status gfp-pckmgr

# Show logs if service failed
if ! systemctl is-active --quiet gfp-pckmgr; then
    echo "Service failed to start. Showing logs:"
    journalctl -u gfp-pckmgr -n 50 --no-pager
    echo "Please check the logs above for errors"
    exit 1
fi

echo "Installation completed successfully!"
echo "The bot is now running as a systemd service."
echo "You can check its status with: systemctl status gfp-pckmgr"
echo "You can view logs with: journalctl -u gfp-pckmgr -f" 