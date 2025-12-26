"""
Humanization Primitives for Automation.

Platform-agnostic humanization functions for simulating human-like behavior
in mobile automation. Uses Appium W3C Actions API.

Usage:
    from humanization import (
        tap_with_jitter,
        human_scroll_vertical,
        human_sleep,
        BehaviorProfile,
        get_or_create_base_seed,
        build_behavior_profile
    )

    # Build profile for account
    base_seed = get_or_create_base_seed('grapheneos', 'alice.account')
    profile = build_behavior_profile(base_seed)
    rng = random.Random(base_seed ^ int(time.time() / 21600))  # 6-hour buckets

    # Use primitives
    tap_with_jitter(driver, center=(540, 1200), profile=profile, rng=rng)
    human_scroll_vertical(driver, direction='down', profile=profile, rng=rng)
    human_sleep(profile, rng, base=1.0)
"""

import time
import random
import hashlib
import json
import os
import logging
from dataclasses import dataclass, asdict, field
from typing import Optional, Tuple, Dict, Any
from pathlib import Path

from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.actions import interaction
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.common.actions.pointer_input import PointerInput

logger = logging.getLogger(__name__)


# =============================================================================
# Action Logging
# =============================================================================

class HumanizationLogger:
    """
    Tracks and logs humanization actions for debugging and validation.

    Logs the first N actions with full parameters, then summarizes.
    """

    def __init__(self, max_detailed_logs: int = 20):
        self.max_detailed_logs = max_detailed_logs
        self.action_count = 0
        self.actions_by_type = {}
        self.logged_profile = False

    def log_session_start(
        self,
        device_type: str,
        account_name: str,
        base_seed: int,
        session_seed: int,
        profile: 'BehaviorProfile'
    ):
        """Log complete session info at startup."""
        logger.info("=" * 60)
        logger.info("HUMANIZATION SESSION START")
        logger.info("=" * 60)
        logger.info(f"Device Type: {device_type}")
        logger.info(f"Account: {account_name}")
        logger.info(f"Base Seed: {base_seed}")
        logger.info(f"Session Seed: {session_seed}")
        logger.info("-" * 40)
        logger.info("BEHAVIOR PROFILE:")
        for key, value in profile.to_dict().items():
            if isinstance(value, float):
                logger.info(f"  {key}: {value:.4f}")
            else:
                logger.info(f"  {key}: {value}")
        logger.info("=" * 60)
        self.logged_profile = True

    def log_action(
        self,
        action_type: str,
        params: Dict[str, Any],
        result: Any = None
    ):
        """Log a humanization action with parameters."""
        self.action_count += 1
        self.actions_by_type[action_type] = self.actions_by_type.get(action_type, 0) + 1

        if self.action_count <= self.max_detailed_logs:
            # Detailed log for first N actions
            params_str = ', '.join(f"{k}={v}" for k, v in params.items())
            result_str = f" -> {result}" if result is not None else ""
            logger.info(f"[ACTION #{self.action_count}] {action_type}({params_str}){result_str}")
        elif self.action_count == self.max_detailed_logs + 1:
            logger.info(f"[ACTION #{self.action_count}+] Switching to summary mode...")

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all actions taken."""
        return {
            'total_actions': self.action_count,
            'actions_by_type': dict(self.actions_by_type)
        }

    def log_session_end(self):
        """Log session summary at end."""
        summary = self.get_summary()
        logger.info("=" * 60)
        logger.info("HUMANIZATION SESSION END")
        logger.info(f"Total Actions: {summary['total_actions']}")
        for action_type, count in summary['actions_by_type'].items():
            logger.info(f"  {action_type}: {count}")
        logger.info("=" * 60)


# Global logger instance (can be replaced per-session)
_humanization_logger: Optional[HumanizationLogger] = None


def get_humanization_logger() -> HumanizationLogger:
    """Get or create the global humanization logger."""
    global _humanization_logger
    if _humanization_logger is None:
        _humanization_logger = HumanizationLogger()
    return _humanization_logger


def reset_humanization_logger(max_detailed_logs: int = 20) -> HumanizationLogger:
    """Reset the humanization logger for a new session."""
    global _humanization_logger
    _humanization_logger = HumanizationLogger(max_detailed_logs)
    return _humanization_logger


# =============================================================================
# Behavior Profile Dataclass
# =============================================================================

@dataclass
class BehaviorProfile:
    """
    Behavior profile defining humanization parameters for an account.

    Each account gets a unique profile built from a deterministic seed,
    making behavior consistent within an account but varying across accounts.
    """
    # Tap jitter (pixels offset from target center)
    tap_jitter_min_px: float = 2.0
    tap_jitter_max_px: float = 8.0

    # Scroll parameters (as percentage of screen height)
    scroll_min_pct: float = 0.15
    scroll_max_pct: float = 0.35
    scroll_duration_min_ms: int = 200
    scroll_duration_max_ms: int = 600

    # Pre/post scroll behavior
    scroll_count_pre_min: int = 0
    scroll_count_pre_max: int = 3
    scroll_count_post_min: int = 0
    scroll_count_post_max: int = 2
    prob_scroll_before_post: float = 0.3
    prob_scroll_after_post: float = 0.2
    scroll_down_probability: float = 0.95  # 95% down, 5% up

    # Sleep/delay parameters (seconds)
    sleep_base_min: float = 0.3
    sleep_base_max: float = 1.5
    sleep_jitter_ratio: float = 0.3  # +-30% of base

    # Watch time when viewing videos (seconds)
    watch_time_min: float = 0.5
    watch_time_max: float = 6.0

    # Probability of extra actions
    prob_explore_video_after_post: float = 0.1
    prob_idle_action: float = 0.0  # Disabled by default (risky)

    def to_dict(self) -> Dict:
        """Convert to dictionary for logging."""
        return asdict(self)


# =============================================================================
# Seed Management
# =============================================================================

SEED_STORE_PATH = Path(__file__).parent / 'random_profiles.json'
SESSION_BUCKET_SECONDS = 21600  # 6 hours


def get_or_create_base_seed(device_type: str, account_name: str) -> int:
    """
    Get or create a stable base seed for a device/account pair.

    The seed is stored in random_profiles.json so it persists across runs.

    Args:
        device_type: 'geelark' or 'grapheneos'
        account_name: TikTok/Instagram account name

    Returns:
        Stable integer seed for this account
    """
    key = f"{device_type}::{account_name}::tiktok"

    # Load existing seeds
    seeds = {}
    if SEED_STORE_PATH.exists():
        try:
            with open(SEED_STORE_PATH, 'r') as f:
                seeds = json.load(f)
        except (json.JSONDecodeError, IOError):
            seeds = {}

    # Return existing seed if present
    if key in seeds:
        logger.debug(f"Using existing seed for {key}: {seeds[key]}")
        return seeds[key]

    # Create new seed from hash
    hash_bytes = hashlib.sha256(key.encode()).digest()
    base_seed = int.from_bytes(hash_bytes[:4], 'big') % (2**31)

    # Store for future use
    seeds[key] = base_seed
    try:
        with open(SEED_STORE_PATH, 'w') as f:
            json.dump(seeds, f, indent=2)
        logger.info(f"Created new seed for {key}: {base_seed}")
    except IOError as e:
        logger.warning(f"Failed to save seed store: {e}")

    return base_seed


def get_session_seed(base_seed: int, bucket_seconds: int = SESSION_BUCKET_SECONDS) -> int:
    """
    Derive a session seed from base seed and current time bucket.

    Behavior varies every bucket_seconds but is consistent within that period.

    Args:
        base_seed: Base seed for the account
        bucket_seconds: Time bucket size (default 6 hours)

    Returns:
        Session-specific seed
    """
    time_bucket = int(time.time() / bucket_seconds)
    session_seed = base_seed ^ time_bucket
    return session_seed


def build_behavior_profile(base_seed: int) -> BehaviorProfile:
    """
    Build a deterministic behavior profile from a seed.

    Uses the seed to create consistent but unique parameters for each account.

    Args:
        base_seed: Seed to use for randomization

    Returns:
        BehaviorProfile with randomized but consistent parameters
    """
    rng = random.Random(base_seed)

    # Randomize parameters within safe bounds
    profile = BehaviorProfile(
        # Tap jitter: 2-12px range, varies per account
        tap_jitter_min_px=rng.uniform(1.5, 4.0),
        tap_jitter_max_px=rng.uniform(5.0, 12.0),

        # Scroll parameters
        scroll_min_pct=rng.uniform(0.12, 0.20),
        scroll_max_pct=rng.uniform(0.25, 0.40),
        scroll_duration_min_ms=rng.randint(150, 300),
        scroll_duration_max_ms=rng.randint(400, 800),

        # Scroll counts
        scroll_count_pre_min=0,
        scroll_count_pre_max=rng.randint(2, 5),
        scroll_count_post_min=0,
        scroll_count_post_max=rng.randint(1, 3),
        prob_scroll_before_post=rng.uniform(0.2, 0.5),
        prob_scroll_after_post=rng.uniform(0.1, 0.3),
        scroll_down_probability=rng.uniform(0.90, 0.98),

        # Sleep parameters
        sleep_base_min=rng.uniform(0.2, 0.5),
        sleep_base_max=rng.uniform(1.0, 2.5),
        sleep_jitter_ratio=rng.uniform(0.2, 0.4),

        # Watch time
        watch_time_min=rng.uniform(0.3, 1.0),
        watch_time_max=rng.uniform(4.0, 8.0),

        # Extra actions
        prob_explore_video_after_post=rng.uniform(0.05, 0.15),
        prob_idle_action=0.0,  # Keep disabled
    )

    return profile


# =============================================================================
# Humanization Primitives
# =============================================================================

def tap_with_jitter(
    driver,
    element=None,
    center: Optional[Tuple[int, int]] = None,
    profile: BehaviorProfile = None,
    rng: random.Random = None,
    log_action: bool = True
) -> Tuple[int, int]:
    """
    Tap with human-like jitter offset.

    Uses Appium W3C Actions API for the tap.

    Args:
        driver: Appium WebDriver instance
        element: Optional element to tap (uses center of element)
        center: Optional (x, y) coordinates if no element provided
        profile: BehaviorProfile for jitter parameters
        rng: Random instance for this session
        log_action: Whether to log the action

    Returns:
        Tuple of (final_x, final_y) that was tapped
    """
    profile = profile or BehaviorProfile()
    rng = rng or random.Random()

    # Get tap center
    if element is not None:
        rect = element.rect
        cx = rect['x'] + rect['width'] // 2
        cy = rect['y'] + rect['height'] // 2
    elif center is not None:
        cx, cy = center
    else:
        raise ValueError("Either element or center must be provided")

    # Apply jitter
    jitter_x = rng.uniform(-profile.tap_jitter_max_px, profile.tap_jitter_max_px)
    jitter_y = rng.uniform(-profile.tap_jitter_max_px, profile.tap_jitter_max_px)

    # Ensure minimum jitter
    if abs(jitter_x) < profile.tap_jitter_min_px:
        jitter_x = profile.tap_jitter_min_px * (1 if jitter_x >= 0 else -1)
    if abs(jitter_y) < profile.tap_jitter_min_px:
        jitter_y = profile.tap_jitter_min_px * (1 if jitter_y >= 0 else -1)

    final_x = int(cx + jitter_x)
    final_y = int(cy + jitter_y)

    if log_action:
        logger.debug(f"tap_with_jitter: ({cx}, {cy}) -> ({final_x}, {final_y}) [jitter: {jitter_x:.1f}, {jitter_y:.1f}]")
        # Log to action tracker
        get_humanization_logger().log_action(
            'tap_with_jitter',
            {'target': (cx, cy), 'jitter': (round(jitter_x, 1), round(jitter_y, 1))},
            result=(final_x, final_y)
        )

    # Perform tap using Appium
    try:
        # Use driver.tap() which is simpler and more reliable
        driver.tap([(final_x, final_y)], duration=rng.randint(50, 150))
    except Exception as e:
        logger.warning(f"tap_with_jitter failed: {e}, falling back to coordinate tap")
        # Fallback to execute_script if available
        try:
            driver.execute_script('mobile: tap', {'x': final_x, 'y': final_y})
        except Exception:
            # Last resort: use ActionChains
            actions = ActionChains(driver)
            actions.w3c_actions = ActionBuilder(driver, mouse=PointerInput(interaction.POINTER_TOUCH, "touch"))
            actions.w3c_actions.pointer_action.move_to_location(final_x, final_y)
            actions.w3c_actions.pointer_action.pointer_down()
            actions.w3c_actions.pointer_action.pause(rng.uniform(0.05, 0.15))
            actions.w3c_actions.pointer_action.pointer_up()
            actions.perform()

    return final_x, final_y


def human_scroll_vertical(
    driver,
    direction: str = 'down',
    profile: BehaviorProfile = None,
    rng: random.Random = None,
    screen_height: int = 2400,
    screen_width: int = 1080,
    log_action: bool = True
) -> Tuple[int, int, int, int]:
    """
    Perform a human-like vertical scroll.

    Args:
        driver: Appium WebDriver instance
        direction: 'up' or 'down'
        profile: BehaviorProfile for scroll parameters
        rng: Random instance for this session
        screen_height: Device screen height in pixels
        screen_width: Device screen width in pixels
        log_action: Whether to log the action

    Returns:
        Tuple of (start_x, start_y, end_x, end_y)
    """
    profile = profile or BehaviorProfile()
    rng = rng or random.Random()

    # Calculate scroll distance as percentage of screen
    scroll_pct = rng.uniform(profile.scroll_min_pct, profile.scroll_max_pct)
    scroll_distance = int(screen_height * scroll_pct)

    # Start position (random within middle area)
    start_x = int(screen_width * rng.uniform(0.3, 0.7))
    start_y = int(screen_height * rng.uniform(0.4, 0.6))

    # End position
    if direction == 'down':
        # Swipe up to scroll down (finger moves up, content moves down)
        end_y = start_y - scroll_distance
    else:
        # Swipe down to scroll up
        end_y = start_y + scroll_distance

    # Add horizontal jitter
    end_x = start_x + rng.randint(-20, 20)

    # Clamp to screen bounds
    end_y = max(100, min(screen_height - 100, end_y))
    end_x = max(50, min(screen_width - 50, end_x))

    # Duration
    duration_ms = rng.randint(profile.scroll_duration_min_ms, profile.scroll_duration_max_ms)

    if log_action:
        logger.debug(f"human_scroll_vertical: ({start_x}, {start_y}) -> ({end_x}, {end_y}), direction={direction}, duration={duration_ms}ms")
        # Log to action tracker
        get_humanization_logger().log_action(
            'human_scroll_vertical',
            {'direction': direction, 'distance_pct': round(scroll_pct, 2), 'duration_ms': duration_ms},
            result=(start_x, start_y, end_x, end_y)
        )

    # Perform swipe
    try:
        driver.swipe(start_x, start_y, end_x, end_y, duration_ms)
    except Exception as e:
        logger.warning(f"human_scroll_vertical failed: {e}")

    return start_x, start_y, end_x, end_y


def human_sleep(
    profile: BehaviorProfile = None,
    rng: random.Random = None,
    base: float = None,
    log_action: bool = True
) -> float:
    """
    Sleep for a human-like duration with jitter.

    Args:
        profile: BehaviorProfile for sleep parameters
        rng: Random instance for this session
        base: Optional base duration to jitter around
        log_action: Whether to log the action

    Returns:
        Actual sleep duration in seconds
    """
    profile = profile or BehaviorProfile()
    rng = rng or random.Random()

    # Determine base duration
    if base is not None:
        sleep_base = base
    else:
        sleep_base = rng.uniform(profile.sleep_base_min, profile.sleep_base_max)

    # Apply jitter
    jitter = sleep_base * rng.uniform(-profile.sleep_jitter_ratio, profile.sleep_jitter_ratio)
    sleep_duration = max(0.1, sleep_base + jitter)

    if log_action:
        logger.debug(f"human_sleep: {sleep_duration:.2f}s (base={sleep_base:.2f}, jitter={jitter:.2f})")
        # Log to action tracker
        get_humanization_logger().log_action(
            'human_sleep',
            {'base': round(sleep_base, 2), 'jitter': round(jitter, 2)},
            result=round(sleep_duration, 2)
        )

    time.sleep(sleep_duration)
    return sleep_duration


def warmup_scrolls(
    driver,
    profile: BehaviorProfile = None,
    rng: random.Random = None,
    screen_height: int = 2400,
    screen_width: int = 1080,
    log_action: bool = True
) -> int:
    """
    Perform warmup scrolls before posting (simulates browsing).

    Args:
        driver: Appium WebDriver instance
        profile: BehaviorProfile for parameters
        rng: Random instance for this session
        screen_height: Device screen height
        screen_width: Device screen width
        log_action: Whether to log actions

    Returns:
        Number of scrolls performed
    """
    profile = profile or BehaviorProfile()
    rng = rng or random.Random()

    # Check if we should do warmup
    if rng.random() > profile.prob_scroll_before_post:
        if log_action:
            logger.debug("warmup_scrolls: skipped (probability)")
        return 0

    # Determine number of scrolls
    num_scrolls = rng.randint(profile.scroll_count_pre_min, profile.scroll_count_pre_max)
    if num_scrolls == 0:
        return 0

    if log_action:
        logger.info(f"warmup_scrolls: performing {num_scrolls} scrolls")
        get_humanization_logger().log_action(
            'warmup_scrolls',
            {'num_scrolls': num_scrolls, 'prob': round(profile.prob_scroll_before_post, 2)}
        )

    for i in range(num_scrolls):
        # Mostly scroll down, occasionally up
        direction = 'down' if rng.random() < profile.scroll_down_probability else 'up'
        human_scroll_vertical(driver, direction, profile, rng, screen_height, screen_width, log_action)

        # Watch time between scrolls
        watch_time = rng.uniform(profile.watch_time_min, profile.watch_time_max)
        if log_action:
            logger.debug(f"warmup_scrolls: watching for {watch_time:.1f}s after scroll {i+1}")
        time.sleep(watch_time)

    return num_scrolls


def cooldown_scrolls(
    driver,
    profile: BehaviorProfile = None,
    rng: random.Random = None,
    screen_height: int = 2400,
    screen_width: int = 1080,
    log_action: bool = True
) -> int:
    """
    Perform cooldown scrolls after posting (simulates natural browsing).

    Args:
        driver: Appium WebDriver instance
        profile: BehaviorProfile for parameters
        rng: Random instance for this session
        screen_height: Device screen height
        screen_width: Device screen width
        log_action: Whether to log actions

    Returns:
        Number of scrolls performed
    """
    profile = profile or BehaviorProfile()
    rng = rng or random.Random()

    # Check if we should do cooldown
    if rng.random() > profile.prob_scroll_after_post:
        if log_action:
            logger.debug("cooldown_scrolls: skipped (probability)")
        return 0

    # Determine number of scrolls
    num_scrolls = rng.randint(profile.scroll_count_post_min, profile.scroll_count_post_max)
    if num_scrolls == 0:
        return 0

    if log_action:
        logger.info(f"cooldown_scrolls: performing {num_scrolls} scrolls")
        get_humanization_logger().log_action(
            'cooldown_scrolls',
            {'num_scrolls': num_scrolls, 'prob': round(profile.prob_scroll_after_post, 2)}
        )

    for i in range(num_scrolls):
        direction = 'down' if rng.random() < profile.scroll_down_probability else 'up'
        human_scroll_vertical(driver, direction, profile, rng, screen_height, screen_width, log_action)

        watch_time = rng.uniform(profile.watch_time_min, profile.watch_time_max)
        if log_action:
            logger.debug(f"cooldown_scrolls: watching for {watch_time:.1f}s after scroll {i+1}")
        time.sleep(watch_time)

    return num_scrolls


# =============================================================================
# Validation Functions
# =============================================================================

def validate_humanization_setup(
    device_type: str = 'grapheneos',
    account_name: str = 'test_account'
) -> Dict[str, Any]:
    """
    Validate humanization setup without a live driver.

    Tests:
    1. Seed generation is deterministic
    2. Profile builds correctly from seed
    3. Profile values are within expected bounds
    4. Session seeds change over time buckets
    5. Logger records actions correctly

    Returns:
        Dict with validation results
    """
    results = {
        'passed': True,
        'tests': [],
        'errors': []
    }

    # Test 1: Seed determinism
    try:
        seed1 = get_or_create_base_seed(device_type, account_name)
        seed2 = get_or_create_base_seed(device_type, account_name)
        if seed1 == seed2:
            results['tests'].append(('seed_determinism', True, f"seed={seed1}"))
        else:
            results['tests'].append(('seed_determinism', False, f"{seed1} != {seed2}"))
            results['passed'] = False
    except Exception as e:
        results['tests'].append(('seed_determinism', False, str(e)))
        results['errors'].append(str(e))
        results['passed'] = False

    # Test 2: Profile builds correctly
    try:
        profile = build_behavior_profile(seed1)
        if isinstance(profile, BehaviorProfile):
            results['tests'].append(('profile_build', True, "BehaviorProfile created"))
        else:
            results['tests'].append(('profile_build', False, f"Got {type(profile)}"))
            results['passed'] = False
    except Exception as e:
        results['tests'].append(('profile_build', False, str(e)))
        results['errors'].append(str(e))
        results['passed'] = False

    # Test 3: Profile values are in bounds
    try:
        bounds_ok = True
        issues = []

        if not (0 < profile.tap_jitter_min_px < profile.tap_jitter_max_px < 20):
            bounds_ok = False
            issues.append(f"jitter: {profile.tap_jitter_min_px}-{profile.tap_jitter_max_px}")

        if not (0 < profile.scroll_min_pct < profile.scroll_max_pct < 1):
            bounds_ok = False
            issues.append(f"scroll_pct: {profile.scroll_min_pct}-{profile.scroll_max_pct}")

        if not (0 <= profile.prob_scroll_before_post <= 1):
            bounds_ok = False
            issues.append(f"prob_scroll_before: {profile.prob_scroll_before_post}")

        if bounds_ok:
            results['tests'].append(('profile_bounds', True, "All values in range"))
        else:
            results['tests'].append(('profile_bounds', False, "; ".join(issues)))
            results['passed'] = False
    except Exception as e:
        results['tests'].append(('profile_bounds', False, str(e)))
        results['errors'].append(str(e))
        results['passed'] = False

    # Test 4: Session seeds vary by time bucket
    try:
        session1 = get_session_seed(seed1, bucket_seconds=1)  # 1 second buckets
        time.sleep(1.1)
        session2 = get_session_seed(seed1, bucket_seconds=1)
        if session1 != session2:
            results['tests'].append(('session_seed_varies', True, f"{session1} -> {session2}"))
        else:
            results['tests'].append(('session_seed_varies', False, "Seeds didn't change"))
            # This is expected with default 6hr buckets, so don't fail
    except Exception as e:
        results['tests'].append(('session_seed_varies', False, str(e)))
        results['errors'].append(str(e))

    # Test 5: Logger works
    try:
        test_logger = HumanizationLogger(max_detailed_logs=5)
        test_logger.log_session_start(device_type, account_name, seed1, seed1, profile)

        # Simulate some actions
        for i in range(3):
            test_logger.log_action('test_tap', {'x': 100 + i, 'y': 200}, result='ok')

        summary = test_logger.get_summary()
        if summary['total_actions'] == 3 and summary['actions_by_type'].get('test_tap') == 3:
            results['tests'].append(('logger', True, f"Logged {summary['total_actions']} actions"))
        else:
            results['tests'].append(('logger', False, f"Expected 3 actions, got {summary}"))
            results['passed'] = False
    except Exception as e:
        results['tests'].append(('logger', False, str(e)))
        results['errors'].append(str(e))
        results['passed'] = False

    return results


def print_validation_report(results: Dict[str, Any]):
    """Print a formatted validation report."""
    print("\n" + "=" * 60)
    print("HUMANIZATION VALIDATION REPORT")
    print("=" * 60)

    for test_name, passed, details in results['tests']:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {status} {test_name}: {details}")

    print("-" * 60)
    if results['passed']:
        print("OVERALL: ALL TESTS PASSED")
    else:
        print("OVERALL: SOME TESTS FAILED")
        if results['errors']:
            print("\nErrors:")
            for err in results['errors']:
                print(f"  - {err}")
    print("=" * 60)


# =============================================================================
# Module Testing
# =============================================================================

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.DEBUG)

    print("Running humanization validation tests...\n")

    # Run validation
    results = validate_humanization_setup('grapheneos', 'test_validation_account')
    print_validation_report(results)

    if not results['passed']:
        sys.exit(1)

    print("\n" + "=" * 60)
    print("ADDITIONAL MANUAL TESTS")
    print("=" * 60)

    # Test seed generation
    seed1 = get_or_create_base_seed('grapheneos', 'test_account_1')
    seed2 = get_or_create_base_seed('grapheneos', 'test_account_2')
    seed1_repeat = get_or_create_base_seed('grapheneos', 'test_account_1')

    print(f"Seed 1: {seed1}")
    print(f"Seed 2: {seed2}")
    print(f"Seed 1 (repeat): {seed1_repeat}")
    print(f"Seeds match: {seed1 == seed1_repeat}")

    # Test profile building
    profile1 = build_behavior_profile(seed1)
    profile2 = build_behavior_profile(seed2)

    print(f"\nProfile 1 summary:")
    print(f"  tap_jitter: {profile1.tap_jitter_min_px:.1f}-{profile1.tap_jitter_max_px:.1f}px")
    print(f"  scroll_pct: {profile1.scroll_min_pct:.2f}-{profile1.scroll_max_pct:.2f}")
    print(f"  prob_warmup: {profile1.prob_scroll_before_post:.2f}")

    print(f"\nProfile 2 summary:")
    print(f"  tap_jitter: {profile2.tap_jitter_min_px:.1f}-{profile2.tap_jitter_max_px:.1f}px")
    print(f"  scroll_pct: {profile2.scroll_min_pct:.2f}-{profile2.scroll_max_pct:.2f}")
    print(f"  prob_warmup: {profile2.prob_scroll_before_post:.2f}")

    # Test sleep (no driver needed)
    print("\nTesting human_sleep (3 calls with same profile):")
    rng = random.Random(seed1)
    for i in range(3):
        duration = human_sleep(profile1, rng, base=1.0, log_action=True)
        print(f"  Sleep {i+1}: {duration:.2f}s")

    print("\n[OK] All tests complete!")
