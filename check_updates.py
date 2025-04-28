#!/usr/bin/env python3
import os
import logging
import time
import git
import subprocess
import shutil
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
CHECK_INTERVAL = 300  # 5 minutes


def backup_local_files():
    """Backup locally modified files before overwriting them."""
    try:
        backup_dir = os.path.join(REPO_PATH, 'backup')
        os.makedirs(backup_dir, exist_ok=True)

        for file in ['check_updates.py', 'gfp_pckmgr.py']:
            src = os.path.join(REPO_PATH, file)
            if os.path.exists(src):
                dst = os.path.join(backup_dir, f"{file}.bak.{int(time.time())}")
                shutil.copy2(src, dst)
                logger.info(f"Backed up {file} to {dst}")
        return True
    except Exception as e:
        logger.error(f"Backup failed: {str(e)}")
        return False


def setup_git_repo():
    """Initialize or clean up git repository."""
    try:
        # Create directory if not exists
        os.makedirs(REPO_PATH, exist_ok=True)

        try:
            repo = git.Repo(REPO_PATH)
            logger.info("Using existing repository")

            # Backup local changes before any operations
            if not backup_local_files():
                logger.warning("Failed to backup files, continuing anyway")

            # Reset any local changes
            repo.git.reset('--hard')
            repo.git.clean('-fd', '--exclude=backup', '--exclude=.env')

            # Configure remote
            if 'origin' not in repo.remotes:
                origin = repo.create_remote('origin', REMOTE_URL)
            else:
                origin = repo.remotes.origin
                if origin.url != REMOTE_URL:
                    origin.set_url(REMOTE_URL)

            # Fetch updates
            origin.fetch()

            # Determine active branch
            try:
                branch = repo.active_branch.name
                logger.info(f"Current active branch: {branch}")
            except:
                branch = 'main'  # Default fallback
                logger.info(f"No active branch detected, using default: {branch}")

            # Verify branch exists
            if f'origin/{branch}' not in repo.references:
                logger.warning(f"Branch origin/{branch} not found, searching for available branches")
                available_branches = []
                for ref in repo.references:
                    if ref.name.startswith('origin/'):
                        available_branches.append(ref.name.split('/')[-1])
                
                if available_branches:
                    branch = available_branches[0]
                    logger.info(f"Found available branches: {available_branches}, using {branch}")
                else:
                    raise Exception("No remote branches found")

            # Reset to remote branch
            logger.info(f"Resetting to origin/{branch}")
            repo.git.reset('--hard', f'origin/{branch}')

            # Ensure we're on the correct branch
            if branch != repo.active_branch.name:
                logger.info(f"Switching to branch {branch}")
                repo.git.checkout(branch)

        except git.exc.InvalidGitRepositoryError:
            # Initialize new repository
            logger.info("Initializing new repository")
            repo = git.Repo.init(REPO_PATH)
            origin = repo.create_remote('origin', REMOTE_URL)

            # First fetch
            origin.fetch()

            # Determine available branch
            branch = 'main'  # Default
            available_branches = []
            for ref in origin.refs:
                if ref.name.startswith('origin/'):
                    available_branches.append(ref.name.split('/')[-1])
            
            if available_branches:
                branch = available_branches[0]
                logger.info(f"Found available branches: {available_branches}, using {branch}")
            else:
                logger.warning("No remote branches found, using default 'main'")

            # Checkout branch
            repo.create_head(branch, origin.refs[branch])
            repo.heads[branch].set_tracking_branch(origin.refs[branch])
            repo.heads[branch].checkout()
            repo.git.reset('--hard', f'origin/{branch}')

        # Configure git user
        with repo.config_writer() as git_config:
            if not git_config.has_option('user', 'name'):
                git_config.set_value('user', 'name', 'GFP Package Manager')
            if not git_config.has_option('user', 'email'):
                git_config.set_value('user', 'email', 'bot@gfp-pckmgr')

        logger.info(f"Repository ready. Branch: {repo.active_branch.name}")
        return repo

    except Exception as e:
        logger.error(f"Repository setup failed: {str(e)}")
        raise


def check_updates(repo):
    """Check for and apply updates."""
    try:
        # Get current state
        try:
            branch = repo.active_branch.name
        except:
            branch = 'main'  # Default fallback

        current_commit = repo.head.commit

        # Fetch updates
        repo.remotes.origin.fetch()

        # Verify branch exists
        if f'origin/{branch}' not in repo.references:
            logger.warning(f"Branch origin/{branch} not found, searching for available branches")
            available_branches = []
            for ref in repo.references:
                if ref.name.startswith('origin/'):
                    available_branches.append(ref.name.split('/')[-1])
            
            if available_branches:
                branch = available_branches[0]
                logger.info(f"Found available branches: {available_branches}, using {branch}")
            else:
                raise Exception("No remote branches found")

        # Get remote commit
        remote_commit = repo.remotes.origin.refs[branch].commit

        logger.info(f"Local: {current_commit.hexsha[:7]}, Remote: {remote_commit.hexsha[:7]}")

        # Check if update needed
        if current_commit.hexsha == remote_commit.hexsha:
            logger.info("No updates available")
            return False

        # Apply updates
        logger.info(f"Updating to {remote_commit.hexsha[:7]}")

        # Backup local changes
        if not backup_local_files():
            logger.warning("Failed to backup files, continuing with update")

        # Reset to remote
        logger.info(f"Resetting to origin/{branch}")
        repo.git.reset('--hard', f'origin/{branch}')

        # Restart services
        logger.info("Restarting services")
        subprocess.run(['systemctl', 'restart', 'gfp-pckmgr'], check=True)
        subprocess.run(['systemctl', 'restart', 'gfp-pckmgr-updater'], check=True)

        return True

    except Exception as e:
        logger.error(f"Update failed: {str(e)}")
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