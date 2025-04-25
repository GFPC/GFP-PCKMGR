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

# Configuration
REPO_PATH = '/opt/gfp-pckmgr'
REMOTE_URL = 'https://github.com/GFPC/GFP-PCKMGR.git'
DEFAULT_BRANCH = 'main'  # Или 'master' - уточните для вашего репозитория
CHECK_INTERVAL = 300  # 5 minutes


def handle_local_changes(repo):
    """Handle local changes by stashing them."""
    try:
        if repo.is_dirty():
            logger.warning("Found uncommitted changes - stashing them")
            repo.git.stash('save', '--include-untracked', 'Auto-stash by GFP Updater')
            return True
        return False
    except Exception as e:
        logger.error(f"Failed to stash changes: {str(e)}")
        raise


def setup_git_repo():
    """Initialize or update git repository with proper error handling."""
    try:
        # Create directory if not exists
        os.makedirs(REPO_PATH, exist_ok=True)

        # Initialize or open repository
        if not os.path.exists(os.path.join(REPO_PATH, '.git')):
            logger.info("Initializing new repository")
            repo = git.Repo.init(REPO_PATH)
            origin = repo.create_remote('origin', REMOTE_URL)
            origin.fetch()

            # Try to checkout default branch
            try:
                branch = DEFAULT_BRANCH
                repo.create_head(branch, origin.refs[branch])
                repo.heads[branch].set_tracking_branch(origin.refs[branch])
                repo.heads[branch].checkout()
            except Exception as e:
                logger.warning(f"Failed to checkout {branch}: {str(e)}")
                # Fallback to any available branch
                for ref in origin.refs:
                    if ref.name.startswith('origin/'):
                        branch = ref.name.split('/')[-1]
                        repo.create_head(branch, origin.refs[branch])
                        repo.heads[branch].set_tracking_branch(origin.refs[branch])
                        repo.heads[branch].checkout()
                        break
        else:
            repo = git.Repo(REPO_PATH)
            logger.info("Using existing repository")

            # Ensure remote is configured
            if 'origin' not in repo.remotes:
                origin = repo.create_remote('origin', REMOTE_URL)
            else:
                origin = repo.remotes.origin
                if origin.url != REMOTE_URL:
                    origin.set_url(REMOTE_URL)

            # Handle local changes before any operations
            stashed = handle_local_changes(repo)

            # Fetch latest changes
            origin.fetch()

            # Get current branch or use default
            try:
                branch = repo.active_branch.name
            except:
                branch = DEFAULT_BRANCH

            # Reset to remote branch
            try:
                repo.git.reset('--hard', f'origin/{branch}')
            except Exception as e:
                logger.error(f"Failed to reset to origin/{branch}: {str(e)}")
                if stashed:
                    repo.git.stash('pop')
                raise

        # Configure git user
        with repo.config_writer() as git_config:
            if not git_config.has_option('user', 'name'):
                git_config.set_value('user', 'name', 'GFP Package Manager')
            if not git_config.has_option('user', 'email'):
                git_config.set_value('user', 'email', 'bot@gfp-pckmgr')

        logger.info(f"Repository setup complete. Active branch: {repo.active_branch.name}")
        return repo

    except Exception as e:
        logger.error(f"Repository setup failed: {str(e)}")
        raise


def check_updates(repo):
    """Check for and apply updates with proper error handling."""
    try:
        # Handle local changes first
        stashed = handle_local_changes(repo)

        # Fetch all changes
        repo.remotes.origin.fetch()

        # Get current and remote commits
        branch = repo.active_branch.name
        current_commit = repo.head.commit
        remote_commit = repo.remotes.origin.refs[branch].commit

        logger.info(f"Local: {current_commit.hexsha[:7]}, Remote: {remote_commit.hexsha[:7]}")

        # Check if update needed
        if current_commit.hexsha == remote_commit.hexsha:
            logger.info("No updates available")
            if stashed:
                repo.git.stash('pop')
            return False

        # Apply updates
        try:
            logger.info(f"Updating to {remote_commit.hexsha[:7]}")
            repo.git.reset('--hard', f'origin/{branch}')

            # Restart services if needed
            if stashed:
                logger.info("Restarting services after update")
                subprocess.run(['systemctl', 'restart', 'gfp-pckmgr'], check=True)
                subprocess.run(['systemctl', 'restart', 'gfp-pckmgr-updater'], check=True)

            return True

        except Exception as e:
            logger.error(f"Update failed: {str(e)}")
            if stashed:
                repo.git.stash('pop')
            raise

    except Exception as e:
        logger.error(f"Update check failed: {str(e)}")
        raise


def main():
    """Main application loop."""
    logger.info("Starting update service")

    try:
        repo = setup_git_repo()

        while True:
            try:
                check_updates(repo)
            except Exception as e:
                logger.error(f"Update cycle failed: {str(e)}")

            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        logger.info("Service stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        raise


if __name__ == '__main__':
    main()