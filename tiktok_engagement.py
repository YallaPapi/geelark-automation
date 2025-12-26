"""
TikTok Engagement Automation - Scroll and like content on FYP.

Usage:
    python tiktok_engagement.py <phone_name> --likes 50 --session-duration 30

Algorithm training approach:
1. Manually like 30-50 target videos first
2. Run this automation - FYP will mostly show similar content
3. TikTok's algorithm does the filtering for you

Alternative: Use --hashtag to engage on specific hashtag pages.
"""
import argparse
import random
import time
from typing import Optional
from device_manager_base import DeviceManager


class TikTokEngagement:
    """Automated TikTok engagement - scroll, watch, like."""

    def __init__(self, driver, device_manager: Optional[DeviceManager] = None):
        self.driver = driver
        self.device_manager = device_manager
        self.likes_given = 0
        self.videos_watched = 0
        self.session_start = time.time()

    def get_screen_elements(self):
        """Dump and parse UI elements."""
        import xml.etree.ElementTree as ET
        page = self.driver.page_source
        root = ET.fromstring(page)
        elements = []
        for elem in root.iter():
            bounds = elem.get('bounds', '[0,0][0,0]')
            try:
                parts = bounds.replace('][', ',').replace('[', '').replace(']', '').split(',')
                x1, y1, x2, y2 = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
            except:
                x1, y1, x2, y2 = 0, 0, 0, 0
            elements.append({
                'text': elem.get('text', ''),
                'desc': elem.get('content-desc', ''),
                'id': elem.get('resource-id', '').split('/')[-1] if elem.get('resource-id') else '',
                'clickable': elem.get('clickable', '') == 'true',
                'bounds': (x1, y1, x2, y2),
            })
        return elements

    def tap(self, x: int, y: int):
        """Tap at coordinates."""
        self.driver.tap([(x, y)])
        time.sleep(0.3)

    def swipe_up(self):
        """Swipe up to next video."""
        width = self.driver.get_window_size()['width']
        height = self.driver.get_window_size()['height']
        start_y = int(height * 0.75)
        end_y = int(height * 0.25)
        x = width // 2
        self.driver.swipe(x, start_y, x, end_y, 400)
        time.sleep(0.5)

    def find_like_button(self, elements) -> Optional[tuple]:
        """Find the like/heart button.

        Known IDs:
        - Geelark: id='f4u' with desc containing 'like'
        - TikTok v43.1.4: id='evz' or similar
        """
        like_ids = ['f4u', 'evz', 'f4s']  # Known like button IDs
        for el in elements:
            # Check by ID first
            if el.get('id') in like_ids:
                bounds = el.get('bounds', (0, 0, 0, 0))
                if bounds[2] > 0:
                    x = (bounds[0] + bounds[2]) // 2
                    y = (bounds[1] + bounds[3]) // 2
                    return (x, y)
            # Check by description
            desc = el.get('desc', '').lower()
            if 'like' in desc and 'double' not in desc:
                bounds = el.get('bounds', (0, 0, 0, 0))
                if bounds[2] > 0:
                    x = (bounds[0] + bounds[2]) // 2
                    y = (bounds[1] + bounds[3]) // 2
                    return (x, y)
        return None

    def is_video_liked(self, elements) -> bool:
        """Check if current video is already liked.

        TikTok changes like button description when liked:
        - Unliked: "Like video" or just "Like"
        - Liked: "Liked" or "Unlike"
        """
        for el in elements:
            el_id = el.get('id', '')
            desc = el.get('desc', '').lower()
            if el_id in ['f4u', 'evz', 'f4s'] or 'like' in desc:
                if 'liked' in desc or 'unlike' in desc:
                    return True
        return False

    def double_tap_to_like(self):
        """Double-tap center of screen to like (alternative method)."""
        width = self.driver.get_window_size()['width']
        height = self.driver.get_window_size()['height']
        x = width // 2
        y = height // 2
        self.driver.tap([(x, y)])
        time.sleep(0.1)
        self.driver.tap([(x, y)])
        time.sleep(0.3)

    def watch_video(self, min_seconds: float = 3.0, max_seconds: float = 15.0):
        """Watch video for random duration.

        Watching longer = more "engaged" signal to algorithm.
        """
        duration = random.uniform(min_seconds, max_seconds)
        print(f"  Watching for {duration:.1f}s...")
        time.sleep(duration)
        self.videos_watched += 1

    def maybe_like(self, probability: float = 0.7) -> bool:
        """Randomly decide whether to like based on probability.

        Args:
            probability: 0.0-1.0 chance of liking

        Returns:
            True if liked, False if skipped
        """
        if random.random() > probability:
            print("  Skipping like (random)")
            return False

        elements = self.get_screen_elements()

        # Check if already liked
        if self.is_video_liked(elements):
            print("  Already liked")
            return False

        # Try button tap first
        like_pos = self.find_like_button(elements)
        if like_pos:
            print(f"  Liking via button at {like_pos}")
            self.tap(like_pos[0], like_pos[1])
            self.likes_given += 1
            return True

        # Fallback to double-tap
        print("  Liking via double-tap")
        self.double_tap_to_like()
        self.likes_given += 1
        return True

    def run_session(self, target_likes: int = 50, session_minutes: int = 30, like_probability: float = 0.7):
        """Run engagement session.

        Args:
            target_likes: Stop after this many likes
            session_minutes: Max session duration
            like_probability: Chance of liking each video
        """
        print(f"\n=== TikTok Engagement Session ===")
        print(f"Target: {target_likes} likes in {session_minutes} minutes")
        print(f"Like probability: {like_probability*100:.0f}%")
        print()

        max_time = session_minutes * 60

        while self.likes_given < target_likes:
            elapsed = time.time() - self.session_start
            if elapsed > max_time:
                print(f"\nSession time limit reached ({session_minutes} min)")
                break

            print(f"[Video {self.videos_watched + 1}] (Likes: {self.likes_given}/{target_likes})")

            # Watch video
            self.watch_video()

            # Maybe like
            self.maybe_like(like_probability)

            # Random pause before scrolling
            time.sleep(random.uniform(0.5, 2.0))

            # Scroll to next video
            print("  Scrolling to next...")
            self.swipe_up()
            time.sleep(random.uniform(1.0, 2.5))

        print(f"\n=== Session Complete ===")
        print(f"Videos watched: {self.videos_watched}")
        print(f"Likes given: {self.likes_given}")
        print(f"Duration: {(time.time() - self.session_start)/60:.1f} minutes")


