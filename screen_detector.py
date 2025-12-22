"""
ScreenDetector - Deterministic screen type detection for Instagram posting.

Part of the Hybrid Posting System - Phase 4.
Replaces AI calls with rule-based detection for known screens.
"""
from enum import Enum, auto
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass


class ScreenType(Enum):
    """Known Instagram screen types during Reel posting flow."""
    # Main flow screens
    FEED_SCREEN = auto()        # Home feed with stories
    PROFILE_SCREEN = auto()     # User profile page
    CREATE_MENU = auto()        # Create popup (Reel/Story/Post options)
    GALLERY_PICKER = auto()     # "New reel" video selection
    CAMERA_SCREEN = auto()      # Camera interface for recording
    VIDEO_EDITING = auto()      # Video editor with Next button
    SHARE_PREVIEW = auto()      # Caption input + Edit cover
    SHARING_PROGRESS = auto()   # "Sharing to Reels..."
    SUCCESS_SCREEN = auto()     # Post complete confirmation

    # Content viewing screens
    REEL_VIEW = auto()          # Viewing a reel/post
    STORY_VIEW = auto()         # Viewing stories
    OWN_REEL_VIEW = auto()      # Viewing your own posted reel (has "View insights", "Boost reel")
    FEED_POST = auto()          # Viewing a post in feed (has likes, comments, suggested)
    REELS_TAB = auto()          # Reels tab ("Reel by X", "Double tap to play")
    STORY_EDITOR = auto()       # Story editor with stickers
    SHARE_SHEET = auto()        # "Also share to" share options

    # Popup screens
    POPUP_DISMISSIBLE = auto()  # "Not now", "Skip", "Later" popups
    POPUP_VERIFICATION = auto() # ID verification request
    POPUP_ACTION_REQ = auto()   # Requires action (login, etc)
    POPUP_ONBOARDING = auto()   # "Swipe to access Reels", tips, tutorials
    POPUP_WARNING = auto()      # "Your reel may get limited reach"
    POPUP_CAPTCHA = auto()      # "Confirm you're human"
    POPUP_SUGGESTED = auto()    # "Suggested for you" follow suggestions
    BROWSER_POPUP = auto()      # External browser/link opened
    DM_SCREEN = auto()          # Direct messages or story reply
    LOADING_SCREEN = auto()     # Empty/loading screen
    ANDROID_HOME = auto()       # Android home screen (not Instagram)
    SPONSORED_POST = auto()     # Sponsored/ad post with "Learn more"

    # Error states
    LOGIN_SCREEN = auto()       # Logged out / login required
    ERROR_SCREEN = auto()       # Something went wrong

    # Fallback
    UNKNOWN = auto()            # Unrecognized screen


@dataclass
class DetectionResult:
    """Result of screen detection with confidence."""
    screen_type: ScreenType
    confidence: float  # 0.0 to 1.0
    matched_rule: str  # Which rule matched
    key_elements: List[str]  # Elements that triggered the match


