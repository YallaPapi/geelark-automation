"""
TikTokScreenDetector - Deterministic screen type detection for TikTok posting.

Part of the TikTok Hybrid Posting System.
Replaces AI calls with rule-based detection for known screens.

IMPORTANT: Detection uses TEXT/DESC as PRIMARY signals (stable across TikTok versions).
IDs are only used as BOOST signals since they change between versions (v35 vs v43).

Based on flow logs collected 2024-12-24 from AI-only test runs.
Updated 2024-12-26 for multi-device support (Geelark + GrapheneOS).
"""
from enum import Enum, auto
from typing import List, Dict, Tuple
from dataclasses import dataclass

# Import version-aware ID mappings
from tiktok_id_map import (
    get_all_known_ids,
    get_text_patterns,
    get_desc_patterns,
)


class TikTokScreenType(Enum):
    """Known TikTok screen types during video posting flow."""
    # Main flow screens
    HOME_FEED = auto()           # For You / Following feed
    CREATE_MENU = auto()         # Camera/recording screen
    GALLERY_PICKER = auto()      # Video selection grid
    VIDEO_EDITOR = auto()        # Sounds/Effects screen
    CAPTION_SCREEN = auto()      # Description + Post button
    UPLOAD_PROGRESS = auto()     # "Posting..." progress
    SUCCESS = auto()             # Post complete

    # Popup screens
    POPUP_PERMISSION = auto()    # Camera/audio/storage permissions
    POPUP_DISMISSIBLE = auto()   # Generic dismissible popup

    # Error states
    LOGIN_REQUIRED = auto()      # Logged out / login required
    ACCOUNT_BANNED = auto()      # Account permanently banned
    ACCOUNT_SUSPENDED = auto()   # Temporarily suspended
    CAPTCHA = auto()             # Security verification
    RESTRICTION = auto()         # Posting restricted

    # Fallback
    UNKNOWN = auto()             # Unrecognized screen


@dataclass
class DetectionResult:
    """Result of screen detection with confidence."""
    screen_type: TikTokScreenType
    confidence: float  # 0.0 to 1.0
    matched_rule: str  # Which rule matched
    key_elements: List[str]  # Elements that triggered the match


