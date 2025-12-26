"""
GrapheneOS-specific configuration.

This module contains all settings specific to GrapheneOS physical devices.
Edit PROFILE_MAPPING to map your Instagram/TikTok accounts to the
correct Android user profiles.

To find your profile IDs, run:
    adb shell pm list users

Example output:
    Users:
        UserInfo{0:Owner:c13} running
        UserInfo{10:Profile 1:410} running
        UserInfo{11:Profile 2:410}
"""

# =============================================================================
# DEVICE CONFIGURATION
# =============================================================================

# Pixel 7 device serial number (from `adb devices`)
DEVICE_SERIAL = "32271FDH2006RW"

# =============================================================================
# PROFILE MAPPING
# =============================================================================
# Map Instagram/TikTok account names to Android user profile IDs.
#
# How it works:
#   - GrapheneOS supports multiple user profiles (like separate phones)
#   - User 0 = Owner profile (main)
#   - User 10, 11, 12... = Secondary profiles
#   - Each profile has its own app data (separate IG/TT logins)
#
# Instructions:
#   1. Create profiles in GrapheneOS Settings > System > Multiple users
#   2. Install and log into Instagram/TikTok on each profile
#   3. Map account names below to the profile where that account is logged in
#
# Example: If "my_ig_account" is logged into Instagram on Profile 1 (user 10):
#   "my_ig_account": 10,

PROFILE_MAPPING = {
    # ==========================================================
    # Profile 0 (Owner) - Main profile accounts
    # ==========================================================
    "darklichencoded": 0,   # Instagram
    "robottekfqc": 0,       # TikTok

    # ==========================================================
    # Profile 10 (Profile "1") - First secondary profile
    # ==========================================================
    # Add accounts logged into Profile 1 here
    # "profile1_instagram_account": 10,
    # "profile1_tiktok_account": 10,

    # ==========================================================
    # Profile 11 (Profile "2") - Second secondary profile
    # ==========================================================
    # Add accounts logged into Profile 2 here
    # "profile2_instagram_account": 11,
    # "profile2_tiktok_account": 11,

    # ==========================================================
    # Profile 12 (Profile "3") - Third secondary profile
    # ==========================================================
    "alice.in.wonderlan31": 12,  # TikTok
}

# =============================================================================
# SCREEN COORDINATES
# =============================================================================
# Pixel 7 screen: 1080 x 2400 pixels
# These coordinates are used for swipe/tap operations

PIXEL_SCREEN = {
    'width': 1080,
    'height': 2400,
    'center_x': 540,
    'center_y': 1200,
    'feed_top_y': 600,
    'feed_bottom_y': 1800,
}

# Individual constants for direct import
PIXEL_SCREEN_WIDTH = 1080
PIXEL_SCREEN_HEIGHT = 2400
PIXEL_SCREEN_CENTER_X = 540
PIXEL_SCREEN_CENTER_Y = 1200
PIXEL_FEED_TOP_Y = 600
PIXEL_FEED_BOTTOM_Y = 1800
PIXEL_SWIPE_DURATION = 300  # milliseconds


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_profile_for_account(account_name: str) -> int:
    """
    Get the Android user profile ID for an account.

    Args:
        account_name: Instagram/TikTok account name

    Returns:
        Profile user ID (0, 10, 11, etc.)

    Raises:
        KeyError: If account not found in PROFILE_MAPPING
    """
    if account_name not in PROFILE_MAPPING:
        raise KeyError(
            f"Account '{account_name}' not found in PROFILE_MAPPING. "
            f"Add it to grapheneos_config.py with the correct profile ID."
        )
    return PROFILE_MAPPING[account_name]


def list_accounts_for_profile(profile_id: int) -> list:
    """
    Get all accounts mapped to a specific profile.

    Args:
        profile_id: Android user profile ID

    Returns:
        List of account names on that profile
    """
    return [
        account for account, pid in PROFILE_MAPPING.items()
        if pid == profile_id
    ]


def validate_config() -> bool:
    """
    Validate the configuration is properly set up.

    Returns:
        True if valid, raises exception if not
    """
    if not DEVICE_SERIAL:
        raise ValueError("DEVICE_SERIAL is not set")

    if not PROFILE_MAPPING:
        raise ValueError(
            "PROFILE_MAPPING is empty. Add your accounts to grapheneos_config.py"
        )

    # Check all profile IDs are valid (non-negative integers)
    for account, profile_id in PROFILE_MAPPING.items():
        if not isinstance(profile_id, int) or profile_id < 0:
            raise ValueError(
                f"Invalid profile ID for account '{account}': {profile_id}. "
                "Profile IDs must be non-negative integers (0, 10, 11, etc.)"
            )

    return True