class ScreenDetector:
    """Detects Instagram screen types from UI elements."""

    # Confidence threshold - below this, return UNKNOWN
    CONFIDENCE_THRESHOLD = 0.7

    def __init__(self):
        """Initialize detector with detection rules."""
        # Detection rules in priority order (first match wins)
        self.rules = [
            # Popups first (highest priority - they overlay other screens)
            ('POPUP_VERIFICATION', self._detect_verification_popup),
            ('LOGIN_SCREEN', self._detect_login_screen),
            ('POPUP_DISMISSIBLE', self._detect_dismissible_popup),

            # Success/progress screens
            ('SUCCESS_SCREEN', self._detect_success_screen),
            ('SHARING_PROGRESS', self._detect_sharing_progress),

            # New popups (high priority - they overlay other screens)
            ('ANDROID_HOME', self._detect_android_home),
            ('LOADING_SCREEN', self._detect_loading_screen),
            ('BROWSER_POPUP', self._detect_browser_popup),
            ('DM_SCREEN', self._detect_dm_screen),
            ('SPONSORED_POST', self._detect_sponsored_post),
            ('POPUP_CAPTCHA', self._detect_captcha),
            ('POPUP_ONBOARDING', self._detect_onboarding),
            ('POPUP_WARNING', self._detect_warning_popup),
            ('POPUP_SUGGESTED', self._detect_suggested_popup),

            # Content viewing (can appear during navigation)
            ('SHARE_SHEET', self._detect_share_sheet),
            ('STORY_EDITOR', self._detect_story_editor),
            ('OWN_REEL_VIEW', self._detect_own_reel_view),
            ('REELS_TAB', self._detect_reels_tab),
            ('STORY_VIEW', self._detect_story_view),
            ('REEL_VIEW', self._detect_reel_view),
            ('FEED_POST', self._detect_feed_post),

            # Main flow screens (order matters)
            ('SHARE_PREVIEW', self._detect_share_preview),
            ('VIDEO_EDITING', self._detect_video_editing),
            ('CAMERA_SCREEN', self._detect_camera_screen),
            ('GALLERY_PICKER', self._detect_gallery_picker),
            ('CREATE_MENU', self._detect_create_menu),
            ('PROFILE_SCREEN', self._detect_profile_screen),
            ('FEED_SCREEN', self._detect_feed_screen),
        ]

    def detect(self, elements: List[Dict]) -> DetectionResult:
        """Detect screen type from UI elements.

        Args:
            elements: List of UI element dicts from dump_ui().

        Returns:
            DetectionResult with screen type and confidence.
        """
        if not elements:
            return DetectionResult(
                screen_type=ScreenType.UNKNOWN,
                confidence=0.0,
                matched_rule='empty_elements',
                key_elements=[]
            )

        # Extract text for matching
        texts = self._extract_texts(elements)
        descs = self._extract_descs(elements)
        all_text = ' '.join(texts + descs).lower()

        # Try each rule in priority order
        best_result = None

        for rule_name, detector_fn in self.rules:
            confidence, key_elements = detector_fn(elements, texts, descs, all_text)

            if confidence >= self.CONFIDENCE_THRESHOLD:
                return DetectionResult(
                    screen_type=ScreenType[rule_name],
                    confidence=confidence,
                    matched_rule=rule_name,
                    key_elements=key_elements
                )

            # Track best sub-threshold match for debugging
            if best_result is None or confidence > best_result.confidence:
                best_result = DetectionResult(
                    screen_type=ScreenType[rule_name],
                    confidence=confidence,
                    matched_rule=rule_name,
                    key_elements=key_elements
                )

        # No rule matched with sufficient confidence
        return DetectionResult(
            screen_type=ScreenType.UNKNOWN,
            confidence=best_result.confidence if best_result else 0.0,
            matched_rule=f'best_was_{best_result.matched_rule}' if best_result else 'none',
            key_elements=best_result.key_elements if best_result else []
        )

    def _extract_texts(self, elements: List[Dict]) -> List[str]:
        """Extract text fields from elements."""
        return [e.get('text', '').lower().strip() for e in elements if e.get('text')]

    def _extract_descs(self, elements: List[Dict]) -> List[str]:
        """Extract description fields from elements."""
        return [e.get('desc', '').lower().strip() for e in elements if e.get('desc')]

    def _extract_ids(self, elements: List[Dict]) -> List[str]:
        """Extract element IDs from elements."""
        return [e.get('id', '').lower().strip() for e in elements if e.get('id')]

    def _has_element_id(self, elements: List[Dict], element_id: str) -> bool:
        """Check if any element has the given ID."""
        return any(e.get('id', '') == element_id for e in elements)

    def _has_element_desc(self, elements: List[Dict], desc: str) -> bool:
        """Check if any element has the given description."""
        return any(desc.lower() in e.get('desc', '').lower() for e in elements)

    # ==================== Detection Rules ====================

    def _detect_verification_popup(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect ID verification popup."""
        markers = ['upload your id', 'verify your identity', 'confirm your identity',
                   'government id', 'official id']
        found = [m for m in markers if m in all_text]
        if found:
            return 0.95, found
        return 0.0, []

    def _detect_login_screen(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect login/logged out screen."""
        markers = ['log in', 'sign in', 'create new account', 'forgot password',
                   'log into instagram', 'continue as']
        found = [m for m in markers if m in all_text]
        if len(found) >= 2:
            return 0.95, found
        elif len(found) == 1:
            return 0.75, found
        return 0.0, []

    def _detect_dismissible_popup(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect dismissible popup (Not now, Skip, etc)."""
        dismiss_markers = ['not now', 'skip', 'maybe later', 'dismiss', 'no thanks',
                          'remind me later', "don't allow", 'cancel']
        found = [m for m in dismiss_markers if m in all_text]

        # Must have dismiss option AND some other content
        if found and len(elements) < 20:  # Popups typically have fewer elements
            return 0.85, found
        elif found:
            return 0.6, found
        return 0.0, []

    def _detect_success_screen(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect post success confirmation."""
        markers = ['your reel', 'shared', 'posted', 'uploaded successfully']
        found = [m for m in markers if m in all_text]

        if 'your reel' in all_text and ('shared' in all_text or 'posted' in all_text):
            return 0.95, ['your reel shared']
        elif len(found) >= 2:
            return 0.8, found
        return 0.0, []

    def _detect_sharing_progress(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect sharing in progress screen."""
        # Primary: Check for upload snackbar container ID (from successful flow data)
        has_upload_snackbar = self._has_element_id(elements, 'upload_snackbar_container')

        # Secondary: "Sharing to Reels" text indicator
        has_sharing_to_reels = 'sharing to reels' in all_text

        # Tertiary: Generic progress markers
        markers = ['sharing', 'posting', 'uploading', 'sending']
        progress_markers = ['...', 'progress', 'please wait']

        found_markers = [m for m in markers if m in all_text]

        score = 0
        found = []

        # ID-based detection (high confidence)
        if has_upload_snackbar:
            score += 0.6
            found.append('upload_snackbar_id')

        # Text-based detection
        if has_sharing_to_reels:
            score += 0.35
            found.append('sharing_to_reels')
        if found_markers:
            score += 0.2
            found.extend(found_markers)
        if any(p in all_text for p in progress_markers):
            score += 0.1
            found.append('progress_indicator')

        return min(score, 0.95), found

    def _detect_share_preview(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect share preview screen (caption input + edit cover)."""
        # Primary: Check for share-specific element IDs (from successful flow data)
        has_caption_input = self._has_element_id(elements, 'caption_input_text_view')  # 71.4% of flows
        has_share_button = self._has_element_id(elements, 'share_button')  # 65% of flows
        has_action_bar_text = self._has_element_id(elements, 'action_bar_button_text')  # OK button
        has_save_draft = self._has_element_id(elements, 'save_draft_button')

        # Secondary: Check for Share button by desc
        has_share_desc = self._has_element_desc(elements, 'Share')
        has_ok_desc = self._has_element_desc(elements, 'OK')  # 62.4% need this step

        # Tertiary: Text-based detection
        has_caption = 'write a caption' in all_text or 'add a caption' in all_text
        has_edit_cover = 'edit cover' in all_text
        has_share = 'share' in texts
        has_hashtags = 'hashtags' in texts or 'hashtags' in all_text
        has_poll = 'poll' in texts
        has_link_reel = 'link a reel' in all_text

        score = 0
        found = []

        # ID-based detection (high confidence)
        if has_caption_input:
            score += 0.4
            found.append('caption_input_id')
        if has_share_button:
            score += 0.35
            found.append('share_button_id')
        if has_action_bar_text and has_ok_desc:
            score += 0.2
            found.append('ok_button')
        if has_save_draft:
            score += 0.1
            found.append('save_draft_id')

        # Desc-based detection
        if has_share_desc:
            score += 0.2
            found.append('share_desc')

        # Text-based fallback
        if has_caption:
            score += 0.15
            found.append('caption')
        if has_edit_cover:
            score += 0.1
            found.append('edit_cover')
        if has_share:
            score += 0.1
            found.append('share_text')
        if has_hashtags:
            score += 0.1
            found.append('hashtags')
        if has_poll or has_link_reel:
            score += 0.1
            found.append('caption_options')

        return min(score, 0.95), found

    def _detect_video_editing(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect video editing screen."""
        # Primary: Check for video editing element IDs (from successful flow data)
        has_clips_right_button = self._has_element_id(elements, 'clips_right_action_button')  # Next button
        has_clips_action_bar = any(self._has_element_id(elements, f'clips_action_bar_{x}')
                                   for x in ['button', 'container', 'text'])
        has_clips_left_button = self._has_element_id(elements, 'clips_left_action_button')

        # Secondary: Check for Next button by desc (73.3% of flows)
        has_next_desc = self._has_element_desc(elements, 'Next')

        # Tertiary: Text-based detection
        has_edit_video = 'edit video' in all_text or 'swipe up to edit' in all_text
        has_next = 'next' in texts
        has_audio = 'add audio' in all_text or 'audio' in texts
        has_effects = 'effects' in all_text or 'filters' in all_text

        score = 0
        found = []

        # ID-based detection (high confidence)
        if has_clips_right_button:
            score += 0.5
            found.append('clips_right_button_id')
        if has_clips_action_bar:
            score += 0.2
            found.append('clips_action_bar_id')
        if has_clips_left_button:
            score += 0.1
            found.append('clips_left_button_id')

        # Desc-based detection
        if has_next_desc:
            score += 0.25
            found.append('next_desc')

        # Text-based fallback
        if has_edit_video:
            score += 0.2
            found.append('edit_video')
        if has_next:
            score += 0.1
            found.append('next')
        if has_audio or has_effects:
            score += 0.1
            found.append('audio/effects')

        return min(score, 0.95), found

    def _detect_gallery_picker(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect gallery/video picker screen."""
        # Primary: Check for gallery-specific element IDs (from successful flow data)
        has_gallery_thumbnail = self._has_element_id(elements, 'gallery_grid_item_thumbnail')
        has_cam_dest_clips = self._has_element_id(elements, 'cam_dest_clips')  # REEL tab
        has_gallery_dest_item = self._has_element_id(elements, 'gallery_destination_item')
        has_preview_container = self._has_element_id(elements, 'preview_container')

        # Secondary: Text-based detection
        has_new_reel = 'new reel' in all_text
        has_recents = 'recents' in all_text
        has_gallery = 'gallery' in all_text or 'album' in all_text
        has_thumbnails = any('thumbnail' in d for d in descs)

        score = 0
        found = []

        # ID-based detection (high confidence)
        if has_gallery_thumbnail:
            score += 0.45
            found.append('gallery_thumbnail_id')
        if has_cam_dest_clips:
            score += 0.25
            found.append('reel_tab_id')
        if has_gallery_dest_item:
            score += 0.2
            found.append('gallery_dest_id')
        if has_preview_container:
            score += 0.1
            found.append('preview_id')

        # Text-based fallback
        if has_new_reel:
            score += 0.25
            found.append('new_reel')
        if has_recents or has_gallery:
            score += 0.15
            found.append('recents/gallery')
        if has_thumbnails:
            score += 0.1
            found.append('thumbnails')

        return min(score, 0.95), found

    def _detect_create_menu(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect create menu popup (Reel/Story/Post options)."""
        # Primary: "Create new reel" in description (90.8% of successful flows)
        # NOTE: This is in desc, not text!
        has_create_new_reel = self._has_element_desc(elements, 'Create new reel')
        has_create_new_story = self._has_element_desc(elements, 'Create new story')
        has_create_new_post = self._has_element_desc(elements, 'Create new post')

        # Secondary: text-based (less reliable)
        options = ['reel', 'story', 'post', 'live']
        found_text = [o for o in options if o in texts]

        score = 0
        found = []

        # Desc-based detection (high confidence)
        if has_create_new_reel:
            score += 0.5
            found.append('create_new_reel_desc')
        if has_create_new_story:
            score += 0.2
            found.append('create_new_story_desc')
        if has_create_new_post:
            score += 0.2
            found.append('create_new_post_desc')

        # Text-based fallback
        if len(found_text) >= 2:
            score += 0.3
            found.extend(found_text)
        elif len(found_text) == 1:
            score += 0.15
            found.extend(found_text)

        return min(score, 0.95), found

    def _detect_profile_screen(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect user profile screen."""
        # Primary: Check for profile-specific element IDs (from successful flow data)
        has_username_container = self._has_element_id(elements, 'action_bar_username_container')
        has_profile_header = any(self._has_element_id(elements, f'profile_header_{x}')
                                 for x in ['avatar', 'bio', 'followers'])
        has_creation_tab = self._has_element_id(elements, 'creation_tab')

        # Key indicator: "Create New" button in description (91.5% of successful flows)
        has_create_new = self._has_element_desc(elements, 'Create New')

        # Secondary: Text-based detection
        has_posts = 'posts' in all_text or any('posts' in d for d in descs)
        has_followers = 'followers' in all_text
        has_following = 'following' in all_text
        has_edit_profile = 'edit profile' in all_text
        has_profile_desc = any('profile' in d or 'your profile' in d for d in descs)
        has_your_story = 'your story' in all_text
        has_add_story = 'add to story' in all_text

        score = 0
        found = []

        # ID-based detection (high confidence)
        if has_username_container:
            score += 0.4
            found.append('username_container_id')
        if has_create_new:
            score += 0.35
            found.append('create_new_desc')
        if has_creation_tab:
            score += 0.2
            found.append('creation_tab_id')
        if has_profile_header:
            score += 0.15
            found.append('profile_header_id')

        # Text-based fallback
        if has_posts:
            score += 0.2
            found.append('posts')
        if has_followers:
            score += 0.15
            found.append('followers')
        if has_following:
            score += 0.1
            found.append('following')
        if has_edit_profile:
            score += 0.15
            found.append('edit_profile')
        if has_profile_desc:
            score += 0.1
            found.append('profile_desc')
        if has_your_story or has_add_story:
            score += 0.05
            found.append('story')

        return min(score, 0.95), found

    def _detect_feed_screen(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect home feed screen."""
        # Primary: Check for navigation tab IDs (from successful flow data)
        has_profile_tab = self._has_element_id(elements, 'profile_tab')
        has_feed_tab = self._has_element_id(elements, 'feed_tab')
        has_clips_tab = self._has_element_id(elements, 'clips_tab')
        has_search_tab = self._has_element_id(elements, 'search_tab')

        # Secondary: Text-based detection
        has_home = any('home' in d for d in descs)
        has_stories = 'story' in all_text and 'unseen' in all_text
        has_reels_tray = 'reels tray' in all_text
        has_nav_tabs = sum(1 for t in ['home', 'search', 'reels', 'shop'] if t in all_text) >= 2
        has_your_story = 'your story' in texts

        score = 0
        found = []

        # ID-based detection (high confidence)
        if has_profile_tab and has_feed_tab:
            score += 0.5
            found.append('nav_tab_ids')
        if has_clips_tab:
            score += 0.2
            found.append('clips_tab')

        # Text-based fallback
        if has_home:
            score += 0.2
            found.append('home_tab')
        if has_stories:
            score += 0.2
            found.append('stories')
        if has_reels_tray:
            score += 0.2
            found.append('reels_tray')
        if has_nav_tabs:
            score += 0.1
            found.append('nav_tabs')
        if has_your_story:
            score += 0.1
            found.append('your_story')

        return min(score, 0.95), found

    def _detect_android_home(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect Android home screen (not Instagram)."""
        android_apps = ['gallery', 'play store', 'phone', 'messaging', 'chrome', 'camera', 'settings']
        found_apps = [app for app in android_apps if app in all_text]

        if len(found_apps) >= 3:
            return 0.95, found_apps
        if len(found_apps) >= 2 and 'home' in descs:
            return 0.85, found_apps
        return 0.0, []

    def _detect_sponsored_post(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect sponsored/ad post."""
        has_learn_more = 'learn more' in all_text
        has_like = any(d.lower() == 'like' for d in descs)
        has_comment = 'comment' in descs or 'comment' in all_text
        has_sponsored = 'sponsored' in all_text
        has_views = 'views' in all_text

        if has_learn_more and has_like:
            score = 0.7
            found = ['learn_more', 'like']
            if has_comment:
                score += 0.1
                found.append('comment')
            if has_sponsored or has_views:
                score += 0.1
                found.append('ad_indicator')
            return min(score, 0.9), found
        return 0.0, []

    def _detect_loading_screen(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect empty/loading screen."""
        # Very few or no elements = loading
        if len(elements) <= 2 and not texts and not descs:
            return 0.8, ['empty']
        if len(elements) <= 5 and not all_text.strip():
            return 0.75, ['minimal_elements']
        return 0.0, []

    def _detect_browser_popup(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect external browser opened."""
        has_close_browser = 'close browser' in all_text
        has_link_history = 'link history' in all_text
        has_url = '.com' in all_text or '.org' in all_text or 'http' in all_text
        has_more_options = 'more options' in all_text

        if has_close_browser:
            return 0.95, ['close_browser']
        if has_link_history and has_url:
            return 0.85, ['browser_link']
        if has_url and has_more_options:
            return 0.75, ['external_url']
        return 0.0, []

    def _detect_dm_screen(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect DM/messaging screen."""
        has_send = 'send' in texts or 'send' in descs
        has_message = 'message' in all_text
        has_story_reply = 'story' in all_text and ('ago' in all_text or 'hours' in all_text)
        has_profile_picture = 'profile picture' in all_text

        score = 0
        found = []

        if has_send:
            score += 0.4
            found.append('send')
        if has_story_reply:
            score += 0.3
            found.append('story_reply')
        if has_message:
            score += 0.2
            found.append('message')
        if has_profile_picture:
            score += 0.1
            found.append('profile_pic')

        return min(score, 0.9), found

    def _detect_captcha(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect captcha/human verification screen."""
        has_confirm_human = "confirm you're human" in all_text
        has_continue = 'continue' in texts
        has_verification = 'verification' in all_text

        if has_confirm_human:
            return 0.95, ['confirm_human']
        if has_verification and has_continue:
            return 0.8, ['verification', 'continue']
        return 0.0, []

    def _detect_onboarding(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect onboarding/tutorial popups."""
        has_swipe_access = 'swipe to' in all_text and ('reels' in all_text or 'messages' in all_text)
        has_got_it = 'got it' in texts
        has_ok_button = 'ok' in texts and len(elements) < 15
        has_simplified = 'simplified' in all_text or 'navigation' in all_text
        has_new_feature = "we've" in all_text or 'new feature' in all_text
        has_introducing = 'introducing' in all_text
        has_archive = 'archive' in all_text
        has_edit_settings = 'edit in settings' in all_text

        score = 0
        found = []

        if has_swipe_access:
            score += 0.5
            found.append('swipe_access')
        if has_got_it or has_ok_button:
            score += 0.3
            found.append('dismiss_button')
        if has_simplified or has_new_feature:
            score += 0.2
            found.append('new_feature')
        if has_introducing:
            score += 0.4
            found.append('introducing')
        if has_archive:
            score += 0.2
            found.append('archive')
        if has_edit_settings:
            score += 0.2
            found.append('settings')

        return min(score, 0.95), found

    def _detect_warning_popup(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect warning popups about content."""
        has_limited_reach = 'limited reach' in all_text
        has_wont_recommend = "won't be recommended" in all_text
        has_over_minutes = 'over' in all_text and 'minutes' in all_text

        if has_limited_reach or has_wont_recommend:
            found = []
            if has_limited_reach:
                found.append('limited_reach')
            if has_wont_recommend:
                found.append('wont_recommend')
            if has_over_minutes:
                found.append('over_minutes')
            return 0.9, found
        return 0.0, []

    def _detect_suggested_popup(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect 'Suggested for you' follow popup."""
        has_suggested = 'suggested for you' in all_text
        has_see_all = 'see all' in texts
        has_follow = 'follow' in texts
        has_dismiss = 'dismiss' in all_text

        if has_suggested and (has_follow or has_dismiss):
            found = ['suggested']
            if has_dismiss:
                found.append('dismiss')
            if has_see_all:
                found.append('see_all')
            return 0.85, found
        return 0.0, []

    def _detect_share_sheet(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect share sheet popup."""
        has_also_share = 'also share to' in all_text
        has_add_highlights = 'add to highlights' in all_text
        has_facebook_story = 'facebook story' in all_text

        if has_also_share:
            found = ['also_share']
            if has_add_highlights:
                found.append('highlights')
            if has_facebook_story:
                found.append('facebook')
            return 0.9, found
        return 0.0, []

    def _detect_story_editor(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect story editor with stickers."""
        has_location_sticker = 'location sticker' in all_text
        has_mention_sticker = 'mention sticker' in all_text
        has_add_yours = 'add yours sticker' in all_text
        has_sticker = 'sticker' in all_text

        sticker_count = sum([has_location_sticker, has_mention_sticker, has_add_yours])
        if sticker_count >= 2 or (has_sticker and sticker_count >= 1):
            found = []
            if has_location_sticker:
                found.append('location')
            if has_mention_sticker:
                found.append('mention')
            if has_add_yours:
                found.append('add_yours')
            return 0.85, found
        return 0.0, []

    def _detect_reels_tab(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect Reels tab (vertical video feed)."""
        has_reel_by = 'reel by' in all_text
        has_double_tap = 'double tap to play' in all_text
        has_reels = 'reels' in texts
        has_friends = 'friends' in texts or 'for you' in texts

        score = 0
        found = []

        if has_reel_by:
            score += 0.4
            found.append('reel_by')
        if has_double_tap:
            score += 0.3
            found.append('double_tap')
        if has_reels:
            score += 0.15
            found.append('reels')
        if has_friends:
            score += 0.15
            found.append('friends_tab')

        return min(score, 0.9), found

    def _detect_own_reel_view(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect viewing your own posted reel (has insights, boost options)."""
        has_view_insights = 'view insights' in all_text
        has_boost_reel = 'boost reel' in all_text
        has_boost_post = 'boost post' in all_text
        has_reels = 'reels' in texts

        score = 0
        found = []

        if has_view_insights:
            score += 0.5
            found.append('view_insights')
        if has_boost_reel or has_boost_post:
            score += 0.4
            found.append('boost')
        if has_reels:
            score += 0.1
            found.append('reels')

        return min(score, 0.95), found

    def _detect_feed_post(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect viewing a post/content in the feed."""
        has_likes = 'likes' in all_text or 'liked by' in all_text
        has_comments = any('comments' in d for d in descs) or 'comment' in texts or 'comment' in descs
        has_suggested = 'suggested' in all_text
        has_photo_by = 'photo by' in all_text or 'reel by' in all_text
        has_turn_sound = 'turn sound on' in all_text
        has_like_button = any(d.lower() == 'like' for d in descs)
        has_photo_n_of = any('photo' in d.lower() and 'of' in d.lower() for d in descs)
        has_visit_profile = 'visit instagram profile' in all_text
        has_sponsored = 'sponsored' in all_text
        has_watch_more = 'watch more' in all_text or 'watch again' in all_text

        score = 0
        found = []

        # Strong signal: Turn sound on + Like button = definitely viewing content
        if has_turn_sound and has_like_button:
            score += 0.55  # Boosted from 0.5 to ensure we hit threshold with comments
            found.append('video_with_like')
        else:
            if has_turn_sound:
                score += 0.25
                found.append('video')
            if has_like_button:
                score += 0.25
                found.append('like_button')

        if has_likes:
            score += 0.2
            found.append('likes')
        if has_comments:
            score += 0.2  # Boosted from 0.15
            found.append('comments')
        if has_suggested:
            score += 0.2
            found.append('suggested')
        if has_photo_by:
            score += 0.15
            found.append('content_by')
        if has_photo_n_of:
            score += 0.1
            found.append('carousel')
        if has_visit_profile:
            score += 0.1
            found.append('visit_profile')
        if has_sponsored:
            score += 0.1
            found.append('sponsored')
        if has_watch_more:
            score += 0.15
            found.append('watch_more')

        return min(score, 0.9), found

    def _detect_story_view(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect story viewing screen."""
        has_send_message = 'send message' in all_text
        has_like_story = 'like story' in all_text
        has_send_story = 'send story' in all_text
        has_reaction = 'reaction' in all_text

        score = 0
        found = []

        if has_send_message:
            score += 0.3
            found.append('send_message')
        if has_like_story:
            score += 0.3
            found.append('like_story')
        if has_send_story:
            score += 0.2
            found.append('send_story')
        if has_reaction:
            score += 0.2
            found.append('reaction')

        return min(score, 0.9), found

    def _detect_reel_view(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect reel/post viewing screen."""
        has_made_with = 'made with edits' in all_text
        has_follow = 'follow' in texts
        has_like = 'like' in texts or 'likes' in all_text
        has_comment = 'comment' in texts or 'comments' in all_text
        has_share = 'share' in texts

        score = 0
        found = []

        if has_made_with:
            score += 0.4
            found.append('made_with_edits')
        if has_follow and has_like:
            score += 0.3
            found.append('follow_like')
        if has_comment:
            score += 0.15
            found.append('comment')
        if has_share:
            score += 0.15
            found.append('share')

        return min(score, 0.9), found

    def _detect_camera_screen(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect camera/recording screen."""
        has_speed = 'speed' in all_text or 'speed selector' in all_text
        has_timer = 'timer' in all_text
        has_flash = 'flash' in all_text
        has_record = 'record' in all_text or 'capture' in all_text
        has_camera_controls = 'flip' in all_text or 'front' in all_text or 'back' in all_text

        score = 0
        found = []

        if has_speed:
            score += 0.25
            found.append('speed')
        if has_timer:
            score += 0.25
            found.append('timer')
        if has_flash:
            score += 0.25
            found.append('flash')
        if has_record or has_camera_controls:
            score += 0.25
            found.append('camera_controls')

        return min(score, 0.9), found


# Convenience function for quick testing
def detect_screen(elements: List[Dict]) -> ScreenType:
    """Quick screen detection returning just the type."""
    detector = ScreenDetector()
    result = detector.detect(elements)
    return result.screen_type


if __name__ == "__main__":
    # Test with sample elements
    test_cases = [
        # Video editing screen
        [
            {'text': 'Swipe up to edit', 'desc': '', 'clickable': False},
            {'text': 'Edit video', 'desc': '', 'clickable': True},
            {'text': 'Next', 'desc': '', 'clickable': True},
        ],
        # Share preview
        [
            {'text': '', 'desc': 'Edit cover', 'clickable': True},
            {'text': 'Write a caption...', 'desc': '', 'clickable': True},
            {'text': 'Share', 'desc': '', 'clickable': True},
        ],
        # Gallery picker
        [
            {'text': 'New reel', 'desc': '', 'clickable': False},
            {'text': 'Recents', 'desc': '', 'clickable': True},
            {'text': '', 'desc': 'Video thumbnail', 'clickable': True},
        ],
    ]

    detector = ScreenDetector()
    for i, elements in enumerate(test_cases, 1):
        result = detector.detect(elements)
        print(f"Test {i}: {result.screen_type.name} (confidence={result.confidence:.2f})")
        print(f"  Rule: {result.matched_rule}, Elements: {result.key_elements}")
