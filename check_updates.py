#!/usr/bin/env python3
import os
import time
import git
import asyncio
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv

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

async def check_and_notify():
    """Check for updates and notify users if available."""
    bot = Bot(token=BOT_TOKEN)
    repo = git.Repo('/opt/gfp-pckmgr')
    last_commit = None
    
    while True:
        try:
            # Fetch latest changes
            repo.remotes.origin.fetch()
            
            # Get current commit
            current_commit = repo.head.commit.hexsha
            
            # If this is the first run, just store the commit
            if last_commit is None:
                last_commit = current_commit
                continue
            
            # Check if there are new commits
            if current_commit != last_commit:
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
                    except Exception as e:
                        logger.error(f"Error sending update notification to user {user_id}: {str(e)}")
                
                # Update last commit
                last_commit = current_commit
            
        except Exception as e:
            logger.error(f"Error checking for updates: {str(e)}")
        
        # Wait before next check
        await asyncio.sleep(CHECK_INTERVAL)

if __name__ == '__main__':
    asyncio.run(check_and_notify()) 