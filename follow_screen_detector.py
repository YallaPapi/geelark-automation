"""
FollowScreenDetector - Deterministic screen type detection for Instagram following.

Completely separate from posting screen_detector.py to avoid any risk of
breaking the working posting system.

Based on flow analysis from: flow_analysis/LockedVaultDuster_20251223_174939.jsonl
"""
from enum import Enum, auto
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass


class FollowScreenType(Enum):
    """Known Instagram screen types during follow flow."""
    # Main follow flow screens
    HOME_FEED = auto()          # Home feed with stories and nav bar
    EXPLORE_PAGE = auto()       # Explore grid with "Search with Meta AI" bar
    SEARCH_INPUT = auto()       # Search input with recent searches
    SEARCH_RESULTS = auto()     # Search results showing user matches
    TARGET_PROFILE = auto()     # Target user's profile with Follow button

    # Success states
    FOLLOW_SUCCESS = auto()     # Follow button changed to "Following" or "Requested"

    # Error/blocking states
    ACTION_BLOCKED = auto()     # "Action Blocked" popup
    LOGIN_REQUIRED = auto()     # Logged out / login required
    CAPTCHA = auto()            # Human verification required

    # Popups that may appear
    POPUP_DISMISSIBLE = auto()  # "Not now", "Skip" popups
    NOTIFICATIONS_POPUP = auto() # Turn on notifications prompt
    ONBOARDING_POPUP = auto()   # "We've simplified" navigation tutorial

    # Additional screens found in flow analysis (Dec 2024)
    REELS_SCREEN = auto()       # Viewing reels/clips tab
    ABOUT_ACCOUNT_PAGE = auto() # Account info page with "Date joined", etc.

    # Fallback
    UNKNOWN = auto()


@dataclass
class FollowDetectionResult:
    """Result of screen detection with confidence."""
    screen_type: FollowScreenType
    confidence: float  # 0.0 to 1.0
    matched_rule: str  # Which rule matched
    key_elements: List[str]  # Elements that triggered the match
    target_element_index: Optional[int] = None  # Index of element to interact with


