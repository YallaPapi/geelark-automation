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
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


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
    MAX_RETRY_ATTEMPTS: int = 3

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

    # ==================== TIMEOUTS ====================

    # ADB command timeout
    ADB_TIMEOUT: int = 30

    # ADB device readiness timeout
    ADB_READY_TIMEOUT: int = 90

    # Appium connection timeout
    APPIUM_CONNECT_TIMEOUT: int = 60

    # Phone boot timeout
    PHONE_BOOT_TIMEOUT: int = 120

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
