#!/usr/bin/env python3
import os
import logging
import subprocess
import tempfile
import time
import git
import hashlib
import shutil
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/var/log/gfp-pckmgr.log')
    ]
)
logger = logging.getLogger(__name__)

# Get configuration from environment variables
BOT_TOKEN = os.getenv('BOT_TOKEN')
ALLOWED_USERS = [int(user_id) for user_id in os.getenv('ALLOWED_USERS', '').split(',') if user_id]

if not BOT_TOKEN:
    logger.error("BOT_TOKEN not found in environment variables")
    raise ValueError("BOT_TOKEN not found in environment variables")

if not ALLOWED_USERS:
    logger.error("No ALLOWED_USERS specified in environment variables")
    raise ValueError("No ALLOWED_USERS specified in environment variables")

logger.info("Bot configuration loaded successfully")

# Dictionary to store command mode status for each user
command_mode_users = set()

HELP_MESSAGE = """
🤖 *GFP Package Manager Bot Help*

*Basic Commands:*
/start - Start the bot and show welcome message
/help - Show this help message
/exec <command> - Execute a single command
/dir - Navigate directories with buttons
/load_journal <service_name> <lines_num> - Get service logs
/update - Check for updates and restart bot
/version - Show current and available versions

*Command Mode:*
/cmd_mode - Enter command mode
/exit - Exit command mode
In command mode, you can send commands directly without /exec prefix.
Type 'exit' or use /exit to leave command mode.

*Examples:*
• Single command:
  `/exec ls -la`
  
• Directory navigation:
  `/dir` - Navigate through directories with buttons
  
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
/dir - Navigate directories
/cmd_mode - Enter command mode
/exit - Exit command mode
/load_journal <service_name> <lines_num> - Get service logs
/update - Check for updates
/version - Show version info
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
        # Get current directory from context or use root
        current_dir = update.effective_user.id in update._user_data and update._user_data[update.effective_user.id].get('current_dir', '/')
        
        # Change to the selected directory before executing command
        os.chdir(current_dir)
        
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

async def dir_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show directory contents with navigation buttons."""
    if update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("You are not authorized to use this bot.")
        return
    
    # Get current directory from context or use root
    current_dir = context.user_data.get('current_dir', '/')
    
    # Get directory contents
    ls_result = subprocess.run(
        f"ls -la {current_dir}",
        shell=True,
        capture_output=True,
        text=True
    )
    
    # Create keyboard buttons
    keyboard = []
    current_row = []
    
    # Get directories and files
    entries = os.listdir(current_dir)
    for entry in entries:
        if len(current_row) == 2:  # 2 buttons per row
            keyboard.append(current_row)
            current_row = []
        
        # Skip . and .. directories
        if entry in ['.', '..']:
            continue
            
        # Check if it's a directory
        full_path = os.path.join(current_dir, entry)
        if os.path.isdir(full_path):
            current_row.append(InlineKeyboardButton(f"📁 {entry}", callback_data=f"dir_{full_path}"))
    
    # Add remaining buttons
    if current_row:
        keyboard.append(current_row)
    
    # Add STOP SELECTING button
    keyboard.append([InlineKeyboardButton("🛑 STOP SELECTING", callback_data="stop_dir")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send message with directory contents and buttons
    await update.message.reply_text(
        f"📁 Current directory: {current_dir}\n\n"
        f"Directory contents:\n"
        f"```\n{ls_result.stdout}\n```",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def dir_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle directory navigation button presses."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "stop_dir":
        await query.edit_message_text("Directory navigation stopped.")
        return
    
    # Extract directory path from callback data
    target_dir = query.data.replace("dir_", "")
    
    # Save selected directory in user context
    context.user_data['current_dir'] = target_dir
    
    # Get directory contents
    ls_result = subprocess.run(
        f"ls -la {target_dir}",
        shell=True,
        capture_output=True,
        text=True
    )
    
    # Create keyboard buttons
    keyboard = []
    current_row = []
    
    # Get directories and files
    entries = os.listdir(target_dir)
    for entry in entries:
        if len(current_row) == 2:  # 2 buttons per row
            keyboard.append(current_row)
            current_row = []
        
        # Skip . and .. directories
        if entry in ['.', '..']:
            continue
            
        # Check if it's a directory
        full_path = os.path.join(target_dir, entry)
        if os.path.isdir(full_path):
            current_row.append(InlineKeyboardButton(f"📁 {entry}", callback_data=f"dir_{full_path}"))
    
    # Add remaining buttons
    if current_row:
        keyboard.append(current_row)
    
    # Add STOP SELECTING button
    keyboard.append([InlineKeyboardButton("🛑 STOP SELECTING", callback_data="stop_dir")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Update message with new directory contents and buttons
    await query.edit_message_text(
        f"📁 Current directory: {target_dir}\n\n"
        f"Directory contents:\n"
        f"```\n{ls_result.stdout}\n```",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def check_updates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check for updates and notify users if available."""
    try:
        # Get repository information
        repo = git.Repo('/opt/gfp-pckmgr')
        current_commit = repo.head.commit
        
        # Determine active branch
        try:
            branch = repo.active_branch.name
        except:
            branch = 'main'  # Default fallback
        
        # Fetch updates
        repo.remotes.origin.fetch()
        
        # Verify branch exists
        if f'origin/{branch}' not in repo.references:
            available_branches = []
            for ref in repo.references:
                if ref.name.startswith('origin/'):
                    available_branches.append(ref.name.split('/')[-1])
            
            if available_branches:
                branch = available_branches[0]
            else:
                raise Exception("No remote branches found")
        
        # Get remote commit
        remote_commit = repo.remotes.origin.refs[branch].commit
        
        # Check if there are new commits
        if current_commit != remote_commit.hexsha:
            # Create keyboard with update buttons
            keyboard = [
                [InlineKeyboardButton("🔄 Update Now", callback_data="update_confirm")],
                [InlineKeyboardButton("❌ Cancel Update", callback_data="update_cancel")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Get commit information
            commit_message = remote_commit.message.split('\n')[0]
            commit_author = remote_commit.author.name
            commit_date = remote_commit.committed_datetime.strftime("%Y-%m-%d %H:%M:%S")
            
            # Send update notification
            message = (
                "🔄 *New Update Available!*\n\n"
                f"*Commit:* {commit_message}\n"
                f"*Author:* {commit_author}\n"
                f"*Date:* {commit_date}\n\n"
                "Would you like to update now?"
            )
            
            # Store current commit in context
            context.bot_data['pending_update'] = {
                'old_commit': current_commit,
                'new_commit': remote_commit.hexsha,
                'branch': branch
            }
            
            await update.message.reply_text(
                message,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text("✅ Bot is up to date!")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Error checking for updates: {str(e)}")

async def send_startup_notification(context: ContextTypes.DEFAULT_TYPE):
    """Send startup notification to all allowed users."""
    try:
        # Get repository information
        repo = git.Repo('/opt/gfp-pckmgr')
        current_commit = repo.head.commit
        
        message = (
            "🤖 *Bot Started*\n\n"
            f"*Version:* {current_commit.hexsha[:7]}\n"
            f"*Branch:* {repo.active_branch.name}\n"
            f"*Last Commit:* {current_commit.message.splitlines()[0]}\n"
            f"*Author:* {current_commit.author.name}\n"
            f"*Date:* {current_commit.committed_datetime.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        # Send notification to all allowed users
        for user_id in ALLOWED_USERS:
            try:
                logger.info(f"Sending startup notification to user {user_id}")
                await context.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode='Markdown'
                )
                logger.info(f"Startup notification sent to user {user_id}")
            except Exception as e:
                logger.error(f"Failed to send startup notification to user {user_id}: {str(e)}")
                
    except Exception as e:
        logger.error(f"Error sending startup notification: {str(e)}")

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
            
            # Get update info from context
            update_info = context.bot_data['pending_update']
            branch = update_info['branch']
            
            # Backup local changes
            backup_dir = os.path.join('/opt/gfp-pckmgr', 'backup')
            os.makedirs(backup_dir, exist_ok=True)
            
            for file in ['check_updates.py', 'gfp_pckmgr.py']:
                src = os.path.join('/opt/gfp-pckmgr', file)
                if os.path.exists(src):
                    dst = os.path.join(backup_dir, f"{file}.bak.{int(time.time())}")
                    shutil.copy2(src, dst)
                    logger.info(f"Backed up {file} to {dst}")
            
            # Reset to remote branch
            logger.info(f"Resetting to origin/{branch}")
            repo.git.reset('--hard', f'origin/{branch}')
            
            # Install new dependencies if requirements.txt changed
            if 'requirements.txt' in [item.a_path for item in repo.index.diff('HEAD~1')]:
                subprocess.run(['pip3', 'install', '-r', 'requirements.txt'], check=True)
            
            # Send success message before restart
            await query.edit_message_text(
                "✅ Update completed successfully!\n"
                "The bot will restart momentarily."
            )
            
            # Stop and start services
            logger.info("Stopping services...")
            try:
                subprocess.run(['systemctl', 'stop', 'gfp-pckmgr'], check=True)
                subprocess.run(['systemctl', 'stop', 'gfp-pckmgr-updater'], check=True)
            except subprocess.CalledProcessError as e:
                if e.returncode == -15:  # SIGTERM
                    logger.info("Services stopped successfully")
                else:
                    raise
            
            logger.info("Starting services...")
            try:
                subprocess.run(['systemctl', 'start', 'gfp-pckmgr-updater'], check=True)
                subprocess.run(['systemctl', 'start', 'gfp-pckmgr'], check=True)
            except subprocess.CalledProcessError as e:
                if e.returncode == -15:  # SIGTERM
                    logger.info("Services started successfully")
                else:
                    raise
            
        except Exception as e:
            logger.error(f"Error during update: {str(e)}")
            await query.edit_message_text(f"❌ Error during update: {str(e)}")

async def version_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current and available versions with MD5 hashes."""
    if update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("You are not authorized to use this bot.")
        return
    
    try:
        # Get local repository
        repo = git.Repo('/opt/gfp-pckmgr')
        
        # Get current version info
        current_commit = repo.head.commit
        current_hash = hashlib.md5(str(current_commit).encode()).hexdigest()
        
        # Get file hashes
        file_hashes = {}
        for file in ['gfp_pckmgr.py', 'check_updates.py']:
            file_path = os.path.join('/opt/gfp-pckmgr', file)
            if os.path.exists(file_path):
                with open(file_path, 'rb') as f:
                    file_hashes[file] = hashlib.md5(f.read()).hexdigest()
        
        # Get remote repository info
        repo.remotes.origin.fetch()
        
        # Determine active branch
        try:
            branch = repo.active_branch.name
        except:
            branch = 'main'  # Default fallback
        
        # Get remote commit
        remote_commit = repo.remotes.origin.refs[branch].commit
        remote_hash = hashlib.md5(str(remote_commit).encode()).hexdigest()
        delimiter = "\n"
        
        # Format version information
        current_version = (
            "📦 *Current Version*\n\n"
            f"*Commit:* {current_commit.hexsha[:7]}\n"
            f"*Message:* {current_commit.message.split(delimiter)[0]}\n"
            f"*Author:* {current_commit.author.name}\n"
            f"*Date:* {current_commit.committed_datetime.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"*Commit Hash (MD5):* `{current_hash}`\n\n"
            "*File Hashes:*\n"
        )
        
        for file, hash_value in file_hashes.items():
            current_version += f"`{file}: {hash_value}`\n"
        
        # Check if update is available
        if current_commit.hexsha != remote_commit.hexsha:
            available_version = (
                "\n🆕 *Available Update*\n\n"
                f"*Commit:* {remote_commit.hexsha[:7]}\n"
                f"*Message:* {remote_commit.message.split(delimiter)[0]}\n"
                f"*Author:* {remote_commit.author.name}\n"
                f"*Date:* {remote_commit.committed_datetime.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"*Commit Hash (MD5):* `{remote_hash}`\n\n"
                "Use /update to install the update"
            )
        else:
            available_version = "\n✅ You are running the latest version!"
        
        # Create keyboard with update button if update is available
        keyboard = []
        if current_commit.hexsha != remote_commit.hexsha:
            keyboard.append([InlineKeyboardButton("🔄 Update Now", callback_data="update_confirm")])
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        
        # Send version information
        await update.message.reply_text(
            current_version + available_version,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error getting version information: {str(e)}")
        await update.message.reply_text(f"❌ Error getting version information: {str(e)}")

async def check_pending_updates(context: ContextTypes.DEFAULT_TYPE):
    """Check for pending updates and notify users."""
    try:
        update_file = os.path.join('/opt/gfp-pckmgr', '.update_available')
        logger.info(f"Checking for update notification file at {update_file}")
        
        if os.path.exists(update_file):
            logger.info("Update notification file found")
            try:
                with open(update_file, 'r') as f:
                    content = f.read()
                    logger.info(f"Update file content: {content}")
                    update_info = eval(content)  # Be careful with eval in production!
                
                # Create keyboard with update buttons
                keyboard = [
                    [InlineKeyboardButton("🔄 Update Now", callback_data="update_confirm")],
                    [InlineKeyboardButton("❌ Cancel Update", callback_data="update_cancel")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Send update notification
                message = (
                    "🔄 *New Update Available!*\n\n"
                    f"*Commit:* {update_info['message']}\n"
                    f"*Author:* {update_info['author']}\n"
                    f"*Date:* {update_info['date']}\n"
                    f"*Branch:* {update_info['branch']}\n"
                    f"*Old Commit:* {update_info['old_commit'][:7]}\n"
                    f"*New Commit:* {update_info['new_commit'][:7]}\n\n"
                    "Would you like to update now?"
                )
                
                # Store update info in context
                context.bot_data['pending_update'] = update_info
                
                # Send notification to all allowed users
                for user_id in ALLOWED_USERS:
                    try:
                        logger.info(f"Sending update notification to user {user_id}")
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=message,
                            reply_markup=reply_markup,
                            parse_mode='Markdown'
                        )
                        logger.info(f"Update notification sent to user {user_id}")
                    except Exception as e:
                        logger.error(f"Failed to send update notification to user {user_id}: {str(e)}")
                
                # Remove update file
                try:
                    os.remove(update_file)
                    logger.info("Update notification file removed")
                except Exception as e:
                    logger.error(f"Failed to remove update notification file: {str(e)}")
                
            except Exception as e:
                logger.error(f"Error processing update notification file: {str(e)}")
        else:
            logger.info("No update notification file found")
            
    except Exception as e:
        logger.error(f"Error checking pending updates: {str(e)}")

def main():
    """Start the bot."""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not found in environment variables")
        return
    
    if not ALLOWED_USERS:
        logger.error("No ALLOWED_USERS specified in environment variables")
        return
    
    logger.info(f"Starting bot with {len(ALLOWED_USERS)} allowed users")
    
    # Create the Application and pass it your bot's token
    application = Application.builder().token(BOT_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("exec", execute_command))
    application.add_handler(CommandHandler("cmd_mode", cmd_mode))
    application.add_handler(CommandHandler("exit", exit_command))
    application.add_handler(CommandHandler("load_journal", load_journal))
    application.add_handler(CommandHandler("dir", dir_command))
    application.add_handler(CommandHandler("update", check_updates))
    application.add_handler(CommandHandler("version", version_command))
    
    # Add callback query handlers
    application.add_handler(CallbackQueryHandler(dir_button, pattern="^dir_|stop_dir$"))
    application.add_handler(CallbackQueryHandler(handle_update_button, pattern="^update_"))
    
    # Add message handler for command mode
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Add handler for unknown commands
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    # Add job queue for checking updates
    job_queue = application.job_queue
    if job_queue:
        logger.info("JobQueue initialized, starting update checks every 30 seconds")
        job_queue.run_repeating(check_pending_updates, interval=30, first=10)
        # Schedule startup notification
        job_queue.run_once(send_startup_notification, 5)  # Send after 5 seconds
        logger.info("Update check job and startup notification scheduled successfully")
    else:
        logger.error("JobQueue not available. Update notifications will not be sent automatically.")

    # Start the Bot
    logger.info("Starting bot polling...")
    application.run_polling()

if __name__ == '__main__':
    main() 