class FollowScreenDetector:
    """Detects Instagram screen types for follow flow."""

    CONFIDENCE_THRESHOLD = 0.7

    def __init__(self):
        """Initialize detector with detection rules."""
        # Detection rules in priority order
        self.rules = [
            # High priority: blocking states
            ('ACTION_BLOCKED', self._detect_action_blocked),
            ('LOGIN_REQUIRED', self._detect_login_required),
            ('CAPTCHA', self._detect_captcha),

            # Popups
            ('ONBOARDING_POPUP', self._detect_onboarding_popup),
            ('NOTIFICATIONS_POPUP', self._detect_notifications_popup),
            ('POPUP_DISMISSIBLE', self._detect_dismissible_popup),

            # Success state (check before profile to catch "Following" state)
            ('FOLLOW_SUCCESS', self._detect_follow_success),

            # Info pages (check before profile)
            ('ABOUT_ACCOUNT_PAGE', self._detect_about_account),

            # Main flow screens (order matters)
            ('TARGET_PROFILE', self._detect_target_profile),
            ('SEARCH_RESULTS', self._detect_search_results),
            ('SEARCH_INPUT', self._detect_search_input),
            ('REELS_SCREEN', self._detect_reels_screen),
            ('EXPLORE_PAGE', self._detect_explore_page),
            ('HOME_FEED', self._detect_home_feed),
        ]

    def detect(self, elements: List[Dict], target_username: str = "") -> FollowDetectionResult:
        """Detect screen type from UI elements.

        Args:
            elements: List of UI element dicts from dump_ui()
            target_username: Target username we're trying to follow (for matching in search results)

        Returns:
            FollowDetectionResult with screen type and confidence
        """
        if not elements:
            return FollowDetectionResult(
                screen_type=FollowScreenType.UNKNOWN,
                confidence=0.0,
                matched_rule='empty_elements',
                key_elements=[]
            )

        # Extract text/desc for matching
        texts = self._extract_texts(elements)
        descs = self._extract_descs(elements)
        ids = self._extract_ids(elements)
        all_text = ' '.join(texts + descs).lower()
        all_ids = ' '.join(ids).lower()

        # Try each rule
        for rule_name, detector_fn in self.rules:
            result = detector_fn(elements, texts, descs, ids, all_text, all_ids, target_username)

            if result[0] >= self.CONFIDENCE_THRESHOLD:
                return FollowDetectionResult(
                    screen_type=FollowScreenType[rule_name],
                    confidence=result[0],
                    matched_rule=rule_name,
                    key_elements=result[1],
                    target_element_index=result[2] if len(result) > 2 else None
                )

        return FollowDetectionResult(
            screen_type=FollowScreenType.UNKNOWN,
            confidence=0.0,
            matched_rule='none',
            key_elements=[]
        )

    def _extract_texts(self, elements: List[Dict]) -> List[str]:
        return [e.get('text', '').lower().strip() for e in elements if e.get('text')]

    def _extract_descs(self, elements: List[Dict]) -> List[str]:
        return [e.get('desc', '').lower().strip() for e in elements if e.get('desc')]

    def _extract_ids(self, elements: List[Dict]) -> List[str]:
        return [e.get('id', '').lower().strip() for e in elements if e.get('id')]

    def _has_element_id(self, elements: List[Dict], element_id: str) -> bool:
        return any(e.get('id', '') == element_id for e in elements)

    def _find_element_index_by_id(self, elements: List[Dict], element_id: str) -> Optional[int]:
        for i, e in enumerate(elements):
            if e.get('id', '') == element_id:
                return i
        return None

    def _find_element_index_by_text(self, elements: List[Dict], text: str, exact: bool = False) -> Optional[int]:
        text_lower = text.lower()
        for i, e in enumerate(elements):
            el_text = e.get('text', '').lower()
            if exact:
                if el_text == text_lower:
                    return i
            else:
                if text_lower in el_text:
                    return i
        return None

    def _find_element_index_by_desc(self, elements: List[Dict], desc: str) -> Optional[int]:
        desc_lower = desc.lower()
        for i, e in enumerate(elements):
            if desc_lower in e.get('desc', '').lower():
                return i
        return None

    # ==================== Detection Rules ====================

    def _detect_reels_screen(self, elements, texts, descs, ids, all_text, all_ids, target) -> Tuple:
        """Detect reels/clips viewing screen.

        Key IDs from flow analysis:
        - clips_media_component, clips_video_container
        - clips_author_info_component, clips_author_username
        - like_button, comment_button
        """
        has_clips_media = 'clips_media_component' in all_ids or 'clips_video_container' in all_ids
        has_clips_author = 'clips_author_info_component' in all_ids or 'clips_author_username' in all_ids

        if has_clips_media or has_clips_author:
            # Find search tab to navigate away
            search_idx = self._find_element_index_by_id(elements, 'search_tab')
            return (0.9, ['reels_screen'], search_idx)

        return (0.0, [], None)

    def _detect_about_account(self, elements, texts, descs, ids, all_text, all_ids, target) -> Tuple:
        """Detect 'About this account' info page.

        Key markers from flow analysis:
        - Text: 'About this account', 'Date joined', 'Account based in'
        - Has action_bar_button_back for navigation
        """
        markers = ['about this account', 'date joined', 'account based in',
                   'former usernames', 'verified', 'meta verified subscription']
        found = [m for m in markers if m in all_text]

        if len(found) >= 2:
            back_idx = self._find_element_index_by_id(elements, 'action_bar_button_back')
            return (0.95, found, back_idx)
        elif len(found) == 1 and 'date joined' in all_text:
            back_idx = self._find_element_index_by_id(elements, 'action_bar_button_back')
            return (0.85, found, back_idx)

        return (0.0, [], None)

    def _detect_action_blocked(self, elements, texts, descs, ids, all_text, all_ids, target) -> Tuple:
        """Detect action blocked popup."""
        markers = ['action blocked', 'try again later', 'temporarily blocked',
                   'we restrict certain activity']
        found = [m for m in markers if m in all_text]
        if found:
            return (0.95, found, None)
        return (0.0, [], None)

    def _detect_login_required(self, elements, texts, descs, ids, all_text, all_ids, target) -> Tuple:
        """Detect login screen."""
        markers = ['log in', 'sign in', 'create new account', 'log into instagram']
        found = [m for m in markers if m in all_text]
        if len(found) >= 2:
            return (0.95, found, None)
        elif len(found) == 1:
            return (0.75, found, None)
        return (0.0, [], None)

    def _detect_captcha(self, elements, texts, descs, ids, all_text, all_ids, target) -> Tuple:
        """Detect captcha/verification."""
        if "confirm you're human" in all_text or 'security check' in all_text:
            return (0.95, ['captcha'], None)
        return (0.0, [], None)

    def _detect_onboarding_popup(self, elements, texts, descs, ids, all_text, all_ids, target) -> Tuple:
        """Detect onboarding/tutorial popup.

        Key IDs from flow analysis (carlooinspired):
        - igds_headline_body
        - igds_headline_headline
        - igds_headline_primary_action_button ("Got it")
        """
        has_headline = 'igds_headline_headline' in all_ids or 'igds_headline_body' in all_ids
        has_action_button = 'igds_headline_primary_action_button' in all_ids

        # Text-based detection
        has_simplified = "we've simplified" in all_text or 'simplified our navigation' in all_text
        has_got_it = 'got it' in all_text

        if has_headline and has_action_button:
            idx = self._find_element_index_by_id(elements, 'igds_headline_primary_action_button')
            if idx is None:
                idx = self._find_element_index_by_text(elements, 'got it')
            return (0.95, ['onboarding_headline'], idx)

        if has_simplified and has_got_it:
            idx = self._find_element_index_by_text(elements, 'got it')
            return (0.90, ['simplified_navigation'], idx)

        return (0.0, [], None)

    def _detect_notifications_popup(self, elements, texts, descs, ids, all_text, all_ids, target) -> Tuple:
        """Detect notifications prompt."""
        if 'turn on notifications' in all_text or 'enable notifications' in all_text:
            # Find "Not Now" or "Skip" button
            idx = self._find_element_index_by_text(elements, 'not now')
            if idx is None:
                idx = self._find_element_index_by_text(elements, 'skip')
            return (0.9, ['notifications_prompt'], idx)
        return (0.0, [], None)

    def _detect_dismissible_popup(self, elements, texts, descs, ids, all_text, all_ids, target) -> Tuple:
        """Detect dismissible popups.

        IMPORTANT: Exclude search context where 'dismiss' buttons are for clearing search history,
        not for dismissing a popup.
        """
        # FIX: Don't match as popup when we're in search context
        # Search screens have dismiss_button for clearing search history
        has_search_bar = 'action_bar_search_edit_text' in all_ids
        has_search_context = 'row_search_user_container' in all_ids or 'row_search_keyword_title' in all_ids
        has_recent_header = 'recent' in all_text

        if has_search_bar or has_search_context or has_recent_header:
            # This is a search screen, not a popup
            return (0.0, [], None)

        # Only check these specific text markers (not just 'dismiss' which appears in search)
        dismiss_markers = ['not now', 'skip', 'maybe later', 'no thanks']
        found = [m for m in dismiss_markers if m in all_text]

        if found and len(elements) < 25:  # Popups have fewer elements
            idx = self._find_element_index_by_text(elements, found[0])
            return (0.85, found, idx)
        return (0.0, [], None)

    def _detect_follow_success(self, elements, texts, descs, ids, all_text, all_ids, target) -> Tuple:
        """Detect successful follow (Following or Requested button visible)."""
        # Check for "Following" or "Requested" button on profile
        # These indicate the follow was successful

        # Look for profile elements + Following/Requested state
        has_profile_header = 'profile_header_followers_stacked_familiar' in all_ids
        has_action_bar_title = 'action_bar_title' in all_ids

        # Check for Following/Requested text
        has_following = 'following' in texts  # Button says "Following"
        has_requested = 'requested' in texts  # Private account - request sent

        # Must be on a profile AND have the success indicator
        if (has_profile_header or has_action_bar_title) and (has_following or has_requested):
            found = []
            if has_following:
                found.append('following_button')
            if has_requested:
                found.append('requested_button')
            return (0.95, found, None)

        return (0.0, [], None)

    def _detect_target_profile(self, elements, texts, descs, ids, all_text, all_ids, target) -> Tuple:
        """Detect target user's profile page with Follow button.

        Key IDs from flow analysis:
        - action_bar_title (username in header)
        - action_bar_username_container (username container)
        - profile_header_follow_button (Follow button)
        - profile_header_followers_stacked_familiar
        - profile_header_following_stacked_familiar
        """
        # Primary: Check for profile-specific IDs
        has_follow_button = self._has_element_id(elements, 'profile_header_follow_button')
        has_followers_section = self._has_element_id(elements, 'profile_header_followers_stacked_familiar')
        has_following_section = self._has_element_id(elements, 'profile_header_following_stacked_familiar')
        has_action_bar_title = self._has_element_id(elements, 'action_bar_title')
        has_username_container = self._has_element_id(elements, 'action_bar_username_container')

        score = 0
        found = []

        if has_follow_button:
            score += 0.5
            found.append('follow_button_id')
        if has_followers_section:
            score += 0.2
            found.append('followers_section')
        if has_following_section:
            score += 0.1
            found.append('following_section')
        if has_action_bar_title:
            score += 0.15
            found.append('action_bar_title')

        # FIX: Handle profile view without follow button visible
        # When has action_bar_username_container + action_bar_title, this is a profile view
        # Need to scroll or look for follow button
        if has_username_container and has_action_bar_title and not has_follow_button:
            # Profile view but follow button not visible - might need to scroll
            score = max(score, 0.75)
            found.append('profile_view')
            # Return back button index to navigate away if needed
            back_idx = self._find_element_index_by_id(elements, 'action_bar_button_back')
            return (min(score, 0.95), found, back_idx)

        # Find the Follow button index
        follow_idx = self._find_element_index_by_id(elements, 'profile_header_follow_button')

        return (min(score, 0.95), found, follow_idx)

    def _detect_search_results(self, elements, texts, descs, ids, all_text, all_ids, target) -> Tuple:
        """Detect search results showing user matches.

        Key IDs from flow analysis:
        - row_search_user_container (clickable user row)
        - row_search_user_username (username text)
        - row_search_user_fullname (full name text)
        - row_search_keyword_title

        IMPORTANT: Distinguish from SEARCH_INPUT by checking if the username is typed.
        Recent searches screen has row_search_user_container but search bar has placeholder.
        """
        has_user_container = 'row_search_user_container' in all_ids
        has_username_element = 'row_search_user_username' in all_ids
        has_fullname_element = 'row_search_user_fullname' in all_ids
        has_search_bar = 'action_bar_search_edit_text' in all_ids

        # Must have search results elements
        if not (has_user_container or has_username_element):
            return (0.0, [], None)

        # FIX: Check if the search bar has the username typed (not just placeholder)
        # If search bar has "Search" or "Search with Meta AI", it's SEARCH_INPUT, not SEARCH_RESULTS
        # NOTE: In some UI versions, search bar text is empty and "Search" is a separate child element
        search_bar_has_placeholder = False
        search_bar_text = ""
        search_bar_is_empty = False
        for el in elements:
            if el.get('id', '') == 'action_bar_search_edit_text':
                search_bar_text = el.get('text', '').lower()
                if 'search' in search_bar_text:
                    search_bar_has_placeholder = True
                elif search_bar_text == '':
                    search_bar_is_empty = True
                break

        # Also check for "Search" placeholder as a separate text element (empty id)
        # This happens when search bar text is empty but "Search" is visible
        if search_bar_is_empty:
            for el in elements:
                el_text = el.get('text', '').lower()
                el_id = el.get('id', '')
                # "Search" text without a meaningful id = placeholder
                if el_text == 'search' and el_id == '':
                    search_bar_has_placeholder = True
                    break

        # If search bar has placeholder or is empty with separate "Search" text,
        # this is the recent searches screen (SEARCH_INPUT), NOT actual search results
        if search_bar_has_placeholder:
            return (0.0, [], None)

        # If no target provided but search bar has some text, check if it looks like a username
        if target:
            target_lower = target.lower()
            # Check if target is in the search bar (typed username)
            if target_lower not in search_bar_text and search_bar_text and 'search' not in search_bar_text:
                # Search bar has different text - maybe a different search
                pass  # Continue with detection

        score = 0
        found = []

        if has_user_container:
            score += 0.4
            found.append('user_container')
        if has_username_element:
            score += 0.3
            found.append('username_element')
        if has_fullname_element:
            score += 0.1
            found.append('fullname_element')
        if has_search_bar:
            score += 0.1
            found.append('search_bar')

        # Find the target user in results
        target_idx = None
        if target:
            target_lower = target.lower()
            for i, el in enumerate(elements):
                el_text = el.get('text', '').lower()
                el_id = el.get('id', '')
                # Match username in row_search_user_username elements
                if el_id == 'row_search_user_username' and el_text == target_lower:
                    # The clickable container is usually the parent - find row_search_user_container
                    # that comes before this element
                    for j in range(i, -1, -1):
                        if elements[j].get('id', '') == 'row_search_user_container':
                            target_idx = j
                            break
                    if target_idx is None:
                        target_idx = i  # Fallback to the username element
                    found.append(f'found_target:{target}')
                    score += 0.1
                    break

        return (min(score, 0.95), found, target_idx)

    def _detect_search_input(self, elements, texts, descs, ids, all_text, all_ids, target) -> Tuple:
        """Detect search input screen with recent searches.

        Key IDs from flow analysis:
        - action_bar_search_edit_text (search input field)
        - action_bar_button_back (back button)
        - row_search_user_container (recent search items)
        - dismiss_button (clear recent search)
        - row_search_keyword_title (keyword suggestions)

        IMPORTANT: This screen shows recent searches BEFORE typing. The search bar
        shows placeholder "Search" or "Search with Meta AI". Once typing starts,
        it becomes SEARCH_RESULTS (with typed username in search bar).
        """
        has_search_input = 'action_bar_search_edit_text' in all_ids
        has_back_button = 'action_bar_button_back' in all_ids
        has_recent_text = 'recent' in all_text
        has_dismiss_button = 'dismiss_button' in all_ids
        has_keyword_title = 'row_search_keyword_title' in all_ids

        # Check if search bar has placeholder (not typed username)
        # NOTE: In some UI versions, search bar text is empty and "Search" is a separate child element
        search_bar_has_placeholder = False
        search_bar_is_empty = False
        for el in elements:
            if el.get('id', '') == 'action_bar_search_edit_text':
                text = el.get('text', '').lower()
                if 'search' in text:  # "Search" or "Search with Meta AI"
                    search_bar_has_placeholder = True
                elif text == '':
                    search_bar_is_empty = True
                break

        # Also check for "Search" placeholder as a separate text element (empty id)
        if search_bar_is_empty:
            for el in elements:
                el_text = el.get('text', '').lower()
                el_id = el.get('id', '')
                if el_text == 'search' and el_id == '':
                    search_bar_has_placeholder = True
                    break

        # FIX: If search bar has placeholder, this is SEARCH_INPUT (waiting for user to type)
        # Even if row_search_user_container exists (for recent searches)
        # If search bar has typed text (no placeholder), let SEARCH_RESULTS handle it

        if not has_search_input:
            return (0.0, [], None)

        score = 0
        found = []

        if has_search_input and has_back_button:
            score += 0.5
            found.append('search_input_bar')

        if has_recent_text:
            score += 0.25
            found.append('recent_header')
        if has_dismiss_button:
            score += 0.15
            found.append('dismiss_button')
        if has_keyword_title:
            score += 0.1
            found.append('keyword_suggestions')

        # Check if search bar has placeholder (empty/ready for typing)
        if search_bar_has_placeholder:
            score += 0.2
            found.append('search_placeholder')

        # If we have back button + search with placeholder + recent/dismiss elements,
        # this is definitely SEARCH_INPUT (recent searches screen)
        if has_back_button and search_bar_has_placeholder and (has_recent_text or has_dismiss_button):
            score = max(score, 0.9)
            found.append('recent_searches_screen')

        # Find search input element index for typing
        search_idx = self._find_element_index_by_id(elements, 'action_bar_search_edit_text')

        return (min(score, 0.95), found, search_idx)

    def _detect_explore_page(self, elements, texts, descs, ids, all_text, all_ids, target) -> Tuple:
        """Detect explore page with grid and search bar.

        Key IDs from flow analysis:
        - grid_card_layout_container (content grid) - may be missing in some variants
        - action_bar_search_edit_text (search bar at top)
        - image_button (grid items)
        - Bottom nav: feed_tab, clips_tab, search_tab, profile_tab
        """
        has_grid_container = 'grid_card_layout_container' in all_ids
        has_search_bar = 'action_bar_search_edit_text' in all_ids
        has_search_tab = 'search_tab' in all_ids
        has_nav_tabs = 'feed_tab' in all_ids and 'profile_tab' in all_ids

        # Key: Explore has the grid + search bar with "Search with Meta AI"
        # But NOT the back button (which indicates we're in search input)
        has_back_button = 'action_bar_button_back' in all_ids

        if has_back_button:
            # If back button exists, this is search_input, not explore
            return (0.0, [], None)

        score = 0
        found = []

        if has_grid_container:
            score += 0.4
            found.append('grid_container')
        if has_search_bar:
            score += 0.3
            found.append('search_bar')
        if has_nav_tabs:
            score += 0.2
            found.append('nav_tabs')
        if has_search_tab:
            score += 0.1
            found.append('search_tab')

        # FIX: Accept explore even without grid if has search bar + nav tabs + search_tab
        # This handles the variant explore page without grid_card_layout_container
        if not has_grid_container and has_search_bar and has_nav_tabs and has_search_tab:
            score = max(score, 0.75)
            if 'explore_variant' not in found:
                found.append('explore_variant')

        # Find search bar index for tapping
        search_idx = self._find_element_index_by_id(elements, 'action_bar_search_edit_text')

        return (min(score, 0.95), found, search_idx)

    def _detect_home_feed(self, elements, texts, descs, ids, all_text, all_ids, target) -> Tuple:
        """Detect home feed screen.

        Key IDs from flow analysis:
        - feed_tab, search_tab, clips_tab, profile_tab (bottom nav)
        - title_logo (Instagram logo)
        - avatar_image_view (story avatars)
        - reel_empty_badge (story indicators)
        - row_feed_profile_header (feed posts)
        """
        has_feed_tab = 'feed_tab' in all_ids
        has_search_tab = 'search_tab' in all_ids
        has_profile_tab = 'profile_tab' in all_ids
        has_clips_tab = 'clips_tab' in all_ids
        has_title_logo = 'title_logo' in all_ids

        # Distinguish from explore: home has title_logo (Instagram header)
        # Explore has grid_card_layout_container
        has_grid = 'grid_card_layout_container' in all_ids
        has_search_bar = 'action_bar_search_edit_text' in all_ids

        if has_grid:
            # This is explore, not home feed
            return (0.0, [], None)

        if has_search_bar:
            # Explore variant, not home feed
            return (0.0, [], None)

        score = 0
        found = []

        if has_feed_tab and has_search_tab and has_profile_tab:
            score += 0.5
            found.append('nav_tabs')
        if has_title_logo:
            score += 0.3
            found.append('title_logo')
        if has_clips_tab:
            score += 0.1
            found.append('clips_tab')

        # FIX: Handle home feed with stories visible (no title_logo visible)
        # Key indicators: avatar_image_view, reel_empty_badge, row_feed_profile_header
        has_stories = 'avatar_image_view' in all_ids or 'reel_empty_badge' in all_ids
        has_feed_post = 'row_feed_profile_header' in all_ids or 'media_group' in all_ids

        if (has_stories or has_feed_post) and has_feed_tab and has_profile_tab:
            # Home feed with stories visible
            score = max(score, 0.8)
            if has_stories:
                found.append('stories_tray')
            if has_feed_post:
                found.append('feed_post')

        # Find search tab index for tapping
        search_idx = self._find_element_index_by_id(elements, 'search_tab')

        return (min(score, 0.95), found, search_idx)


