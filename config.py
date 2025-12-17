"""
Centralized Configuration Module.

This is the SINGLE SOURCE OF TRUTH for all paths and configuration values.
All other modules should import from here instead of defining their own paths.

Usage:
    from config import Config, setup_environment

    # At module startup
    setup_environment()

    # Use paths
    adb_path = Config.ADB_PATH
"""

import os
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass(frozen=True)
class Config:
    """
    Centralized configuration constants.

    These values should NEVER be redefined in other files.
    If you need to change a value, change it HERE.
    """

    # ==================== PATHS ====================

    # Android SDK - use the one with Appium compatibility
    ANDROID_SDK_PATH: str = r"C:\Users\asus\Downloads\android-sdk"

    # ADB executable path - derived from SDK path for consistency
    ADB_PATH: str = os.path.join(ANDROID_SDK_PATH, "platform-tools", "adb.exe")

    # Project root directory
    PROJECT_ROOT: str = os.path.dirname(os.path.abspath(__file__))

    # ==================== APPIUM ====================

    # Base Appium port (workers use 4723, 4725, 4727, etc.)
    APPIUM_BASE_PORT: int = 4723

    # Default Appium URL for single-worker mode
    DEFAULT_APPIUM_URL: str = "http://127.0.0.1:4723"

    # ==================== PARALLEL EXECUTION ====================

    # Default number of parallel workers
    DEFAULT_NUM_WORKERS: int = 3

    # Maximum workers (limited by ports and system resources)
    MAX_WORKERS: int = 10

    # Port allocation for workers:
    # - Appium ports: 4723, 4725, 4727, ... (odd ports)
    # - systemPort ranges: 8200-8209, 8210-8219, 8220-8229, ...
    SYSTEM_PORT_BASE: int = 8200
    SYSTEM_PORT_RANGE: int = 10  # Ports per worker

    # ==================== JOB EXECUTION ====================

    # Maximum posts per account per day (prevents account bans)
    MAX_POSTS_PER_ACCOUNT_PER_DAY: int = 1

    # Delay between jobs in seconds
    DELAY_BETWEEN_JOBS: int = 10

    # Job timeout in seconds
    JOB_TIMEOUT: int = 300

    # Shutdown timeout in seconds
    SHUTDOWN_TIMEOUT: int = 60

    # ==================== RETRY SETTINGS ====================

    # Maximum retry attempts for failed jobs
    MAX_RETRY_ATTEMPTS: int = 5

    # Delay between retries in minutes
    RETRY_DELAY_MINUTES: int = 5

    # Non-retryable error types
    NON_RETRYABLE_ERRORS: frozenset = frozenset({
        'suspended', 'captcha', 'loggedout', 'actionblocked', 'banned'
    })

    # ==================== FILES ====================

    # Progress file for parallel workers
    PROGRESS_FILE: str = "parallel_progress.csv"

    # Scheduler state file
    STATE_FILE: str = "scheduler_state.json"

    # Logs directory
    LOGS_DIR: str = "logs"

    # Accounts file
    ACCOUNTS_FILE: str = "accounts.txt"

    # ==================== CAMPAIGNS ====================

    # Directory containing campaign folders
    CAMPAIGNS_DIR: str = "campaigns"

    # Campaign config file name (within each campaign folder)
    CAMPAIGN_CONFIG_FILE: str = "campaign.json"

    # Default campaign file names
    CAMPAIGN_ACCOUNTS_FILE: str = "accounts.txt"
    CAMPAIGN_PROGRESS_FILE: str = "progress.csv"
    CAMPAIGN_STATE_FILE: str = "scheduler_state.json"

    # ==================== TIMEOUTS ====================

    # ADB command timeout
    ADB_TIMEOUT: int = 30

    # ADB device readiness timeout
    ADB_READY_TIMEOUT: int = 90

    # Appium connection timeout
    APPIUM_CONNECT_TIMEOUT: int = 60

    # Phone boot timeout
    PHONE_BOOT_TIMEOUT: int = 120

    # ==================== SCREEN COORDINATES ====================
    # For Geelark cloud phones (720x1280 resolution)
    # Used for swipe/tap operations in UI automation

    SCREEN_CENTER_X: int = 360          # Horizontal center of screen
    SCREEN_CENTER_Y: int = 640          # Vertical center of screen
    FEED_TOP_Y: int = 400               # Top position for feed scroll
    FEED_BOTTOM_Y: int = 900            # Bottom position for feed scroll
    REELS_TOP_Y: int = 300              # Top position for reels scroll
    REELS_BOTTOM_Y: int = 1000          # Bottom position for reels scroll
    NOTIFICATIONS_TOP_Y: int = 800      # Top position for notifications scroll
    STORY_NEXT_TAP_X: int = 650         # Right side of screen for story navigation
    SWIPE_DURATION_FAST: int = 300      # Duration in ms for fast swipes
    SWIPE_DURATION_SLOW: int = 200      # Duration in ms for slower swipes
    SWIPE_DURATION_MAX: int = 400       # Maximum swipe duration for randomization

    # ==================== CLASS METHODS ====================

    @classmethod
    def get_worker_appium_port(cls, worker_id: int) -> int:
        """Get the Appium port for a specific worker."""
        return cls.APPIUM_BASE_PORT + (worker_id * 2)

    @classmethod
    def get_worker_system_port_range(cls, worker_id: int) -> tuple:
        """Get the systemPort range for a specific worker."""
        start = cls.SYSTEM_PORT_BASE + (worker_id * cls.SYSTEM_PORT_RANGE)
        end = start + cls.SYSTEM_PORT_RANGE - 1
        return (start, end)

    @classmethod
    def get_worker_appium_url(cls, worker_id: int) -> str:
        """Get the Appium URL for a specific worker."""
        port = cls.get_worker_appium_port(worker_id)
        return f"http://127.0.0.1:{port}"