def main():
    parser = argparse.ArgumentParser(description='TikTok Engagement Automation')
    parser.add_argument('phone_name', help='Phone/account name')
    parser.add_argument('--likes', type=int, default=50, help='Target number of likes')
    parser.add_argument('--duration', type=int, default=30, help='Session duration in minutes')
    parser.add_argument('--probability', type=float, default=0.7, help='Like probability (0.0-1.0)')
    parser.add_argument('--device', choices=['geelark', 'grapheneos'], default='geelark',
                       help='Device type')
    parser.add_argument('--appium-url', default='http://127.0.0.1:4723',
                       help='Appium server URL')
    args = parser.parse_args()

    print(f"[DEVICE] {args.device}")
    print(f"Looking for phone: {args.phone_name}")

    # Create device manager and connect
    if args.device == 'grapheneos':
        from grapheneos_device_manager import GrapheneOSDeviceManager
        from grapheneos_config import PROFILE_MAPPING, DEVICE_SERIAL
        device_manager = GrapheneOSDeviceManager(
            serial=DEVICE_SERIAL,
            profile_mapping=PROFILE_MAPPING
        )
        device_manager.ensure_connected(args.phone_name)

        from appium import webdriver
        caps = device_manager.get_appium_caps()
        caps['appium:appPackage'] = 'com.zhiliaoapp.musically'
        caps['appium:appActivity'] = 'com.ss.android.ugc.aweme.splash.SplashActivity'
        caps['appium:noReset'] = True
        driver = webdriver.Remote(args.appium_url, caps)
    else:
        from device_connection import DeviceConnectionManager
        conn = DeviceConnectionManager(args.phone_name, appium_url=args.appium_url)
        conn.connect()
        driver = conn.driver
        device_manager = None

    print("Connected!\n")

    try:
        engagement = TikTokEngagement(driver, device_manager)
        engagement.run_session(
            target_likes=args.likes,
            session_minutes=args.duration,
            like_probability=args.probability
        )
    finally:
        driver.quit()


if __name__ == '__main__':
    main()
