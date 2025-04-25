#!/usr/bin/env python3
import os
import logging
import time
import git
import asyncio
import shutil
import stat
import subprocess
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from dotenv import load_dotenv
from telegram.ext import ContextTypes

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/var/log/gfp-pckmgr-updater.log')
    ]
)
logger = logging.getLogger(__name__)

# Global variables
LAST_CHECKED_COMMIT = None
CHECK_INTERVAL = 300  # 5 minutes

def set_file_permissions():
    """Set correct permissions for all files."""
    try:
        # Set permissions for Python scripts
        os.chmod('/opt/gfp-pckmgr/gfp_pckmgr.py', 0o755)
        os.chmod('/opt/gfp-pckmgr/check_updates.py', 0o755)
        
        # Set permissions for service files
        os.chmod('/etc/systemd/system/gfp-pckmgr.service', 0o644)
        os.chmod('/etc/systemd/system/gfp-pckmgr-updater.service', 0o644)
        
        # Set permissions for .env file
        os.chmod('/opt/gfp-pckmgr/.env', 0o600)
        
        logger.info("File permissions set successfully")
    except Exception as e:
        logger.error(f"Error setting file permissions: {str(e)}")

def setup_git_repo():
    """Setup git repository with proper remote configuration."""
    try:
        repo = git.Repo('/opt/gfp-pckmgr')
        logger.info("Git repository initialized")
        
        # Check if remote exists
        if not repo.remotes:
            logger.info("No remote found, adding origin...")
            repo.create_remote('origin', 'https://github.com/GFPC/GFP-PCKMGR.git')
        
        # Configure git
        with repo.config_writer() as git_config:
            git_config.set_value('user', 'name', 'GFP Package Manager')
            git_config.set_value('user', 'email', 'bot@gfp-pckmgr')
        
        # Verify remote configuration
        repo.remotes.origin.fetch()
        logger.info("Successfully verified remote configuration")
        
        return repo
        
    except Exception as e:
        logger.error(f"Error setting up git repository: {str(e)}")
        raise

def notify_users(message):
    """Send notification to all allowed users."""
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    ALLOWED_USERS = [int(user_id) for user_id in os.getenv('ALLOWED_USERS', '').split(',') if user_id]
    
    if not BOT_TOKEN or not ALLOWED_USERS:
        logger.error("Missing BOT_TOKEN or ALLOWED_USERS in environment variables")
        return
    
    for user_id in ALLOWED_USERS:
        try:
            subprocess.run([
                'curl', '-s', '-X', 'POST',
                f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
                '-d', f'chat_id={user_id}',
                '-d', f'text={message}',
                '-d', 'parse_mode=Markdown'
            ], check=True)
        except Exception as e:
            logger.error(f"Error sending message to user {user_id}: {str(e)}")

def check_updates(repo):
    """Check for updates and apply them if available."""
    global LAST_CHECKED_COMMIT
    
    try:
        # Fetch latest changes
        repo.remotes.origin.fetch()
        
        # Get current and remote commit info
        current_commit = repo.head.commit
        remote_commit = repo.remotes.origin.refs.main.commit
        
        # If this is the first run, just store the commit
        if LAST_CHECKED_COMMIT is None:
            LAST_CHECKED_COMMIT = current_commit.hexsha
            logger.info(f"Initial commit set to: {LAST_CHECKED_COMMIT[:7]}")
            return
        
        # Check if there are new commits
        if remote_commit.hexsha != LAST_CHECKED_COMMIT:
            logger.info(f"New commit detected: {remote_commit.hexsha[:7]}")
            
            # Check for local changes
            if repo.is_dirty():
                logger.info("Stashing local changes before pulling")
                repo.git.stash('save', '--keep-index', 'Auto-stash before update')
                stashed = True
            else:
                stashed = False
            
            try:
                # Pull changes
                repo.remotes.origin.pull()
                
                # Set file permissions
                set_file_permissions()
                
                # Update last checked commit
                LAST_CHECKED_COMMIT = remote_commit.hexsha
                
                # Notify users
                message = (
                    f"🔄 *Обновление завершено*\n\n"
                    f"✅ Установлена новая версия: `{remote_commit.hexsha[:7]}`\n"
                    f"📝 Сообщение: {remote_commit.message.strip()}\n"
                    f"👤 Автор: {remote_commit.author.name}\n"
                    f"📅 Дата: {remote_commit.committed_datetime.strftime('%Y-%m-%d %H:%M:%S')}"
                )
                notify_users(message)
                
                # Restart services only if files were actually updated
                if stashed:
                    logger.info("Restarting services after update")
                    subprocess.run(['systemctl', 'restart', 'gfp-pckmgr'], check=True)
                    subprocess.run(['systemctl', 'restart', 'gfp-pckmgr-updater'], check=True)
                
            except Exception as e:
                logger.error(f"Error during update: {str(e)}")
                if stashed:
                    logger.info("Restoring stashed changes")
                    repo.git.stash('pop')
        else:
            logger.debug("No updates available")
            
    except Exception as e:
        logger.error(f"Error in check_updates: {str(e)}")

def main():
    """Main function that runs continuously."""
    logger.info("Starting update checker")
    
    try:
        # Initial setup
        set_file_permissions()
        repo = setup_git_repo()
        
        # Main loop
        while True:
            try:
                check_updates(repo)
                time.sleep(CHECK_INTERVAL)
            except KeyboardInterrupt:
                logger.info("Update checker stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in main loop: {str(e)}")
                time.sleep(60)  # Wait 1 minute before retrying
                
    except Exception as e:
        logger.error(f"Fatal error in update checker: {str(e)}")
        raise

if __name__ == '__main__':
    main() 