class TikTokScreenDetector:
    """Detects TikTok screen types from UI elements."""

    # Confidence threshold - below this, return UNKNOWN
    CONFIDENCE_THRESHOLD = 0.7

    def __init__(self):
        """Initialize detector with detection rules."""
        # Detection rules in priority order (first match wins)
        self.rules = [
            # Error states first (highest priority)
            ('ACCOUNT_BANNED', self._detect_banned),
            ('ACCOUNT_SUSPENDED', self._detect_suspended),
            ('LOGIN_REQUIRED', self._detect_login_required),
            ('CAPTCHA', self._detect_captcha),
            ('RESTRICTION', self._detect_restriction),

            # Popups (overlay other screens)
            ('POPUP_PERMISSION', self._detect_permission_popup),

            # Progress/success screens
            ('SUCCESS', self._detect_success),
            ('UPLOAD_PROGRESS', self._detect_upload_progress),

            # Main flow screens (order matters)
            # GALLERY_PICKER must come BEFORE POPUP_DISMISSIBLE to avoid
            # false popup detection when gallery has a 'Close' button
            ('CAPTION_SCREEN', self._detect_caption_screen),
            ('VIDEO_EDITOR', self._detect_video_editor),
            ('GALLERY_PICKER', self._detect_gallery_picker),
            ('CREATE_MENU', self._detect_create_menu),
            ('HOME_FEED', self._detect_home_feed),

            # Generic popup detection last (fallback for true popups)
            ('POPUP_DISMISSIBLE', self._detect_dismissible_popup),
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
                screen_type=TikTokScreenType.UNKNOWN,
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
                    screen_type=TikTokScreenType[rule_name],
                    confidence=confidence,
                    matched_rule=rule_name,
                    key_elements=key_elements
                )

            # Track best sub-threshold match for debugging
            if best_result is None or confidence > best_result.confidence:
                best_result = DetectionResult(
                    screen_type=TikTokScreenType[rule_name],
                    confidence=confidence,
                    matched_rule=rule_name,
                    key_elements=key_elements
                )

        # No rule matched with sufficient confidence
        return DetectionResult(
            screen_type=TikTokScreenType.UNKNOWN,
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

    def _has_element_id(self, elements: List[Dict], element_id: str) -> bool:
        """Check if any element has the given ID."""
        return any(e.get('id', '') == element_id for e in elements)

    def _has_element_desc(self, elements: List[Dict], desc: str) -> bool:
        """Check if any element has the given description."""
        return any(desc.lower() in e.get('desc', '').lower() for e in elements)

    def _has_any_id(self, elements: List[Dict], id_list: List[str]) -> bool:
        """Check if any element has any of the given IDs.

        Used for checking multiple version-specific IDs at once.

        Args:
            elements: List of UI elements from dump_ui()
            id_list: List of IDs to check (e.g., ['fpj', 'g19'] for caption field)

        Returns:
            True if any element has any of the specified IDs.
        """
        element_ids = {e.get('id', '') for e in elements}
        return bool(element_ids & set(id_list))

    def _has_any_text(self, texts: List[str], patterns: List[str]) -> bool:
        """Check if any text matches any of the patterns.

        Args:
            texts: List of extracted text content from elements
            patterns: List of text patterns to match (lowercase)

        Returns:
            True if any text contains any of the patterns.
        """
        for text in texts:
            for pattern in patterns:
                if pattern.lower() in text.lower():
                    return True
        return False

    def _has_any_desc(self, elements: List[Dict], patterns: List[str]) -> bool:
        """Check if any element desc matches any of the patterns.

        Args:
            elements: List of UI elements
            patterns: List of desc patterns to match

        Returns:
            True if any element desc contains any of the patterns.
        """
        for el in elements:
            desc = el.get('desc', '').lower()
            for pattern in patterns:
                if pattern.lower() in desc:
                    return True
        return False

    def _get_element_by_id(self, elements: List[Dict], element_id: str) -> Dict:
        """Get element with given ID."""
        for el in elements:
            if el.get('id', '') == element_id:
                return el
        return {}

    # ==================== Error State Detection ====================

    def _detect_banned(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect permanently banned account."""
        markers = [
            'your account was permanently banned',
            'account has been banned',
            'this account was banned',
            'account is banned',
        ]
        found = [m for m in markers if m in all_text]
        if found:
            return 0.98, found
        return 0.0, []

    def _detect_suspended(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect suspended account."""
        markers = [
            'account suspended',
            'temporarily suspended',
            'account has been suspended',
        ]
        found = [m for m in markers if m in all_text]
        if found:
            return 0.95, found
        return 0.0, []

    def _detect_login_required(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect login/logged out screen."""
        markers = [
            'log in to tiktok',
            'sign up for tiktok',
            'phone number or email',
            'log in or sign up',
        ]
        found = [m for m in markers if m in all_text]
        if len(found) >= 2:
            return 0.95, found
        elif len(found) == 1:
            return 0.8, found
        return 0.0, []

    def _detect_captcha(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect captcha/verification screen."""
        markers = [
            'verify you are human',
            'security verification',
            'slide to verify',
            'complete the puzzle',
        ]
        found = [m for m in markers if m in all_text]
        if found:
            return 0.95, found
        return 0.0, []

    def _detect_restriction(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect posting restriction."""
        markers = [
            'you cannot post',
            'posting is restricted',
            'this action is blocked',
            'try again later',
        ]
        found = [m for m in markers if m in all_text]
        if found:
            return 0.85, found
        return 0.0, []

    # ==================== Popup Detection ====================

    def _detect_permission_popup(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect permission dialog popup.

        TikTok shows camera, audio, and storage permission dialogs.
        Key indicators:
        - id='grant_dialog' or 'grant_singleton'
        - id='permission_message' with "Allow TikTok to..."
        - id='permission_allow_foreground_only_button' for "WHILE USING THE APP"
        """
        score = 0.0
        found = []

        # Primary: Permission dialog IDs (high confidence)
        if self._has_element_id(elements, 'grant_dialog'):
            score += 0.5
            found.append('grant_dialog_id')
        if self._has_element_id(elements, 'grant_singleton'):
            score += 0.3
            found.append('grant_singleton_id')
        if self._has_element_id(elements, 'permission_message'):
            score += 0.4
            found.append('permission_message_id')

        # Primary: Allow button (very specific)
        if self._has_element_id(elements, 'permission_allow_foreground_only_button'):
            score += 0.5
            found.append('allow_button_id')

        # Secondary: Permission text patterns
        permission_patterns = [
            'allow tiktok to take pictures',
            'allow tiktok to record audio',
            'allow tiktok to access photos',
        ]
        for pattern in permission_patterns:
            if pattern in all_text:
                score += 0.2
                found.append(pattern[:30])
                break

        # Tertiary: Button text
        if 'while using the app' in all_text:
            score += 0.15
            found.append('while_using_app')
        if 'only this time' in all_text:
            score += 0.1
            found.append('only_this_time')

        return min(score, 0.98), found

    def _detect_dismissible_popup(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect generic dismissible popup.

        Handles permission dialogs, contact prompts, and other dismissible popups.
        """
        # Dismiss markers - include both ASCII and Unicode apostrophe variants
        dismiss_markers = [
            'not now', 'skip', 'maybe later', 'dismiss', 'no thanks',
            "don't allow", "don't allow",  # ASCII and Unicode apostrophe
            'cancel', 'deny', 'later', 'close'
        ]
        found = [m for m in dismiss_markers if m in all_text]

        # Also check for dialog/popup indicators
        has_dialog = any('dialog' in d.lower() for d in descs)

        # Must have dismiss option
        if found:
            # Small popup (fewer elements) = high confidence
            if len(elements) <= 25:
                return 0.90, found + (['dialog'] if has_dialog else [])
            # Larger screen but still has dismiss option
            else:
                return 0.75, found
        # Dialog indicator without clear dismiss text
        elif has_dialog:
            return 0.5, ['dialog_indicator']
        return 0.0, []

    # ==================== Progress/Success Detection ====================

    def _detect_success(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect post success screen.

        Key indicators (from flow logs):
        - Video playback screen with like/comment buttons
        - id='evz' desc='Like video'
        - id='dnk' desc='Read or add comments'
        - id='evm' desc='Like'
        - Profile reference in element desc
        - "Connect with contacts" screen after posting
        - "Invite friends" / "Friends" post-post screens
        """
        score = 0.0
        found = []

        # HIGH PRIORITY: "Connect with contacts" screen (appears after successful post)
        if 'connect with contacts' in all_text or 'connect with friends' in all_text:
            score += 0.8
            found.append('connect_with_contacts')
            return min(score, 0.98), found  # Early return - definitely success

        # HIGH PRIORITY: "Invite friends" screen (appears after successful post)
        if 'invite friends' in all_text and 'friends' in texts:
            score += 0.75
            found.append('invite_friends')
            return min(score, 0.95), found  # Early return - definitely success

        # Primary: Like video button (id='evz')
        if self._has_element_id(elements, 'evz'):
            evz_elem = self._get_element_by_id(elements, 'evz')
            if 'like' in evz_elem.get('desc', '').lower():
                score += 0.4
                found.append('like_video_button')

        # Primary: Comments button (id='dnk')
        if self._has_element_id(elements, 'dnk'):
            dnk_elem = self._get_element_by_id(elements, 'dnk')
            if 'comment' in dnk_elem.get('desc', '').lower():
                score += 0.35
                found.append('comments_button')

        # Secondary: Like icon (id='evm')
        if self._has_element_id(elements, 'evm'):
            score += 0.15
            found.append('like_icon')

        # Secondary: Profile reference
        for elem in elements:
            desc = elem.get('desc', '').lower()
            if 'profile' in desc and elem.get('id') == 'xo5':
                score += 0.15
                found.append('profile_reference')
                break

        # Tertiary: Text markers
        text_markers = [
            'your video is being uploaded',
            'uploaded successfully',
            'video posted',
            'posted!',
        ]
        text_found = [m for m in text_markers if m in all_text]
        if text_found:
            score += 0.3
            found.extend(text_found)

        return min(score, 0.95), found

    def _detect_upload_progress(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect upload in progress screen."""
        markers = [
            'uploading',
            'posting',
            'processing',
        ]
        found = [m for m in markers if m in all_text]

        # Check for progress indicators
        has_progress = any('progress' in e.get('id', '').lower() for e in elements)

        score = 0.0
        if found:
            score += 0.5
        if has_progress:
            score += 0.3
            found.append('progress_indicator')

        return min(score, 0.9), found

    # ==================== Main Flow Detection ====================

    def _detect_caption_screen(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect caption/description entry screen.

        DETECTION PRIORITY (text/desc primary, IDs as boost):
        1. PRIMARY: Text patterns - 'description', 'add description', 'boost views'
        2. PRIMARY: 'Post' button text
        3. SECONDARY: Desc patterns - 'post', 'draft'
        4. TERTIARY: ID boost (version-specific, NOT primary signal)
        """
        score = 0.0
        found = []

        # ===== PRIMARY: Text-based detection (stable across versions) =====

        # Description field text patterns
        description_patterns = get_text_patterns('description_text')
        if self._has_any_text([all_text], description_patterns):
            score += 0.35
            found.append('description_text')

        # Post button text (exact match)
        if any(t.strip() == 'post' for t in texts):
            score += 0.30
            found.append('post_button_text')

        # Title field text
        title_patterns = get_text_patterns('title_text')
        if self._has_any_text([all_text], title_patterns):
            score += 0.15
            found.append('title_text')

        # ===== SECONDARY: Desc-based detection =====

        # Post button desc
        post_desc_patterns = get_desc_patterns('post_desc')
        if self._has_any_desc(elements, post_desc_patterns):
            score += 0.20
            found.append('post_desc')

        # Draft button desc
        draft_desc_patterns = get_desc_patterns('draft_desc')
        if self._has_any_desc(elements, draft_desc_patterns):
            score += 0.10
            found.append('draft_desc')

        # Edit cover text
        cover_patterns = get_text_patterns('cover_text')
        if self._has_any_text([all_text], cover_patterns):
            score += 0.10
            found.append('cover_text')

        # Hashtag/mention text
        if self._has_any_text([all_text], get_text_patterns('hashtag_text')):
            score += 0.05
            found.append('hashtag_text')

        # ===== TERTIARY: ID boost (NOT primary signal) =====

        # Caption field IDs (version-specific: fpj for v35, g19/g1c for v43)
        caption_ids = get_all_known_ids('caption_field')
        if self._has_any_id(elements, caption_ids):
            score += 0.10
            found.append('caption_id_boost')

        # Post button IDs (version-specific: pwo/pvz/pvl for v35, qrb for v43)
        post_ids = get_all_known_ids('post_button')
        if self._has_any_id(elements, post_ids):
            score += 0.10
            found.append('post_id_boost')

        # Edit cover IDs
        cover_ids = get_all_known_ids('edit_cover')
        if self._has_any_id(elements, cover_ids):
            score += 0.05
            found.append('cover_id_boost')

        # Draft button IDs
        draft_ids = get_all_known_ids('drafts')
        if self._has_any_id(elements, draft_ids):
            score += 0.05
            found.append('draft_id_boost')

        # Visibility settings text (additional signal)
        if 'everyone can view' in all_text or 'who can view' in all_text:
            score += 0.10
            found.append('visibility_settings')

        return min(score, 0.95), found

    def _detect_video_editor(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect sounds/effects editor screen.

        DETECTION PRIORITY (text/desc primary, IDs as boost):
        1. PRIMARY: Text patterns - 'add sound', 'effects', 'filters', 'next'
        2. SECONDARY: Edit tool descs - 'effects', 'text', 'stickers'
        3. TERTIARY: ID boost (editor-specific IDs)
        """
        score = 0.0
        found = []

        # ===== PRIMARY: Text-based detection (stable across versions) =====

        # "Add sound" text (note: singular "sound")
        add_sound_patterns = get_text_patterns('add_sound')
        if self._has_any_text([all_text], add_sound_patterns):
            score += 0.30
            found.append('add_sound')

        # Edit tools text (effects, filters, text, stickers)
        edit_tools = get_text_patterns('edit_tools')
        tools_found = sum(1 for tool in edit_tools if tool in all_text)
        if tools_found >= 3:
            score += 0.30
            found.append(f'edit_tools({tools_found})')
        elif tools_found >= 2:
            score += 0.20
            found.append(f'edit_tools({tools_found})')
        elif tools_found >= 1:
            score += 0.10
            found.append(f'edit_tools({tools_found})')

        # Next button text (required for editor)
        editor_next_patterns = get_text_patterns('editor_next')
        if self._has_any_text(texts, editor_next_patterns):
            score += 0.25
            found.append('next_button')

        # ===== SECONDARY: Additional text signals =====

        # AutoCut feature
        if 'autocut' in all_text:
            score += 0.10
            found.append('autocut')

        # Captions editing option
        if 'captions' in all_text:
            score += 0.05
            found.append('captions')

        # ===== TERTIARY: ID boost (NOT primary signal) =====

        # Editor next button IDs
        editor_next_ids = get_all_known_ids('editor_next')
        if self._has_any_id(elements, editor_next_ids):
            score += 0.10
            found.append('next_id_boost')

        # Music indicator IDs
        music_ids = get_all_known_ids('music_indicator')
        if self._has_any_id(elements, music_ids):
            score += 0.05
            found.append('music_id_boost')

        # Add sound button IDs
        add_sound_ids = get_all_known_ids('add_sound')
        if self._has_any_id(elements, add_sound_ids):
            score += 0.05
            found.append('sound_id_boost')

        return min(score, 0.95), found

    def _detect_gallery_picker(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect gallery/video picker screen.

        DETECTION PRIORITY (text/desc primary, IDs as boost):
        1. PRIMARY: Text patterns - 'recents', 'next', 'videos', 'photos'
        2. SECONDARY: Desc patterns - 'close'
        3. TERTIARY: ID boost (gallery-specific IDs)

        NOTE: This must score HIGH enough (>0.75) to beat POPUP_DISMISSIBLE
        which triggers on 'close' button presence.
        """
        score = 0.0
        found = []

        # ===== PRIMARY: Text-based detection (stable across versions) =====

        # Recents text - strong gallery indicator
        recents_patterns = get_text_patterns('recents_text')
        if self._has_any_text(texts, recents_patterns):
            score += 0.40  # Increased from 0.35
            found.append('recents_text')

        # Next button text
        next_patterns = get_text_patterns('next_text')
        if self._has_any_text(texts, next_patterns):
            score += 0.30
            found.append('next_text')

        # Media filter tabs (videos, photos, all, ai gallery)
        media_tabs = ['videos', 'photos', 'all', 'live photos', 'ai gallery']
        found_tabs = [t for t in media_tabs if t in texts]
        if found_tabs:
            # More tabs = higher confidence
            if len(found_tabs) >= 2:
                score += 0.30  # Multiple tabs = strong gallery signal
            else:
                score += 0.15
            found.append(f'media_tabs({len(found_tabs)})')

        # Select multiple option - definitive gallery indicator
        if 'select multiple' in all_text:
            score += 0.15  # Increased from 0.10
            found.append('multi_select')

        # ===== SECONDARY: Desc-based detection =====

        # Close button desc (only add if we have other gallery markers)
        close_patterns = get_desc_patterns('close_desc')
        if self._has_any_desc(elements, close_patterns) and found:
            score += 0.10
            found.append('close_desc')

        # ===== TERTIARY: ID boost (NOT primary signal) =====

        # Recents tab IDs
        recents_ids = get_all_known_ids('recents_tab')
        if self._has_any_id(elements, recents_ids):
            score += 0.10
            found.append('recents_id_boost')

        # Gallery next button IDs
        gallery_next_ids = get_all_known_ids('gallery_next')
        if self._has_any_id(elements, gallery_next_ids):
            score += 0.10
            found.append('next_id_boost')

        # Gallery close IDs
        gallery_close_ids = get_all_known_ids('gallery_close')
        if self._has_any_id(elements, gallery_close_ids):
            score += 0.05
            found.append('close_id_boost')

        # Duration label IDs (video thumbnails)
        duration_ids = get_all_known_ids('duration_label')
        if self._has_any_id(elements, duration_ids):
            score += 0.05
            found.append('duration_id_boost')

        return min(score, 0.95), found

    def _detect_create_menu(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect camera/create menu screen.

        DETECTION PRIORITY (text/desc primary, IDs as boost):
        1. PRIMARY: Text patterns - 'photo', 'text', duration options
        2. PRIMARY: Desc patterns - 'record video', 'add sound', 'close'
        3. TERTIARY: ID boost (camera-specific IDs)
        """
        score = 0.0
        found = []

        # ===== PRIMARY: Text-based detection (stable across versions) =====

        # Photo/Text tab options
        photo_patterns = get_text_patterns('photo_tab')
        text_patterns = get_text_patterns('text_tab')
        if self._has_any_text(texts, photo_patterns):
            score += 0.20
            found.append('photo_tab')
        if self._has_any_text(texts, text_patterns):
            score += 0.15
            found.append('text_tab')

        # Duration options (10m, 60s, 15s, 3m, etc.)
        duration_patterns = get_text_patterns('duration_options')
        duration_found = sum(1 for d in duration_patterns if d in texts)
        if duration_found >= 2:
            score += 0.30
            found.append(f'duration_options({duration_found})')
        elif duration_found >= 1:
            score += 0.15
            found.append('duration_option')

        # ===== SECONDARY: Desc-based detection =====

        # Record video desc
        record_patterns = get_desc_patterns('record_desc')
        if self._has_any_desc(elements, record_patterns):
            score += 0.25
            found.append('record_desc')

        # Add sound desc
        add_sound_patterns = get_desc_patterns('add_sound_desc')
        if self._has_any_desc(elements, add_sound_patterns):
            score += 0.20
            found.append('add_sound_desc')

        # Close button desc
        close_patterns = get_desc_patterns('close_desc')
        if self._has_any_desc(elements, close_patterns):
            score += 0.10
            found.append('close_desc')

        # ===== TERTIARY: ID boost (NOT primary signal) =====

        # Record button IDs
        record_ids = get_all_known_ids('record_button')
        if self._has_any_id(elements, record_ids):
            score += 0.10
            found.append('record_id_boost')

        # Add sound button IDs
        sound_ids = get_all_known_ids('add_sound')
        if self._has_any_id(elements, sound_ids):
            score += 0.05
            found.append('sound_id_boost')

        # Gallery thumbnail IDs
        gallery_ids = get_all_known_ids('gallery_thumb')
        if self._has_any_id(elements, gallery_ids):
            score += 0.10
            found.append('gallery_id_boost')

        # Close button IDs
        close_ids = get_all_known_ids('close_button')
        if self._has_any_id(elements, close_ids):
            score += 0.05
            found.append('close_id_boost')

        return min(score, 0.95), found

    def _detect_home_feed(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect TikTok home feed (For You Page).

        DETECTION PRIORITY (text/desc primary, IDs as boost):
        1. PRIMARY: Text patterns - 'for you', 'following'
        2. PRIMARY: Desc patterns - 'create', 'home', 'profile'
        3. TERTIARY: ID boost (nav button IDs)
        """
        score = 0.0
        found = []

        # ===== PRIMARY: Text-based detection (stable across versions) =====

        # For You tab text
        for_you_patterns = get_text_patterns('for_you_text')
        if self._has_any_text([all_text], for_you_patterns):
            score += 0.30
            found.append('for_you_text')

        # Following tab text
        following_patterns = get_text_patterns('following_text')
        if self._has_any_text([all_text], following_patterns):
            score += 0.20
            found.append('following_text')

        # ===== SECONDARY: Desc-based detection =====

        # Create button desc
        create_patterns = get_desc_patterns('create_desc')
        if self._has_any_desc(elements, create_patterns):
            score += 0.25
            found.append('create_desc')

        # Home button desc
        home_patterns = get_desc_patterns('home_desc')
        if self._has_any_desc(elements, home_patterns):
            score += 0.15
            found.append('home_desc')

        # Profile button desc
        profile_patterns = get_desc_patterns('profile_desc')
        if self._has_any_desc(elements, profile_patterns):
            score += 0.10
            found.append('profile_desc')

        # Search button desc
        search_patterns = get_desc_patterns('search_desc')
        if self._has_any_desc(elements, search_patterns):
            score += 0.05
            found.append('search_desc')

        # ===== TERTIARY: ID boost (NOT primary signal) =====

        # Create button IDs
        create_ids = get_all_known_ids('create_button')
        if self._has_any_id(elements, create_ids):
            score += 0.10
            found.append('create_id_boost')

        # Home nav IDs
        home_ids = get_all_known_ids('home_nav')
        if self._has_any_id(elements, home_ids):
            score += 0.05
            found.append('home_id_boost')

        # Profile nav IDs
        profile_ids = get_all_known_ids('profile_nav')
        if self._has_any_id(elements, profile_ids):
            score += 0.05
            found.append('profile_id_boost')

        # Search button IDs
        search_ids = get_all_known_ids('search_button')
        if self._has_any_id(elements, search_ids):
            score += 0.05
            found.append('search_id_boost')

        return min(score, 0.95), found


# Convenience function for quick testing
def detect_screen(elements: List[Dict]) -> TikTokScreenType:
    """Quick screen detection returning just the type."""
    detector = TikTokScreenDetector()
    result = detector.detect(elements)
    return result.screen_type


if __name__ == "__main__":
    # Test with sample elements from flow logs
    test_cases = [
        # Home feed
        [
            {'text': '', 'desc': 'Create', 'id': 'lxd', 'clickable': True},
            {'text': '', 'desc': 'Home', 'id': 'lxg', 'clickable': True},
            {'text': 'For You', 'desc': '', 'id': 'text1', 'clickable': True},
        ],
        # Permission popup
        [
            {'text': 'Allow TikTok to take pictures and record video?', 'desc': '', 'id': 'permission_message'},
            {'text': 'WHILE USING THE APP', 'desc': '', 'id': 'permission_allow_foreground_only_button'},
        ],
        # Create menu
        [
            {'text': '', 'desc': 'Record video', 'id': 'q76', 'clickable': True},
            {'text': '', 'desc': 'Add sound', 'id': 'd24', 'clickable': True},
            {'text': 'POST', 'desc': '', 'id': 'u33', 'clickable': True},
        ],
        # Gallery picker
        [
            {'text': 'Recents', 'desc': '', 'id': 'x4d', 'clickable': True},
            {'text': 'Next', 'desc': '', 'id': 'tvr', 'clickable': True},
            {'text': 'Videos', 'desc': '', 'id': '', 'clickable': True},
        ],
    ]

    detector = TikTokScreenDetector()
    for i, elements in enumerate(test_cases, 1):
        result = detector.detect(elements)
        print(f"Test {i}: {result.screen_type.name} (confidence={result.confidence:.2f})")
        print(f"  Rule: {result.matched_rule}, Elements: {result.key_elements}")