@dataclass
class CampaignConfig:
    """
    Configuration for a single posting campaign.

    Each campaign has its own folder with accounts, videos, captions, and progress.
    This allows running multiple campaigns (podcast, viral, etc.) independently.

    Usage:
        # Load from campaign folder
        campaign = CampaignConfig.from_folder("campaigns/viral")

        # Access paths
        accounts = campaign.accounts_file
        progress = campaign.progress_file
    """

    name: str                              # Campaign name (e.g., "viral", "podcast")
    base_dir: str                          # Campaign folder path
    accounts_file: str                     # Path to accounts.txt
    progress_file: str                     # Path to progress.csv
    state_file: str                        # Path to scheduler_state.json
    videos_dir: str                        # Path to videos folder
    captions_file: str                     # Path to captions CSV
    max_posts_per_account_per_day: int = 1 # Daily limit per account
    enabled: bool = True                   # Whether campaign is active

    # CSV format configuration
    caption_column: str = "post_caption"   # Column name for caption text
    filename_column: str = "filename"      # Column name for video filename

    @classmethod
    def from_folder(cls, campaign_path: str) -> 'CampaignConfig':
        """
        Load campaign configuration from a folder.

        Expected folder structure:
            campaign_path/
            ├── campaign.json (optional - for settings override)
            ├── accounts.txt
            ├── captions.csv
            ├── progress.csv (created automatically)
            └── videos/ (or any subfolder with .mp4 files)

        Args:
            campaign_path: Path to campaign folder (relative or absolute)

        Returns:
            CampaignConfig instance

        Raises:
            FileNotFoundError: If campaign folder doesn't exist
            ValueError: If required files are missing
        """
        base_dir = os.path.abspath(campaign_path)

        if not os.path.isdir(base_dir):
            raise FileNotFoundError(f"Campaign folder not found: {base_dir}")

        # Get campaign name from folder
        name = os.path.basename(base_dir)

        # Default paths
        accounts_file = os.path.join(base_dir, Config.CAMPAIGN_ACCOUNTS_FILE)
        progress_file = os.path.join(base_dir, Config.CAMPAIGN_PROGRESS_FILE)
        state_file = os.path.join(base_dir, Config.CAMPAIGN_STATE_FILE)

        # Find captions file (look for .csv files)
        captions_file = None
        for f in os.listdir(base_dir):
            if f.endswith('.csv') and f != Config.CAMPAIGN_PROGRESS_FILE:
                captions_file = os.path.join(base_dir, f)
                break

        # Find videos directory (first subfolder with .mp4 files)
        videos_dir = None
        for item in os.listdir(base_dir):
            item_path = os.path.join(base_dir, item)
            if os.path.isdir(item_path):
                # Check if it has mp4 files
                for root, dirs, files in os.walk(item_path):
                    if any(f.endswith('.mp4') for f in files):
                        videos_dir = item_path
                        break
                if videos_dir:
                    break

        # Load optional campaign.json for settings override
        config_file = os.path.join(base_dir, Config.CAMPAIGN_CONFIG_FILE)
        settings = {}
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                settings = json.load(f)

        # Validate required files
        if not os.path.exists(accounts_file):
            raise ValueError(f"Campaign missing accounts.txt: {accounts_file}")
        if captions_file is None or not os.path.exists(captions_file):
            raise ValueError(f"Campaign missing captions CSV in: {base_dir}")
        if videos_dir is None:
            raise ValueError(f"Campaign missing videos folder in: {base_dir}")

        # Detect CSV format by reading header
        caption_column = "post_caption"
        filename_column = "filename"
        with open(captions_file, 'r', encoding='utf-8') as f:
            header = f.readline().strip().lower()
            # Handle podcast format: "Text,Image/Video link 1 (shortcode)"
            if "text" in header and "shortcode" in header:
                caption_column = "Text"
                filename_column = "shortcode"  # Special handling needed
            # Handle viral format: "filename,onscreen_text,post_caption"
            elif "post_caption" in header:
                caption_column = "post_caption"
                filename_column = "filename"

        return cls(
            name=settings.get('name', name),
            base_dir=base_dir,
            accounts_file=accounts_file,
            progress_file=progress_file,
            state_file=state_file,
            videos_dir=videos_dir,
            captions_file=captions_file,
            max_posts_per_account_per_day=settings.get('max_posts_per_account_per_day', 1),
            enabled=settings.get('enabled', True),
            caption_column=caption_column,
            filename_column=filename_column,
        )

    @classmethod
    def list_campaigns(cls, campaigns_dir: str = None) -> List['CampaignConfig']:
        """
        List all available campaigns.

        Args:
            campaigns_dir: Path to campaigns directory (default: Config.CAMPAIGNS_DIR)

        Returns:
            List of CampaignConfig for each valid campaign folder
        """
        if campaigns_dir is None:
            campaigns_dir = os.path.join(Config.PROJECT_ROOT, Config.CAMPAIGNS_DIR)

        campaigns = []
        if not os.path.isdir(campaigns_dir):
            return campaigns

        for item in os.listdir(campaigns_dir):
            item_path = os.path.join(campaigns_dir, item)
            if os.path.isdir(item_path):
                try:
                    campaign = cls.from_folder(item_path)
                    campaigns.append(campaign)
                except (FileNotFoundError, ValueError):
                    # Skip invalid campaign folders
                    pass

        return campaigns

    def get_accounts(self) -> List[str]:
        """Load and return list of accounts for this campaign."""
        with open(self.accounts_file, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]

    def __str__(self) -> str:
        return f"Campaign({self.name}, accounts={self.accounts_file}, videos={self.videos_dir})"


