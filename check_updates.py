#!/usr/bin/env python3
import os
import logging
import time
import git
import subprocess
from dotenv import load_dotenv

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
REPO_PATH = '/opt/gfp-pckmgr'
REMOTE_URL = 'https://github.com/GFPC/GFP-PCKMGR.git'
BRANCH = 'main'  # Или 'master' в зависимости от вашего репозитория


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
        raise


def setup_git_repo():
    """Setup git repository with proper remote configuration."""
    try:
        # Check if directory exists
        if not os.path.exists(REPO_PATH):
            os.makedirs(REPO_PATH, exist_ok=True)
            logger.info(f"Created directory {REPO_PATH}")

        # Initialize repository if it doesn't exist
        if not os.path.exists(os.path.join(REPO_PATH, '.git')):
            logger.info("Initializing new Git repository")
            repo = git.Repo.init(REPO_PATH)

            # Add remote
            if 'origin' not in repo.remotes:
                origin = repo.create_remote('origin', REMOTE_URL)
            else:
                origin = repo.remotes.origin
                origin.set_url(REMOTE_URL)

            # Fetch and checkout branch
            origin.fetch()

            # Check if branch exists in remote
            if f'origin/{BRANCH}' not in repo.references:
                raise Exception(f"Branch {BRANCH} not found in remote repository")

            # Create and checkout local branch
            repo.create_head(BRANCH, origin.refs[BRANCH])
            repo.heads[BRANCH].set_tracking_branch(origin.refs[BRANCH])
            repo.heads[BRANCH].checkout()

            logger.info(f"Checked out branch: {BRANCH}")
        else:
            repo = git.Repo(REPO_PATH)
            logger.info("Using existing Git repository")

        # Configure git user
        with repo.config_writer() as git_config:
            if not git_config.has_option('user', 'name'):
                git_config.set_value('user', 'name', 'GFP Package Manager')
            if not git_config.has_option('user', 'email'):
                git_config.set_value('user', 'email', 'bot@gfp-pckmgr')

        # Verify repository state
        if repo.bare:
            raise Exception("Repository is bare")

        if repo.is_dirty():
            logger.warning("Repository has uncommitted changes")

        logger.info(f"Repository setup complete at {REPO_PATH}")
        logger.info(f"Current branch: {repo.active_branch.name}")

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
            logger.info(f"Notification sent to user {user_id}")
        except Exception as e:
            logger.error(f"Error sending message to user {user_id}: {str(e)}")


def check_updates(repo):
    """Check for updates and apply them if available."""
    global LAST_CHECKED_COMMIT

    try:
        logger.info("Checking for updates...")

        # Fetch all changes from remote
        repo.remotes.origin.fetch()

        # Get current and remote commits
        current_commit = repo.head.commit
        remote_commit = repo.remotes.origin.refs[BRANCH].commit

        logger.info(f"Local commit: {current_commit.hexsha[:7]}")
        logger.info(f"Remote commit: {remote_commit.hexsha[:7]}")

        # First run initialization
        if LAST_CHECKED_COMMIT is None:
            LAST_CHECKED_COMMIT = current_commit.hexsha
            logger.info(f"Initial commit set to: {LAST_CHECKED_COMMIT[:7]}")
            return

        # Check if update is needed
        if remote_commit.hexsha == LAST_CHECKED_COMMIT:
            logger.info("No updates available")
            return

        logger.info(f"Update available: {remote_commit.hexsha[:7]}")

        # Stash local changes if any
        if repo.is_dirty():
            logger.info("Stashing local changes")
            repo.git.stash('save', '--keep-index', 'Auto-stash before update')
            stashed = True
        else:
            stashed = False

        try:
            # Reset to remote branch
            repo.git.reset('--hard', f'origin/{BRANCH}')

            # Update last checked commit
            LAST_CHECKED_COMMIT = remote_commit.hexsha

            # Set file permissions
            set_file_permissions()

            # Prepare update message
            message = (
                f"🔄 *Update completed*\n\n"
                f"✅ New version: `{remote_commit.hexsha[:7]}`\n"
                f"📝 Commit message: {remote_commit.message.strip()}\n"
                f"👤 Author: {remote_commit.author.name}\n"
                f"📅 Date: {remote_commit.committed_datetime.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            notify_users(message)

            # Restart services if needed
            if stashed:
                logger.info("Restarting services after update")
                subprocess.run(['systemctl', 'restart', 'gfp-pckmgr'], check=True)
                subprocess.run(['systemctl', 'restart', 'gfp-pckmgr-updater'], check=True)

            logger.info("Update completed successfully")

        except Exception as e:
            logger.error(f"Error during update: {str(e)}")
            if stashed:
                logger.info("Restoring stashed changes")
                repo.git.stash('pop')
            raise

    except Exception as e:
        logger.error(f"Error in check_updates: {str(e)}")
        raise


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
                time.sleep(60)  # Wait before retrying

    except Exception as e:
        logger.error(f"Fatal error in update checker: {str(e)}")
        raise


if __name__ == '__main__':
    main()