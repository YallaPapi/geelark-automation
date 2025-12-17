# Prompt 4 Response – BasePoster / PostResult API & Error Handling Review

## Objective
Review the BasePoster and PostResult APIs, plus error handling in InstagramPoster, for a system operating at ~100 posts/day across 100+ accounts.

---

## 1. BasePoster Interface Review

### Current Interface (`posters/base_poster.py`)

```python
class BasePoster(ABC):
    @property
    @abstractmethod
    def platform(self) -> str:
        pass

    @abstractmethod
    def connect(self) -> bool:
        pass

    @abstractmethod
    def post(self, video_path: str, caption: str, humanize: bool = False) -> PostResult:
        pass

    @abstractmethod
    def cleanup(self):
        pass
```

### Assessment

| Aspect | Rating | Notes |
|--------|--------|-------|
| Method count | Good | 3 methods + 1 property is minimal and focused |
| Return types | Good | `connect()` returns bool, `post()` returns rich PostResult |
| Parameter clarity | Good | All parameters have clear types and purpose |
| Lifecycle clarity | Good | Clear connect → post → cleanup flow |

### Recommendations

1. **Add optional `pre_flight_check()`** - Returns bool indicating if device is ready for posting without actually starting the flow. Useful for health checks before claiming jobs.

2. **Add `last_result` property** - Allow access to the most recent PostResult for debugging/logging after cleanup.

3. **Consider async support** - For future parallelization improvements, async versions could be beneficial.

---

## 2. PostResult Dataclass Review

### Current Implementation

```python
@dataclass
class PostResult:
    success: bool
    error: Optional[str] = None
    error_type: Optional[str] = None       # e.g., 'suspended', 'adb_timeout'
    error_category: Optional[str] = None   # 'account', 'infrastructure', 'unknown'
    retryable: bool = True
    platform: str = ""
    account: str = ""
    duration_seconds: float = 0.0
    screenshot_path: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
```

### Assessment

| Field | Purpose | Rating | Notes |
|-------|---------|--------|-------|
| `success` | Primary outcome | Essential | Core field |
| `error` | Human-readable message | Essential | Good for logs |
| `error_type` | Specific error code | Good | Enables targeted handling |
| `error_category` | Broad classification | Good | Drives retry logic |
| `retryable` | Quick retry decision | Good | Pre-computed for convenience |
| `platform` | Source identification | Good | Essential for multi-platform |
| `account` | Account identification | Good | Essential for tracking |
| `duration_seconds` | Performance metric | Good | Helps identify slow accounts |
| `screenshot_path` | Debug artifact | Good | Essential for post-mortem |
| `timestamp` | When result occurred | Good | Audit trail |

### Recommended Additional Fields

```python
@dataclass
class PostResult:
    # ... existing fields ...

    # Additional recommended fields:
    job_id: Optional[str] = None          # Link result to specific job
    raw_error: Optional[str] = None       # Full exception traceback/details
    retry_after_seconds: Optional[int] = None  # Suggested retry delay
    metadata: Dict[str, Any] = field(default_factory=dict)  # Extensible data

    @property
    def is_account_error(self) -> bool:
        """Convenience: True if this is an account-level (non-retryable) error."""
        return self.error_category == 'account'

    @property
    def is_infrastructure_error(self) -> bool:
        """Convenience: True if this is an infrastructure (retryable) error."""
        return self.error_category == 'infrastructure'

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization/logging."""
        return {
            'success': self.success,
            'error': self.error,
            'error_type': self.error_type,
            'error_category': self.error_category,
            'retryable': self.retryable,
            'platform': self.platform,
            'account': self.account,
            'duration_seconds': self.duration_seconds,
            'timestamp': self.timestamp,
        }
```

---

## 3. Error Classification Analysis

### Current Instagram Error Mapping (`post_reel_smart.py:421-470`)

```python
error_patterns = {
    'terminated': ['we disabled your account', ...],
    'suspended': ['account has been suspended', ...],
    'id_verification': ['confirm your identity', ...],
    'captcha': ['confirm it\'s you', ...],
    'action_blocked': ['action blocked', ...],
    'logged_out': ['log in to instagram', ...],
    'app_update': ['update instagram', ...],
}
```

### Error Type to Category Mapping

| error_type | error_category | retryable | Notes |
|------------|----------------|-----------|-------|
| `terminated` | account | No | Permanent ban - remove account |
| `suspended` | account | No | Temporary ban - cooldown period |
| `id_verification` | account | No | Manual intervention required |
| `captcha` | account | No | Manual intervention required |
| `action_blocked` | account | Maybe | Could be temporary (hours) |
| `logged_out` | account | No | Needs re-authentication |
| `app_update` | infrastructure | Yes | Update app, then retry |
| `adb_timeout` | infrastructure | Yes | Device/network issue |
| `connection_dropped` | infrastructure | Yes | Network issue |
| `appium_crash` | infrastructure | Yes | Restart Appium |
| `max_steps` | unknown | Yes | UI navigation failed |
| `loop_stuck` | unknown | Yes | UI navigation stuck |

### Current Implementation in InstagramPoster (`posters/instagram_poster.py`)

```python
ACCOUNT_ERROR_TYPES = {'suspended', 'terminated', 'id_verification', 'logged_out', 'captcha'}

# Determine if retryable based on error type
non_retryable = {'suspended', 'terminated', 'id_verification', 'logged_out'}
retryable = error_type not in non_retryable

# Map to category
category = 'account' if error_type in non_retryable else 'infrastructure'
```

### Issues Identified

1. **`captcha` inconsistency** - In `ACCOUNT_ERROR_TYPES` but not in `non_retryable` set. Should be non-retryable since it requires manual intervention.

