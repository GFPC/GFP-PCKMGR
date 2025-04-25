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


def get_remote_branch(repo):
    """Determine the default branch from remote repository."""
    try:
        # Fetch all remote branches
        repo.git.fetch('--all')

        # Try to get default branch from remote
        remote_head = repo.git.ls_remote('--symref', 'origin', 'HEAD')
        for line in remote_head.split('\n'):
            if 'ref:' in line:
                return line.split('refs/heads/')[-1].split()[0]

        # Fallback to common branch names
        for branch in ['main', 'master']:
            if f'origin/{branch}' in repo.references:
                return branch

        raise Exception("Cannot determine default branch from remote")
    except Exception as e:
        logger.error(f"Error detecting remote branch: {str(e)}")
        return DEFAULT_BRANCH  # Fallback


def setup_git_repo():
    """Initialize or update git repository."""
    try:
        # Create directory if not exists
        os.makedirs(REPO_PATH, exist_ok=True)

        # Initialize repository
        if not os.path.exists(os.path.join(REPO_PATH, '.git')):
            logger.info("Initializing new repository")
            repo = git.Repo.init(REPO_PATH)
            origin = repo.create_remote('origin', REMOTE_URL)
            origin.fetch()

            # Determine and checkout default branch
            branch = get_remote_branch(repo)
            repo.create_head(branch, origin.refs[branch])
            repo.heads[branch].set_tracking_branch(origin.refs[branch])
            repo.heads[branch].checkout()
        else:
            repo = git.Repo(REPO_PATH)
            logger.info("Using existing repository")

            # Ensure remote is configured
            if 'origin' not in repo.remotes:
                origin = repo.create_remote('origin', REMOTE_URL)
            else:
                origin = repo.remotes.origin
                origin.set_url(REMOTE_URL)

            # Determine current branch
            branch = get_remote_branch(repo)
            if branch not in repo.heads:
                repo.create_head(branch, origin.refs[branch])

            repo.heads[branch].set_tracking_branch(origin.refs[branch])
            repo.heads[branch].checkout()

        # Configure git user
        with repo.config_writer() as git_config:
            if not git_config.has_option('user', 'name'):
                git_config.set_value('user', 'name', 'GFP Package Manager')
            if not git_config.has_option('user', 'email'):
                git_config.set_value('user', 'email', 'bot@gfp-pckmgr')

        # Verify repository state
        if repo.bare:
            raise Exception("Repository is bare")

        logger.info(f"Repository ready. Branch: {repo.active_branch.name}")
        return repo

    except Exception as e:
        logger.error(f"Repository setup failed: {str(e)}")
        raise


def check_updates(repo):
    """Check for and apply updates."""
    try:
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
            return False

        # Stash local changes if any
        stashed = False
        if repo.is_dirty():
            logger.info("Stashing local changes")
            repo.git.stash('save', '--keep-index', 'Auto-stash before update')
            stashed = True

        try:
            # Reset to remote branch
            repo.git.reset('--hard', f'origin/{branch}')
            logger.info(f"Updated to commit: {repo.head.commit.hexsha[:7]}")

            # Restart services if needed
            if stashed:
                logger.info("Restarting services")
                subprocess.run(['systemctl', 'restart', 'gfp-pckmgr'], check=True)
                subprocess.run(['systemctl', 'restart', 'gfp-pckmgr-updater'], check=True)

            return True

        except Exception as e:
            if stashed:
                logger.info("Restoring stashed changes")
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