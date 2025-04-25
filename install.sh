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
pip3 install gitpython

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
cp check_updates.py $INSTALL_DIR/
cp .env $INSTALL_DIR/
cp requirements.txt $INSTALL_DIR/

# Initialize git repository if it doesn't exist
if [ ! -d "$INSTALL_DIR/.git" ]; then
    echo "Initializing git repository..."
    cd $INSTALL_DIR
    git init
    git add .
    git commit -m "Initial commit"
    cd -
fi

# Copy service files
cp gfp-pckmgr.service /etc/systemd/system/
cp gfp-pckmgr-updater.service /etc/systemd/system/

# Set correct permissions
echo "Setting file permissions..."
# Python scripts
chmod 755 $INSTALL_DIR/gfp_pckmgr.py
chmod 755 $INSTALL_DIR/check_updates.py
# Service files
chmod 644 /etc/systemd/system/gfp-pckmgr.service
chmod 644 /etc/systemd/system/gfp-pckmgr-updater.service
# Configuration files
chmod 600 $INSTALL_DIR/.env
# Git repository
chmod -R 755 $INSTALL_DIR/.git
find $INSTALL_DIR/.git -type f -exec chmod 644 {} \;

# Reload systemd
systemctl daemon-reload

# Stop services if they're running
if systemctl is-active --quiet gfp-pckmgr; then
    echo "Stopping existing bot service..."
    systemctl stop gfp-pckmgr
fi

if systemctl is-active --quiet gfp-pckmgr-updater; then
    echo "Stopping existing updater service..."
    systemctl stop gfp-pckmgr-updater
fi

# Enable and start services
systemctl enable gfp-pckmgr
systemctl enable gfp-pckmgr-updater
systemctl start gfp-pckmgr
systemctl start gfp-pckmgr-updater

# Check service status
echo "Checking services status..."
sleep 2  # Give the services some time to start

echo "Bot service status:"
systemctl status gfp-pckmgr

echo "Updater service status:"
systemctl status gfp-pckmgr-updater

# Show logs if services failed
if ! systemctl is-active --quiet gfp-pckmgr; then
    echo "Bot service failed to start. Showing logs:"
    journalctl -u gfp-pckmgr -n 50 --no-pager
    echo "Please check the logs above for errors"
    exit 1
fi

if ! systemctl is-active --quiet gfp-pckmgr-updater; then
    echo "Updater service failed to start. Showing logs:"
    journalctl -u gfp-pckmgr-updater -n 50 --no-pager
    echo "Please check the logs above for errors"
    exit 1
fi

echo "Installation completed successfully!"
echo "The bot and updater are now running as systemd services."
echo "You can check their status with:"
echo "  systemctl status gfp-pckmgr"
echo "  systemctl status gfp-pckmgr-updater"
echo "You can view logs with:"
echo "  journalctl -u gfp-pckmgr -f"
echo "  journalctl -u gfp-pckmgr-updater -f" 