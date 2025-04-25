#!/usr/bin/env python3
import os
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
import logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Get configuration from environment variables
BOT_TOKEN = os.getenv('BOT_TOKEN')
ALLOWED_USERS = [int(user_id) for user_id in os.getenv('ALLOWED_USERS', '').split(',') if user_id]
CHECK_INTERVAL = 300  # Check every 5 minutes

def set_file_permissions():
    """Set correct permissions for all files."""
    try:
        # Set permissions for all Python files
        for file in ['gfp_pckmgr.py', 'check_updates.py']:
            file_path = os.path.join('/opt/gfp-pckmgr', file)
            if os.path.exists(file_path):
                os.chmod(file_path, 0o755)
                logger.info(f"Set permissions for {file} to 755")
        
        # Set permissions for service files
        for file in ['gfp-pckmgr.service', 'gfp-pckmgr-updater.service']:
            file_path = os.path.join('/etc/systemd/system', file)
            if os.path.exists(file_path):
                os.chmod(file_path, 0o644)
                logger.info(f"Set permissions for {file} to 644")
        
        # Set permissions for .env file
        env_path = os.path.join('/opt/gfp-pckmgr', '.env')
        if os.path.exists(env_path):
            os.chmod(env_path, 0o600)
            logger.info("Set permissions for .env to 600")
            
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
            # Get repository URL from current directory
            try:
                current_repo = git.Repo('.')
                origin_url = current_repo.remotes.origin.url
                repo.create_remote('origin', origin_url)
                logger.info(f"Added remote origin: {origin_url}")
            except Exception as e:
                logger.error(f"Failed to get origin URL from current repo: {str(e)}")
                # Try to get URL from git config
                try:
                    result = subprocess.run(
                        ['git', 'config', '--get', 'remote.origin.url'],
                        capture_output=True,
                        text=True,
                        cwd='/opt/gfp-pckmgr'
                    )
                    if result.returncode == 0:
                        origin_url = result.stdout.strip()
                        repo.create_remote('origin', origin_url)
                        logger.info(f"Added remote origin from git config: {origin_url}")
                    else:
                        raise Exception("Could not get origin URL from git config")
                except Exception as e:
                    logger.error(f"Failed to get origin URL from git config: {str(e)}")
                    raise
        
        # Configure git
        with repo.config_writer() as git_config:
            git_config.set_value('user', 'name', 'GFP Package Manager')
            git_config.set_value('user', 'email', 'bot@gfp-pckmgr')
        
        # Verify remote configuration
        try:
            repo.remotes.origin.fetch()
            logger.info("Successfully verified remote configuration")
        except Exception as e:
            logger.error(f"Failed to verify remote configuration: {str(e)}")
            raise
        
        logger.info("Git repository configured successfully")
        return repo
        
    except Exception as e:
        logger.error(f"Error setting up git repository: {str(e)}")
        raise

