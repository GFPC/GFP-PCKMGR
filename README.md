# GFP Package Manager

A Telegram bot that allows authorized users to manage packages and execute commands on a Linux system.

## Features

- Execute Linux commands remotely through Telegram
- Manage system packages
- Secure access control through user ID verification
- Automatic restart on failure
- Systemd service integration
- Easy installation and uninstallation

## Prerequisites

- Python 3.6 or higher
- pip3
- systemd
- A Telegram bot token (get it from @BotFather)
- Your Telegram user ID (get it from @userinfobot)

## Installation

1. Clone this repository:
```bash
git clone <repository-url>
cd gfp-pckmgr
```

2. Copy the environment template and configure it:
```bash
cp env.example .env
nano .env
```
Edit the `.env` file to add your bot token and allowed user IDs.

3. Make the installation script executable:
```bash
chmod +x install.sh
```

4. Run the installation script as root:
```bash
sudo ./install.sh
```

## Usage

1. Start a chat with your bot on Telegram
2. Send the `/start` command to verify your access
3. Execute commands using the `/exec` command followed by the command you want to run:
   ```
   /exec ls -la
   /exec systemctl status nginx
   ```

## Security Notes

- The bot runs as root, so be careful with the commands you execute
- Only authorized users (specified in ALLOWED_USERS) can use the bot
- Commands are executed with a 30-second timeout
- The bot automatically restarts if it crashes

## Uninstallation

To remove the bot and all its files:

```bash
sudo ./uninstall.sh
```

## Troubleshooting

Check the service status:
```bash
systemctl status gfp-pckmgr
```

View logs:
```bash
journalctl -u gfp-pckmgr -f
```

## License

MIT License 