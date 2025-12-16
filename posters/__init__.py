"""Platform poster factory and exports.

This package provides a unified interface for posting to different social
media platforms (Instagram, TikTok, etc.) using the same orchestration
infrastructure.

Usage:
    from posters import get_poster, PostResult

    # Create a platform-specific poster
    poster = get_poster('instagram', 'my_account', system_port=8200)

    # Use the standard interface
    if poster.connect():
        result = poster.post('/path/to/video.mp4', 'My caption')
        if result.success:
            print('Posted!')
    poster.cleanup()
"""
from .base_poster import BasePoster, PostResult

__all__ = ['BasePoster', 'PostResult', 'get_poster']


def get_poster(platform: str, phone_name: str, **kwargs) -> BasePoster:
    """Factory function to get platform-specific poster.

    This is the main entry point for creating posters. It returns the
    appropriate BasePoster implementation based on the platform.

    Args:
        platform: Platform identifier ('instagram', 'tiktok', 'youtube_shorts').
        phone_name: Geelark phone name to post from.
        **kwargs: Additional args passed to poster constructor:
            - system_port: UiAutomator2 systemPort (default: 8200)
            - appium_url: Appium server URL (default: http://127.0.0.1:4723)

    Returns:
        BasePoster implementation for the specified platform.

    Raises:
        ValueError: If platform is not supported.

    Example:
        poster = get_poster(
            platform='instagram',
            phone_name='my_account',
            system_port=8200,
            appium_url='http://127.0.0.1:4723'
        )
    """
    platform_lower = platform.lower().strip()

    if platform_lower == "instagram":
        from .instagram_poster import InstagramPoster
        return InstagramPoster(phone_name, **kwargs)

    elif platform_lower == "tiktok":
        # TikTok poster will be implemented later
        from .tiktok_poster import TikTokPoster
        return TikTokPoster(phone_name, **kwargs)

    elif platform_lower == "youtube_shorts":
        # YouTube Shorts poster will be implemented later
        raise ValueError(f"Platform '{platform}' is not yet implemented")

    else:
        raise ValueError(
            f"Unsupported platform: '{platform}'. "
            f"Supported platforms: instagram, tiktok"
        )
