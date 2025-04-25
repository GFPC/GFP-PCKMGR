#!/usr/bin/env python3
import os
import logging
import subprocess
import tempfile
import time
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
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

# Dictionary to store command mode status for each user
command_mode_users = set()

HELP_MESSAGE = """
🤖 *GFP Package Manager Bot Help*

*Basic Commands:*
/start - Start the bot and show welcome message
/help - Show this help message
/exec <command> - Execute a single command
/load_journal <service_name> <lines_num> - Get service logs

*Command Mode:*
/cmd_mode - Enter command mode
/exit - Exit command mode
In command mode, you can send commands directly without /exec prefix.
Type 'exit' or use /exit to leave command mode.

*Examples:*
• Single command:
  `/exec ls -la`
  
• Command mode:
  ```
  /cmd_mode
  ls -la
  pwd
  /exit
  ```

• View service logs:
  `/load_journal nginx 100`

*Security Notes:*
• Only authorized users can use the bot
• Commands are executed with a 30-second timeout
• The bot runs with root privileges, be careful with commands
• Long outputs will be split into multiple messages

*Need more help?*
Contact the bot administrator for assistance.
"""

UNKNOWN_COMMAND_MESSAGE = """
❌ Unknown command. Please use one of the following commands:

/start - Start the bot
/help - Show help message
/exec <command> - Execute a command
/cmd_mode - Enter command mode
/exit - Exit command mode
/load_journal <service_name> <lines_num> - Get service logs
"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    if update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("You are not authorized to use this bot.")
        return
    
    await update.message.reply_text(
        "Hello! I'm GFP Package Manager bot.\n\n"
        "Available commands:\n"
        "/start - Show this message\n"
        "/help - Show detailed help\n"
        "/exec <command> - Execute a single command\n"
        "/cmd_mode - Enter command mode (use /exit to leave)\n"
        "/exit - Exit command mode\n"
        "/load_journal <service_name> <lines_num> - Get service logs"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    if update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("You are not authorized to use this bot.")
        return
    
    await update.message.reply_text(HELP_MESSAGE, parse_mode='Markdown')

async def load_journal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get service logs using journalctl."""
    if update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("You are not authorized to use this bot.")
        return
    
    if len(context.args) != 2:
        await update.message.reply_text(
            "Please provide service name and number of lines.\n"
            "Example: /load_journal nginx 100"
        )
        return
    
    service_name = context.args[0]
    try:
        lines_num = int(context.args[1])
        if lines_num <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Number of lines must be a positive integer.")
        return
    
    try:
        # Create a temporary file
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.log', delete=False) as temp_file:
            # Run journalctl command and write output to temp file
            result = subprocess.run(
                f"journalctl -eu {service_name} -n {lines_num}",
                shell=True,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                await update.message.reply_text(
                    f"❌ Error getting logs for {service_name}:\n{result.stderr}"
                )
                return
            
            # Write logs to temp file
            temp_file.write(result.stdout)
            temp_file.flush()
            
            # Send the file
            with open(temp_file.name, 'rb') as file:
                await update.message.reply_document(
                    document=file,
                    filename=f"{service_name}_logs.log",
                    caption=f"Logs for {service_name} (last {lines_num} lines)"
                )
            
            # Clean up
            os.unlink(temp_file.name)
            
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def execute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Execute a command on the system."""
    if update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("You are not authorized to use this bot.")
        return
    
    if not context.args:
        await update.message.reply_text("Please provide a command to execute.")
        return
    
    command = ' '.join(context.args)
    await _execute_and_reply(update, command)

async def cmd_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enter command mode."""
    if update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("You are not authorized to use this bot.")
        return
    
    user_id = update.effective_user.id
    command_mode_users.add(user_id)
    await update.message.reply_text(
        "Entered command mode. Send commands directly without /exec.\n"
        "Type 'exit' or use /exit to leave command mode."
    )

async def exit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exit command mode."""
    if update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("You are not authorized to use this bot.")
        return
    
    user_id = update.effective_user.id
    if user_id in command_mode_users:
        command_mode_users.remove(user_id)
        await update.message.reply_text("Exited command mode.")
    else:
        await update.message.reply_text("You are not in command mode.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle messages in command mode."""
    if update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("You are not authorized to use this bot.")
        return
    
    user_id = update.effective_user.id
    if user_id in command_mode_users:
        command = update.message.text
        if command.lower() == 'exit':
            command_mode_users.remove(user_id)
            await update.message.reply_text("Exited command mode.")
            return
        
        await _execute_and_reply(update, command)
    else:
        # If not in command mode and message is not a command, show unknown command message
        if not update.message.text.startswith('/'):
            await update.message.reply_text(UNKNOWN_COMMAND_MESSAGE)

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle unknown commands."""
    if update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("You are not authorized to use this bot.")
        return
    
    await update.message.reply_text(UNKNOWN_COMMAND_MESSAGE)

async def _execute_and_reply(update: Update, command: str):
    """Execute a command and send the response."""
    start_time = time.time()
    try:
        # Get current directory
        pwd_result = subprocess.run(
            "pwd",
            shell=True,
            capture_output=True,
            text=True
        )
        current_dir = pwd_result.stdout.strip()

        # Execute the command
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        # Calculate execution time
        execution_time = time.time() - start_time
        
        if result.returncode == 0:
            response = (
                f"✅ Command executed successfully in {execution_time:.2f} seconds\n"
                f"📁 Current directory: {current_dir}\n\n"
                f"{result.stdout}"
            )
        else:
            response = (
                f"❌ Command failed with error in {execution_time:.2f} seconds\n"
                f"📁 Current directory: {current_dir}\n\n"
                f"{result.stderr}"
            )
        
        # Split response if it's too long
        if len(response) > 4000:
            for i in range(0, len(response), 4000):
                await update.message.reply_text(response[i:i+4000])
        else:
            await update.message.reply_text(response)
            
    except subprocess.TimeoutExpired:
        execution_time = time.time() - start_time
        await update.message.reply_text(f"❌ Command execution timed out after {execution_time:.2f} seconds.")
    except Exception as e:
        execution_time = time.time() - start_time
        await update.message.reply_text(f"❌ Error executing command in {execution_time:.2f} seconds: {str(e)}")

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
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("exec", execute_command))
    application.add_handler(CommandHandler("cmd_mode", cmd_mode))
    application.add_handler(CommandHandler("exit", exit_command))
    application.add_handler(CommandHandler("load_journal", load_journal))
    
    # Add message handler for command mode
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Add handler for unknown commands
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    # Start the Bot
    application.run_polling()

if __name__ == '__main__':
    main() 