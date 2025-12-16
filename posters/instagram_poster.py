"""Instagram poster adapter - wraps SmartInstagramPoster with BasePoster interface."""
import time
from typing import Optional

from .base_poster import BasePoster, PostResult


class InstagramPoster(BasePoster):
    """Instagram poster implementation using SmartInstagramPoster.

    This is an adapter that wraps the existing SmartInstagramPoster class
    to conform to the BasePoster interface, enabling the factory pattern
    for multi-platform support.

    The underlying SmartInstagramPoster handles:
    - Device connection via DeviceConnectionManager
    - Claude AI-driven UI navigation
    - Instagram-specific error detection
    - Video upload and posting flow
    """

    # Instagram package name (used internally by SmartInstagramPoster)
    APP_PACKAGE = "com.instagram.android"

    # Error types that indicate account-level issues (non-retryable)
    ACCOUNT_ERROR_TYPES = {'suspended', 'terminated', 'id_verification', 'logged_out', 'captcha'}

    def __init__(
        self,
        phone_name: str,
        system_port: int = 8200,
        appium_url: str = None
    ):
        """Initialize Instagram poster.

        Args:
            phone_name: Geelark phone name to post from.
            system_port: UiAutomator2 systemPort for Appium.
            appium_url: Appium server URL (e.g., 'http://127.0.0.1:4723').
        """
        self._phone_name = phone_name
        self._system_port = system_port
        self._appium_url = appium_url
        self._poster = None  # Lazy init to avoid import at module load
        self._connected = False
        self._start_time = None

    @property
    def platform(self) -> str:
        """Return platform identifier."""
        return "instagram"

    def _ensure_poster(self):
        """Lazy-initialize the underlying SmartInstagramPoster."""
        if self._poster is None:
            # Import here to avoid circular imports and ensure ANDROID_HOME is set
            from post_reel_smart import SmartInstagramPoster
            self._poster = SmartInstagramPoster(
                phone_name=self._phone_name,
                system_port=self._system_port,
                appium_url=self._appium_url
            )

    def connect(self) -> bool:
        """Connect to device via SmartInstagramPoster.

        Returns:
            True if connection successful, False otherwise.
        """
        self._ensure_poster()
        self._start_time = time.time()

        try:
            self._poster.connect()
            self._connected = True
            return True
        except Exception as e:
            print(f"[InstagramPoster] Connect failed: {e}")
            return False

    def post(self, video_path: str, caption: str, humanize: bool = False) -> PostResult:
        """Post to Instagram via SmartInstagramPoster.

        Args:
            video_path: Path to video file.
            caption: Caption text.
            humanize: Whether to perform human-like actions.

        Returns:
            PostResult with outcome details.
        """
        if not self._connected:
            return PostResult(
                success=False,
                error="Not connected - call connect() first",
                error_type="connection_error",
                error_category="infrastructure",
                retryable=True,
                platform=self.platform,
                account=self._phone_name
            )

        try:
            success = self._poster.post(video_path, caption, humanize=humanize)
            duration = time.time() - self._start_time if self._start_time else 0

            if success:
                return PostResult(
                    success=True,
                    platform=self.platform,
                    account=self._phone_name,
                    duration_seconds=duration
                )
            else:
                # Extract error info from SmartInstagramPoster
                error_msg = self._poster.last_error_message or "Post failed"
                error_type = self._poster.last_error_type or "unknown"
                screenshot = self._poster.last_screenshot_path

                # Determine if retryable based on error type
                retryable = error_type not in self.ACCOUNT_ERROR_TYPES

                # Map to category
                category = 'account' if error_type in self.ACCOUNT_ERROR_TYPES else 'infrastructure'

                return PostResult(
                    success=False,
                    error=error_msg,
                    error_type=error_type,
                    error_category=category,
                    retryable=retryable,
                    platform=self.platform,
                    account=self._phone_name,
                    duration_seconds=duration,
                    screenshot_path=screenshot
                )

        except Exception as e:
            duration = time.time() - self._start_time if self._start_time else 0
            return PostResult(
                success=False,
                error=f"{type(e).__name__}: {str(e)}",
                error_type="exception",
                error_category="infrastructure",
                retryable=True,
                platform=self.platform,
                account=self._phone_name,
                duration_seconds=duration
            )

    def cleanup(self):
        """Cleanup via SmartInstagramPoster."""
        if self._poster:
            try:
                self._poster.cleanup()
            except Exception as e:
                print(f"[InstagramPoster] Cleanup warning: {e}")
            finally:
                self._poster = None
                self._connected = False