# Convenience function
def detect_follow_screen(elements: List[Dict], target: str = "") -> FollowScreenType:
    """Quick screen detection returning just the type."""
    detector = FollowScreenDetector()
    result = detector.detect(elements, target)
    return result.screen_type


if __name__ == "__main__":
    # Test with sample elements from flow
    print("FollowScreenDetector - Test")
    print("=" * 50)

    detector = FollowScreenDetector()

    # Test home feed elements
    home_elements = [
        {'id': 'feed_tab', 'text': '', 'desc': 'Home'},
        {'id': 'search_tab', 'text': '', 'desc': 'Search'},
        {'id': 'profile_tab', 'text': '', 'desc': 'Profile'},
        {'id': 'title_logo', 'text': '', 'desc': 'Instagram'},
    ]
    result = detector.detect(home_elements)
    print(f"Home feed: {result.screen_type.name} (conf={result.confidence:.2f})")

    # Test explore page
    explore_elements = [
        {'id': 'grid_card_layout_container', 'text': '', 'desc': 'Reel'},
        {'id': 'action_bar_search_edit_text', 'text': 'Search with Meta AI', 'desc': ''},
        {'id': 'feed_tab', 'text': '', 'desc': 'Home'},
        {'id': 'profile_tab', 'text': '', 'desc': 'Profile'},
    ]
    result = detector.detect(explore_elements)
    print(f"Explore: {result.screen_type.name} (conf={result.confidence:.2f})")

    # Test profile with follow button
    profile_elements = [
        {'id': 'action_bar_title', 'text': 'matt.s.trotter', 'desc': ''},
        {'id': 'profile_header_follow_button', 'text': 'Follow', 'desc': 'Follow Matt'},
        {'id': 'profile_header_followers_stacked_familiar', 'text': '', 'desc': '530 followers'},
    ]
    result = detector.detect(profile_elements, 'matt.s.trotter')
    print(f"Profile: {result.screen_type.name} (conf={result.confidence:.2f}), target_idx={result.target_element_index}")