async def check_and_notify():
    """Check for updates and notify users if available."""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not found in environment variables")
        return
    
    if not ALLOWED_USERS:
        logger.error("No ALLOWED_USERS specified in environment variables")
        return
    
    try:
        bot = Bot(token=BOT_TOKEN)
        logger.info("Bot initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize bot: {str(e)}")
        return
    
    try:
        repo = setup_git_repo()
        logger.info("Git repository setup completed")
    except Exception as e:
        logger.error(f"Failed to setup git repository: {str(e)}")
        return
    
    last_commit = None
    
    while True:
        try:
            # Fetch latest changes
            try:
                logger.info("Fetching from remote...")
                repo.remotes.origin.fetch()
                logger.info("Fetch completed successfully")
            except git.exc.GitCommandError as e:
                logger.error(f"Failed to fetch from remote: {str(e)}")
                # Try to fix remote configuration
                try:
                    logger.info("Attempting to fix remote configuration...")
                    # Get URL from git config
                    result = subprocess.run(
                        ['git', 'config', '--get', 'remote.origin.url'],
                        capture_output=True,
                        text=True,
                        cwd='/opt/gfp-pckmgr'
                    )
                    if result.returncode == 0:
                        origin_url = result.stdout.strip()
                        if repo.remotes:
                            repo.delete_remote('origin')
                        repo.create_remote('origin', origin_url)
                        logger.info(f"Recreated remote origin: {origin_url}")
                        continue
                    else:
                        raise Exception("Could not get origin URL from git config")
                except Exception as e:
                    logger.error(f"Failed to fix remote configuration: {str(e)}")
                    continue
            
            # Get current commit
            current_commit = repo.head.commit.hexsha
            logger.debug(f"Current commit: {current_commit[:7]}")
            
            # If this is the first run, just store the commit
            if last_commit is None:
                last_commit = current_commit
                logger.info(f"Initial commit set to: {last_commit[:7]}")
                continue
            
            # Check if there are new commits
            if current_commit != last_commit:
                logger.info(f"New commit detected: {current_commit[:7]}")
                # Get commit information
                new_commit = repo.head.commit
                commit_message = new_commit.message.split('\n')[0]
                commit_author = new_commit.author.name
                commit_date = new_commit.committed_datetime.strftime("%Y-%m-%d %H:%M:%S")
                
                # Create keyboard with update buttons
                keyboard = [
                    [InlineKeyboardButton("🔄 Update Now", callback_data="update_confirm")],
                    [InlineKeyboardButton("❌ Cancel Update", callback_data="update_cancel")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Send update notification to all allowed users
                message = (
                    "🔄 *New Update Available!*\n\n"
                    f"*Commit:* {commit_message}\n"
                    f"*Author:* {commit_author}\n"
                    f"*Date:* {commit_date}\n\n"
                    "Would you like to update now?"
                )
                
                for user_id in ALLOWED_USERS:
                    try:
                        await bot.send_message(
                            chat_id=user_id,
                            text=message,
                            reply_markup=reply_markup,
                            parse_mode='Markdown'
                        )
                        logger.info(f"Update notification sent to user {user_id}")
                    except Exception as e:
                        logger.error(f"Error sending update notification to user {user_id}: {str(e)}")
                
                # Update last commit
                last_commit = current_commit
                logger.info(f"Last commit updated to: {last_commit[:7]}")
            
        except Exception as e:
            logger.error(f"Error in update check loop: {str(e)}")
        
        # Wait before next check
        await asyncio.sleep(CHECK_INTERVAL)

async def handle_update_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle update confirmation button presses."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "update_cancel":
        await query.edit_message_text("Update cancelled.")
        return
    
    if query.data == "update_confirm":
        try:
            # Get repository
            repo = git.Repo('/opt/gfp-pckmgr')
            
            # Check for local changes
            if repo.is_dirty():
                logger.warning("Local changes detected, attempting to stash...")
                try:
                    repo.git.stash()
                    logger.info("Local changes stashed successfully")
                except Exception as e:
                    logger.error(f"Failed to stash local changes: {str(e)}")
                    await query.edit_message_text(
                        "❌ Failed to update: Local changes detected and could not be stashed.\n"
                        "Please resolve local changes manually."
                    )
                    return
            
            # Pull latest changes
            try:
                repo.remotes.origin.pull()
                logger.info("Successfully pulled latest changes")
            except git.exc.GitCommandError as e:
                logger.error(f"Failed to pull changes: {str(e)}")
                await query.edit_message_text(
                    "❌ Failed to update: Could not pull changes.\n"
                    "Please check the repository status manually."
                )
                return
            
            # Set correct permissions
            set_file_permissions()
            
            # Install new dependencies if requirements.txt changed
            if 'requirements.txt' in [item.a_path for item in repo.index.diff('HEAD~1')]:
                subprocess.run(['pip3', 'install', '-r', 'requirements.txt'], check=True)
            
            # Reload systemd to pick up any service file changes
            subprocess.run(['systemctl', 'daemon-reload'], check=True)
            
            # Restart the service
            subprocess.run(['systemctl', 'restart', 'gfp-pckmgr'], check=True)
            
            await query.edit_message_text(
                "✅ Update completed successfully!\n"
                "The bot will restart momentarily."
            )
            
        except Exception as e:
            logger.error(f"Error during update: {str(e)}")
            await query.edit_message_text(f"❌ Error during update: {str(e)}")

if __name__ == '__main__':
    try:
        # Set initial permissions
        set_file_permissions()
        asyncio.run(check_and_notify())
    except KeyboardInterrupt:
        logger.info("Update checker stopped by user")
    except Exception as e:
        logger.error(f"Fatal error in update checker: {str(e)}")
        raise 