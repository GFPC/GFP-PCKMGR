#!/usr/bin/env python3
import os
import logging
import subprocess
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Get configuration from environment variables
BOT_TOKEN = os.getenv('BOT_TOKEN')
ALLOWED_USERS = [int(user_id) for user_id in os.getenv('ALLOWED_USERS', '').split(',') if user_id]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    if update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("You are not authorized to use this bot.")
        return
    
    await update.message.reply_text(
        "Hello! I'm GFP Package Manager bot. "
        "Use /exec <command> to execute commands on the system."
    )

async def execute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Execute a command on the system."""
    if update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("You are not authorized to use this bot.")
        return
    
    if not context.args:
        await update.message.reply_text("Please provide a command to execute.")
        return
    
    command = ' '.join(context.args)
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            response = f"✅ Command executed successfully:\n\n{result.stdout}"
        else:
            response = f"❌ Command failed with error:\n\n{result.stderr}"
        
        # Split response if it's too long
        if len(response) > 4000:
            for i in range(0, len(response), 4000):
                await update.message.reply_text(response[i:i+4000])
        else:
            await update.message.reply_text(response)
            
    except subprocess.TimeoutExpired:
        await update.message.reply_text("❌ Command execution timed out after 30 seconds.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error executing command: {str(e)}")

def main():
    """Start the bot."""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not found in environment variables")
        return
    
    if not ALLOWED_USERS:
        logger.error("No ALLOWED_USERS specified in environment variables")
        return
    
    # Create the Application and pass it your bot's token
    application = Application.builder().token(BOT_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("exec", execute_command))

    # Start the Bot
    application.run_polling()

if __name__ == '__main__':
    main() 