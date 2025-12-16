"""Base poster interface and shared types for multi-platform posting."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class PostResult:
    """Standardized result from a posting attempt.

    Attributes:
        success: Whether the post was successful.
        error: Error message if failed.
        error_type: Specific error type (e.g., 'suspended', 'adb_timeout', 'terminated').
        error_category: Error category ('account', 'infrastructure', 'unknown').
        retryable: Whether the job can be retried.
        platform: Platform identifier (e.g., 'instagram', 'tiktok').
        account: Account/phone name used for posting.
        duration_seconds: Time taken for the posting attempt.
        screenshot_path: Path to error screenshot if captured.
        timestamp: ISO timestamp of the result.
    """
    success: bool
    error: Optional[str] = None
    error_type: Optional[str] = None
    error_category: Optional[str] = None
    retryable: bool = True
    platform: str = ""
    account: str = ""
    duration_seconds: float = 0.0
    screenshot_path: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class BasePoster(ABC):
    """Abstract base class for platform-specific posters.

    All platform posters (Instagram, TikTok, YouTube Shorts, etc.) must
    implement this interface to work with the parallel posting system.

    The posting flow is:
        1. Create poster with get_poster(platform, phone_name, **kwargs)
        2. Call connect() to establish device connection
        3. Call post(video_path, caption) to execute posting
        4. Call cleanup() to release resources

    Example:
        poster = get_poster('instagram', 'my_account', system_port=8200)
        if poster.connect():
            result = poster.post('/path/to/video.mp4', 'Check this out!')
            if result.success:
                print('Posted successfully!')
            else:
                print(f'Failed: {result.error}')
        poster.cleanup()
    """

    @property
    @abstractmethod
    def platform(self) -> str:
        """Return platform identifier (e.g., 'instagram', 'tiktok')."""
        pass

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection to device.

        This includes:
        - Finding the phone in Geelark
        - Starting the phone if not running
        - Connecting via ADB
        - Creating Appium session

        Returns:
            True if connection successful, False otherwise.
        """
        pass

    @abstractmethod
    def post(self, video_path: str, caption: str, humanize: bool = False) -> PostResult:
        """Execute the posting flow.

        Args:
            video_path: Path to video file on local machine.
            caption: Caption text for the post.
            humanize: If True, perform human-like delays and actions.

        Returns:
            PostResult with success status and error details if failed.
        """
        pass

    @abstractmethod
    def cleanup(self):
        """Release resources and disconnect from device.

        This should:
        - Close Appium session
        - Disconnect ADB
        - Optionally stop the phone
        - Clean up any temporary files
        """
        pass