@dataclass
class PostingContext:
    """
    Unified context for all posting operations.

    This is the single source of truth for file paths and settings,
    whether running a campaign or in legacy mode.

    Usage:
        # Campaign mode
        campaign = CampaignConfig.from_folder("campaigns/viral")
        ctx = PostingContext.from_campaign(campaign)

        # Legacy mode
        ctx = PostingContext.legacy()

        # Use in functions
        tracker = ProgressTracker(ctx.progress_file)
        accounts = ctx.get_accounts()
    """

    # Required paths
    progress_file: str
    accounts_file: str

    # Optional paths (campaign mode)
    state_file: Optional[str] = None
    videos_dir: Optional[str] = None
    captions_file: Optional[str] = None

    # Settings
    max_posts_per_account_per_day: int = 1

    # Source info
    campaign_name: Optional[str] = None  # None = legacy mode
    campaign_config: Optional['CampaignConfig'] = None

    @classmethod
    def from_campaign(cls, campaign: 'CampaignConfig') -> 'PostingContext':
        """
        Create context from a CampaignConfig.

        Args:
            campaign: CampaignConfig loaded from a campaign folder

        Returns:
            PostingContext with all campaign paths and settings
        """
        return cls(
            progress_file=campaign.progress_file,
            accounts_file=campaign.accounts_file,
            state_file=campaign.state_file,
            videos_dir=campaign.videos_dir,
            captions_file=campaign.captions_file,
            max_posts_per_account_per_day=campaign.max_posts_per_account_per_day,
            campaign_name=campaign.name,
            campaign_config=campaign,
        )

    @classmethod
    def legacy(
        cls,
        progress_file: str = None,
        accounts_file: str = None,
        state_file: str = None,
        max_posts_per_account_per_day: int = None,
    ) -> 'PostingContext':
        """
        Create context for legacy (non-campaign) mode.

        Uses default Config values if not specified.

        Args:
            progress_file: Progress CSV path (default: Config.PROGRESS_FILE)
            accounts_file: Accounts file path (default: Config.ACCOUNTS_FILE)
            state_file: State JSON path (default: Config.STATE_FILE)
            max_posts_per_account_per_day: Daily limit (default: Config.MAX_POSTS_PER_ACCOUNT_PER_DAY)

        Returns:
            PostingContext for legacy mode
        """
        return cls(
            progress_file=progress_file or Config.PROGRESS_FILE,
            accounts_file=accounts_file or Config.ACCOUNTS_FILE,
            state_file=state_file or Config.STATE_FILE,
            max_posts_per_account_per_day=max_posts_per_account_per_day or Config.MAX_POSTS_PER_ACCOUNT_PER_DAY,
            campaign_name=None,
            campaign_config=None,
        )

    def get_accounts(self) -> List[str]:
        """
        Load accounts from the appropriate source.

        Returns:
            List of account names

        Raises:
            ValueError: If no accounts found
        """
        if self.campaign_config:
            accounts = self.campaign_config.get_accounts()
        else:
            with open(self.accounts_file, 'r', encoding='utf-8') as f:
                accounts = [line.strip() for line in f if line.strip()]

        if not accounts:
            raise ValueError(f"No accounts found in {self.accounts_file}")

        return accounts

    def is_campaign_mode(self) -> bool:
        """Check if running in campaign mode."""
        return self.campaign_name is not None

    def describe(self) -> str:
        """
        Human-readable description of this context.

        Returns:
            Description string for logging
        """
        if self.campaign_name:
            return f"campaign '{self.campaign_name}'"
        return "legacy mode (root files)"

    def __str__(self) -> str:
        return f"PostingContext({self.describe()}, progress={self.progress_file})"