2. **`action_blocked` ambiguity** - Sometimes temporary (30 min - 24 hours), sometimes permanent. Should have sub-types: `action_blocked_temp`, `action_blocked_perm`.

3. **Duplicate classification logic** - Error classification happens in:
   - `InstagramPoster.post()` (when returning PostResult)
   - `progress_tracker._classify_error()` (when updating job status)
   - `parallel_worker.execute_posting_job()` (exception handling)

### Recommendation: Centralize Error Classification

Create a shared error classifier that all components use:

```python
# posters/error_classifier.py
from dataclasses import dataclass
from typing import Optional, Dict, List

@dataclass
class ErrorClassification:
    error_type: str
    error_category: str  # 'account', 'infrastructure', 'unknown'
    retryable: bool
    retry_after_seconds: Optional[int] = None
    suggested_action: Optional[str] = None

class ErrorClassifier:
    """Platform-agnostic error classifier. Each platform provides patterns."""

    def __init__(self, patterns: Dict[str, List[str]], categories: Dict[str, str]):
        """
        Args:
            patterns: {error_type: [pattern1, pattern2, ...]}
            categories: {error_type: 'account' | 'infrastructure' | 'unknown'}
        """
        self.patterns = patterns
        self.categories = categories

    def classify(self, error_message: str) -> ErrorClassification:
        """Classify an error message."""
        error_lower = error_message.lower()

        for error_type, patterns in self.patterns.items():
            for pattern in patterns:
                if pattern in error_lower:
                    category = self.categories.get(error_type, 'unknown')
                    retryable = category == 'infrastructure'
                    return ErrorClassification(
                        error_type=error_type,
                        error_category=category,
                        retryable=retryable
                    )

        return ErrorClassification(
            error_type='unknown',
            error_category='unknown',
            retryable=True  # Default to retryable for unknown errors
        )

# Usage in InstagramPoster:
INSTAGRAM_ERROR_PATTERNS = {
    'terminated': ['we disabled your account', 'permanently disabled'],
    'suspended': ['account has been suspended', 'account has been disabled'],
    # ...
}

INSTAGRAM_ERROR_CATEGORIES = {
    'terminated': 'account',
    'suspended': 'account',
    'adb_timeout': 'infrastructure',
    # ...
}

classifier = ErrorClassifier(INSTAGRAM_ERROR_PATTERNS, INSTAGRAM_ERROR_CATEGORIES)
```

---

## 4. Worker Integration Simplification

### Current Flow

```python
# parallel_worker.py
result = poster.post(video_path, caption, humanize=True)

if result.success:
    return True, "", None, None
else:
    return False, result.error, result.error_category, result.error_type
```

### Issues

1. **Return tuple is clunky** - 4-tuple is error-prone and hard to extend.
2. **Duplicate error handling** - Exceptions outside `post()` need separate classification.

### Recommendation: Return PostResult Directly

```python
# parallel_worker.py
def execute_posting_job(...) -> PostResult:
    """Execute job and return PostResult directly."""
    try:
        poster = get_poster(platform, account, ...)

        if not poster.connect():
            return PostResult(
                success=False,
                error="Connection failed",
                error_type="connection_failed",
                error_category="infrastructure",
                platform=platform,
                account=account
            )

        return poster.post(video_path, caption, humanize=True)

    except TimeoutError as e:
        return PostResult(
            success=False,
            error=str(e),
            error_type="adb_timeout",
            error_category="infrastructure",
            platform=platform,
            account=account
        )

    # ...
```

Then progress_tracker can work directly with PostResult:

```python
# progress_tracker.py
def update_job_from_result(self, job_id: str, result: PostResult, worker_id: int):
    """Update job status from PostResult."""
    if result.success:
        self.update_job_status(job_id, 'success', worker_id)
    else:
        self.update_job_status(
            job_id, 'failed', worker_id,
            error=result.error,
            error_category=result.error_category,
            error_type=result.error_type,
            retry_delay_minutes=5 if result.retryable else None
        )
```

---

## 5. Summary: Good and Bad Practices

### Good Practices
- PostResult dataclass is well-structured with essential fields
- Error categorization into account/infrastructure is correct
- retryable flag pre-computed in PostResult
- Screenshot capture for debugging
- Duration tracking for performance analysis

### Bad Practices / Areas for Improvement
1. **Duplicate error classification logic** - Should be centralized
2. **`captcha` inconsistency** - Missing from non_retryable set
3. **Return tuple in worker** - Should return PostResult directly
4. **`action_blocked` ambiguity** - Needs sub-types for temp vs perm
5. **No job_id in PostResult** - Harder to correlate results with jobs
6. **No raw_error field** - Full traceback would help debugging

### Implementation Priority

| Fix | Priority | Effort | Impact |
|-----|----------|--------|--------|
| Add `captcha` to non_retryable | High | Low | Prevents wasted retries |
| Centralize error classifier | Medium | Medium | Reduces code duplication |
| Return PostResult from worker | Medium | Medium | Cleaner API |
| Add job_id to PostResult | Low | Low | Better correlation |
| Add raw_error field | Low | Low | Better debugging |

---

## 6. Final Recommendations for TikTokPoster

When implementing TikTokPoster, apply these patterns:

1. **Use same PostResult** - Standardized across platforms
2. **Create TikTok-specific error patterns** - Different error messages
3. **Share ErrorClassifier interface** - Each poster provides its own patterns
4. **Implement same 3-method interface** - connect(), post(), cleanup()
5. **Include platform in PostResult** - Set to "tiktok"
6. **Map TikTok errors to same categories** - 'account' vs 'infrastructure'
