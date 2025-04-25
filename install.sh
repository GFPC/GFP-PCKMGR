#!/bin/bash

# Exit on error
set -e

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root"
    exit 1
fi

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Check if we're already in the target directory
if [ "$SCRIPT_DIR" = "/opt/gfp-pckmgr" ]; then
    echo "Already in target directory, skipping file copy"
else
    # Create directory if it doesn't exist
    mkdir -p /opt/gfp-pckmgr

    # Copy files
    cp -f "$SCRIPT_DIR/gfp_pckmgr.py" /opt/gfp-pckmgr/
    cp -f "$SCRIPT_DIR/check_updates.py" /opt/gfp-pckmgr/
    cp -f "$SCRIPT_DIR/requirements.txt" /opt/gfp-pckmgr/
    cp -f "$SCRIPT_DIR/gfp-pckmgr.service" /etc/systemd/system/
    cp -f "$SCRIPT_DIR/gfp-pckmgr-updater.service" /etc/systemd/system/
fi

# Check if .env exists, if not create it from template
if [ ! -f /opt/gfp-pckmgr/.env ]; then
    if [ -f "$SCRIPT_DIR/env.example" ]; then
        cp "$SCRIPT_DIR/env.example" /opt/gfp-pckmgr/.env
        echo "Created .env from template. Please edit /opt/gfp-pckmgr/.env to add your bot token and allowed users."
        echo "After editing, run this script again."
        exit 0
    else
        echo "Error: .env file does not exist and env.example template not found."
        exit 1
    fi
fi

# Set permissions
chmod 755 /opt/gfp-pckmgr/gfp_pckmgr.py
chmod 755 /opt/gfp-pckmgr/check_updates.py
chmod 644 /etc/systemd/system/gfp-pckmgr.service
chmod 644 /etc/systemd/system/gfp-pckmgr-updater.service
chmod 600 /opt/gfp-pckmgr/.env

# Install dependencies
pip3 install -r /opt/gfp-pckmgr/requirements.txt
pip3 install gitpython

# Initialize git repository if it doesn't exist
if [ ! -d "/opt/gfp-pckmgr/.git" ]; then
    echo "Initializing git repository..."
    cd /opt/gfp-pckmgr
    git init
    git add .
    git commit -m "Initial commit"
    cd -
fi

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