def setup_environment() -> None:
    """
    Set up environment variables for Android SDK and ADB.

    Call this early in your script before any Appium imports.
    """
    os.environ['ANDROID_HOME'] = Config.ANDROID_SDK_PATH
    os.environ['ANDROID_SDK_ROOT'] = Config.ANDROID_SDK_PATH

    # Add platform-tools to PATH if not already there
    platform_tools = os.path.join(Config.ANDROID_SDK_PATH, 'platform-tools')
    current_path = os.environ.get('PATH', '')
    if platform_tools not in current_path:
        os.environ['PATH'] = f"{platform_tools};{current_path}"


def get_adb_env() -> dict:
    """
    Get environment dict with ANDROID_HOME properly set.

    Use this when spawning subprocesses that need ADB.
    """
    env = os.environ.copy()
    env['ANDROID_HOME'] = Config.ANDROID_SDK_PATH
    env['ANDROID_SDK_ROOT'] = Config.ANDROID_SDK_PATH

    platform_tools = os.path.join(Config.ANDROID_SDK_PATH, 'platform-tools')
    if platform_tools not in env.get('PATH', ''):
        env['PATH'] = f"{platform_tools};{env.get('PATH', '')}"

    return env


# Validate configuration on import
def _validate_config():
    """Validate that critical paths exist."""
    if not os.path.exists(Config.ANDROID_SDK_PATH):
        print(f"WARNING: ANDROID_SDK_PATH does not exist: {Config.ANDROID_SDK_PATH}")

    if not os.path.exists(Config.ADB_PATH):
        print(f"WARNING: ADB_PATH does not exist: {Config.ADB_PATH}")


# Run validation on import
_validate_config()
