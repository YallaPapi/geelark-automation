"""
TikTokScreenDetector - Deterministic screen type detection for TikTok posting.

Part of the TikTok Hybrid Posting System.
Replaces AI calls with rule-based detection for known screens.

Based on flow logs collected 2024-12-24 from AI-only test runs.
"""
from enum import Enum, auto
from typing import List, Dict, Tuple
from dataclasses import dataclass


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
            ('POPUP_DISMISSIBLE', self._detect_dismissible_popup),

            # Progress/success screens
            ('SUCCESS', self._detect_success),
            ('UPLOAD_PROGRESS', self._detect_upload_progress),

            # Main flow screens (order matters)
            # CREATE_MENU MUST be before VIDEO_EDITOR - both have "Add sound"
            # but CREATE_MENU has duration options (10m, 60s, 15s) and PHOTO/TEXT tabs
            ('CAPTION_SCREEN', self._detect_caption_screen),
            ('CREATE_MENU', self._detect_create_menu),  # Check BEFORE VIDEO_EDITOR
            ('VIDEO_EDITOR', self._detect_video_editor),
            ('GALLERY_PICKER', self._detect_gallery_picker),
            ('HOME_FEED', self._detect_home_feed),
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
        """Detect generic dismissible popup."""
        dismiss_markers = ['not now', 'skip', 'maybe later', 'dismiss', 'no thanks',
                          "don't allow", 'cancel']
        found = [m for m in dismiss_markers if m in all_text]

        # Must have dismiss option AND be a small popup (fewer elements)
        if found and len(elements) < 20:
            return 0.85, found
        elif found:
            return 0.6, found
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

        Key indicators (from flow logs):
        - id='fpj' - Description field with 'Add description...' hint
        - id='d1k' text='Edit cover'
        - id='auj' text='Hashtags'
        - id='aui' text='Mention'
        - id='pvl' / id='pvz' / id='pwo' - Post button
        - id='f6a' desc='Save draft'
        """
        score = 0.0
        found = []

        # Primary: Description field (id='fpj') - THE KEY INDICATOR
        if self._has_element_id(elements, 'fpj'):
            fpj_elem = self._get_element_by_id(elements, 'fpj')
            text = fpj_elem.get('text', '').lower()
            if 'description' in text or 'add description' in text or text:
                # Even if it has caption text (filled in), it's still the caption screen
                score += 0.45
                found.append('description_field_fpj')

        # Primary: Post button with IDs (id='pvl' / 'pvz' / 'pwo')
        post_ids = ['pvl', 'pvz', 'pwo']
        for pid in post_ids:
            if self._has_element_id(elements, pid):
                elem = self._get_element_by_id(elements, pid)
                if 'post' in elem.get('text', '').lower() or 'post' in elem.get('desc', '').lower():
                    score += 0.35
                    found.append(f'post_button_{pid}')
                    break

        # Secondary: Edit cover (id='d1k')
        if self._has_element_id(elements, 'd1k'):
            score += 0.1
            found.append('edit_cover')

        # Secondary: Hashtags button (id='auj')
        if self._has_element_id(elements, 'auj'):
            score += 0.1
            found.append('hashtags_button')

        # Secondary: Mention button (id='aui')
        if self._has_element_id(elements, 'aui'):
            score += 0.05
            found.append('mention_button')

        # Secondary: Save draft (id='f6a')
        if self._has_element_id(elements, 'f6a'):
            score += 0.05
            found.append('save_draft')

        # Tertiary: Description hint text (fallback for older flows)
        desc_patterns = [
            'describe your video',
            'add a description',
            'write a caption',
        ]
        for pattern in desc_patterns:
            if pattern in all_text:
                score += 0.2
                found.append(pattern)
                break

        # Tertiary: Post button (text = "Post") - fallback
        if score < 0.7 and 'post' in texts:
            for elem in elements:
                if elem.get('text', '').strip().lower() == 'post':
                    score += 0.25
                    found.append('post_button_text')
                    break

        # Tertiary: Visibility settings
        if 'everyone can view' in all_text:
            score += 0.1
            found.append('visibility_everyone')

        return min(score, 0.98), found

    def _detect_video_editor(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect sounds/effects editor screen.

        After selecting video, before caption screen.

        Geelark key indicators:
        - Editor-specific IDs: fmo, fmh, fms, flf, y48
        - "Add sound" text
        - Effects/Filters/Captions/Stickers

        GrapheneOS v43.1.4 key indicators:
        - id='ntq' text='Next' - Next button
        - id='d88' desc='Music' - Music icon
        - id='ycm' - Music name text
        - id='ntn' - Next button container
        - id='qxr' - Your Story container
        - Right-side editing tools with desc: Edit, Text, Stickers, Effects, etc.
        - "Your Story" text at bottom
        """
        score = 0.0
        found = []

        # PRIMARY: GrapheneOS Next button (id='ntq' with text='Next')
        for el in elements:
            if el.get('id') == 'ntq' and el.get('text', '').lower() == 'next':
                score += 0.4
                found.append('next_button_ntq')
                break

        # PRIMARY: GrapheneOS Music indicator (id='d88' desc='Music')
        if self._has_element_id(elements, 'd88'):
            for el in elements:
                if el.get('id') == 'd88' and 'music' in el.get('desc', '').lower():
                    score += 0.35
                    found.append('music_d88')
                    break

        # PRIMARY: GrapheneOS editing tools (check desc for tool names)
        graphene_tools = ['edit', 'text', 'stickers', 'effects', 'video templates', 'ai meme', 'ai alive']
        found_tools = sum(1 for tool in graphene_tools if tool in all_text)
        if found_tools >= 4:
            score += 0.35
            found.append(f'graphene_tools({found_tools})')
        elif found_tools >= 2:
            score += 0.2
            found.append(f'graphene_tools({found_tools})')

        # PRIMARY: "Your Story" option (GrapheneOS)
        if 'your story' in all_text:
            score += 0.25
            found.append('your_story')

        # PRIMARY: GrapheneOS IDs
        graphene_editor_ids = ['ntq', 'ntn', 'qxr', 'd88', 'ycm', 'ce1', 'w85']
        graphene_id_count = sum(1 for eid in graphene_editor_ids if self._has_element_id(elements, eid))
        if graphene_id_count >= 4:
            score += 0.3
            found.append(f'graphene_ids({graphene_id_count})')
        elif graphene_id_count >= 2:
            score += 0.15
            found.append(f'graphene_ids({graphene_id_count})')

        # SECONDARY: Geelark editor-specific element IDs
        geelark_ids = ['fmo', 'fmh', 'fms', 'flf', 'y48', 'fmu', 'fmw', 'fnx']
        geelark_id_count = sum(1 for eid in geelark_ids if self._has_element_id(elements, eid))
        if geelark_id_count >= 3:
            score += 0.35
            found.append(f'geelark_ids({geelark_id_count})')
        elif geelark_id_count >= 1:
            score += 0.2
            found.append(f'geelark_ids({geelark_id_count})')

        # SECONDARY: "Add sound" text
        if 'add sound' in all_text:
            score += 0.2
            found.append('add_sound')

        # SECONDARY: Effects/Filters options
        if 'effects' in all_text:
            score += 0.15
            found.append('effects')
        if 'filters' in all_text:
            score += 0.1
            found.append('filters')

        # TERTIARY: Captions/Stickers/Text options
        if 'captions' in all_text:
            score += 0.1
            found.append('captions')
        if 'stickers' in all_text:
            score += 0.1
            found.append('stickers')

        # TERTIARY: AutoCut feature
        if 'autocut' in all_text:
            score += 0.1
            found.append('autocut')

        # TERTIARY: Generic Next button check
        has_next = any(e.get('text', '').lower() == 'next' for e in elements)
        if has_next and 'next_button_ntq' not in found:
            score += 0.1
            found.append('next_button_generic')

        return min(score, 0.98), found

    def _detect_gallery_picker(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect gallery/video picker screen.

        Key indicators (from flow logs):
        - id='x4d' with text='Recents' - Gallery selector
        - id='tvr' with text='Next' - Next button
        - id='b6x' with desc='Close' - Gallery close
        - text='Videos' / 'Photos' / 'All' - Filter tabs
        - text='Select multiple' - Multi-select option
        """
        score = 0.0
        found = []

        # Primary: Recents selector (id='x4d')
        if self._has_element_id(elements, 'x4d'):
            recents_elem = self._get_element_by_id(elements, 'x4d')
            if 'recents' in recents_elem.get('text', '').lower():
                score += 0.35
                found.append('recents_selector')

        # Primary: Next button (id='tvr')
        if self._has_element_id(elements, 'tvr'):
            next_elem = self._get_element_by_id(elements, 'tvr')
            if next_elem.get('text', '').lower() == 'next':
                score += 0.35
                found.append('next_button_id')

        # Secondary: Gallery close button (id='b6x')
        if self._has_element_id(elements, 'b6x'):
            score += 0.15
            found.append('gallery_close')

        # Secondary: Media filter tabs
        media_tabs = ['videos', 'photos', 'all', 'live photos']
        found_tabs = [t for t in media_tabs if t in texts]
        if found_tabs:
            score += 0.1
            found.append('media_tabs')

        # Secondary: Select multiple option
        if 'select multiple' in all_text:
            score += 0.1
            found.append('multi_select')

        # Tertiary: Video duration labels (MM:SS format)
        # These indicate video thumbnails are visible
        for elem in elements:
            text = elem.get('text', '')
            if elem.get('id') == 'faj' and ':' in text:
                score += 0.1
                found.append('video_duration')
                break

        return min(score, 0.95), found

    def _detect_create_menu(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect camera/create menu screen.

        Key indicators (from flow logs):
        Geelark:
        - id='q76' with desc='Record video' - Record button
        - id='d24' with desc='Add sound' - Sound button
        - id='j0z' with desc='Close' - Close button
        - id='c_u' - Gallery thumbnail

        GrapheneOS v43.1.4:
        - id='d8a' with desc='Add sound' - Sound button
        - id='r3r' - Gallery thumbnail (center bottom)
        - id='ymg' - Gallery preview (bottom left)
        - Camera options: Flip, Flash, Timer, Layout, Ratio, Retouch
        - PHOTO / TEXT mode tabs (UNIQUE to camera screen!)

        Common:
        - text='POST' / 'CREATE' - Action buttons
        - text='10m' / '60s' / '15s' - Duration options
        """
        score = 0.0
        found = []

        # HIGHEST PRIORITY: PHOTO/TEXT mode tabs - UNIQUE to camera screen!
        # The video editor does NOT have these tabs
        has_photo = 'photo' in texts
        has_text_tab = 'text' in texts  # "TEXT" tab on camera
        if has_photo and has_text_tab:
            score += 0.5  # Very strong indicator
            found.append('photo_text_tabs')
        elif has_photo:
            score += 0.3
            found.append('photo_tab')

        # HIGHEST PRIORITY: Duration options (10m, 60s, 15s) - UNIQUE to camera!
        durations = ['10m', '60s', '15s']
        found_durations = [d for d in durations if d in texts]
        if len(found_durations) >= 2:
            score += 0.45  # Very strong indicator
            found.append('duration_options_multi')
        elif found_durations:
            score += 0.25
            found.append('duration_options')

        # Primary: Record video button (Geelark id='q76')
        if self._has_element_id(elements, 'q76'):
            record_elem = self._get_element_by_id(elements, 'q76')
            if 'record' in record_elem.get('desc', '').lower():
                score += 0.35
                found.append('record_button')

        # Primary: Add sound button
        # Geelark: id='d24', GrapheneOS: id='d8a'
        for sound_id in ['d24', 'd8a']:
            if self._has_element_id(elements, sound_id):
                sound_elem = self._get_element_by_id(elements, sound_id)
                if 'sound' in sound_elem.get('desc', '').lower():
                    score += 0.25
                    found.append(f'add_sound_{sound_id}')
                    break

        # Primary: Gallery thumbnail
        # Geelark: id='c_u', GrapheneOS: id='r3r' or id='ymg'
        for gallery_id in ['c_u', 'r3r', 'ymg']:
            if self._has_element_id(elements, gallery_id):
                score += 0.2
                found.append(f'gallery_{gallery_id}')
                break

        # Secondary: Close button (id='j0z' or id='jix')
        for close_id in ['j0z', 'jix']:
            if self._has_element_id(elements, close_id):
                score += 0.1
                found.append('close_button')
                break

        # Secondary: Camera control buttons (GrapheneOS)
        camera_controls = ['flip', 'flash', 'timer', 'layout', 'ratio', 'retouch']
        found_controls = [c for c in camera_controls if c in all_text]
        if len(found_controls) >= 3:
            score += 0.25
            found.append(f'camera_controls({len(found_controls)})')
        elif found_controls:
            score += 0.1
            found.append('camera_controls')

        # Tertiary: POST/CREATE mode tabs at bottom
        if 'post' in texts and 'create' in texts:
            score += 0.1
            found.append('post_create_tabs')

        return min(score, 0.98), found

    def _detect_home_feed(self, elements, texts, descs, all_text) -> Tuple[float, List[str]]:
        """Detect TikTok home feed (For You Page).

        Key indicators (from flow logs):
        Geelark version:
        - id='lxd' with desc='Create' - Create button in nav
        - id='lxg' with desc='Home' - Home nav button
        - id='lxi' with desc='Profile' - Profile nav button
        - id='lxf' with desc='Friends' - Friends nav button
        - id='lxh' with desc='Inbox' - Inbox nav button
        - id='ia6' with desc='Search' - Search button

        TikTok v43.1.4 (GrapheneOS):
        - id='mkn' with desc='Create' - Create button in nav
        - id='mkq' with desc='Home' - Home nav button
        - id='mks' with desc='Profile' - Profile nav button
        - id='mkp' with desc='Friends' - Friends nav button
        - id='mkr' with desc='Inbox' - Inbox nav button
        - id='irz' with desc='Search' - Search button

        Common:
        - text='For You' / 'Following' - Feed tabs
        """
        score = 0.0
        found = []

        # Primary: Create button in bottom nav
        # Geelark: id='lxd', GrapheneOS v43.1.4: id='mkn'
        create_found = False
        for create_id in ['lxd', 'mkn']:
            if self._has_element_id(elements, create_id):
                create_elem = self._get_element_by_id(elements, create_id)
                if 'create' in create_elem.get('desc', '').lower():
                    score += 0.4
                    found.append('create_button')
                    create_found = True
                    break

        # Primary: Home nav button
        # Geelark: id='lxg', GrapheneOS v43.1.4: id='mkq'
        for home_id in ['lxg', 'mkq']:
            if self._has_element_id(elements, home_id):
                home_elem = self._get_element_by_id(elements, home_id)
                if 'home' in home_elem.get('desc', '').lower():
                    score += 0.2
                    found.append('home_nav')
                    break

        # Secondary: Other nav buttons
        # Profile: Geelark id='lxi', GrapheneOS v43.1.4: id='mks'
        for profile_id in ['lxi', 'mks']:
            if self._has_element_id(elements, profile_id):
                score += 0.1
                found.append('profile_nav')
                break

        # Friends: Geelark id='lxf', GrapheneOS v43.1.4: id='mkp'
        for friends_id in ['lxf', 'mkp']:
            if self._has_element_id(elements, friends_id):
                score += 0.05
                found.append('friends_nav')
                break

        # Inbox: Geelark id='lxh', GrapheneOS v43.1.4: id='mkr'
        for inbox_id in ['lxh', 'mkr']:
            if self._has_element_id(elements, inbox_id):
                score += 0.05
                found.append('inbox_nav')
                break

        # Secondary: Feed tabs
        if 'for you' in all_text:
            score += 0.15
            found.append('for_you_tab')
        if 'following' in all_text:
            score += 0.1
            found.append('following_tab')

        # Tertiary: Search button
        # Geelark: id='ia6', GrapheneOS v43.1.4: id='irz'
        for search_id in ['ia6', 'irz']:
            if self._has_element_id(elements, search_id):
                score += 0.05
                found.append('search_button')
                break

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
