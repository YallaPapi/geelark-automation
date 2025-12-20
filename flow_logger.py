"""
Flow Logger - Captures detailed posting flow data for pattern analysis.

This module logs every step of the Instagram posting flow to enable
future analysis and construction of deterministic rules.
"""
import os
import json
import hashlib
from datetime import datetime
from typing import List, Dict, Any, Optional


def compute_screen_signature(elements: List[Dict]) -> str:
    """Compute a stable hash signature for a UI screen state.

    Creates a deterministic signature that identifies "same screen"
    across different sessions, even with minor variations.

    Args:
        elements: List of UI element dicts from dump_ui().

    Returns:
        16-character hex string signature.
    """
    if not elements:
        return "empty_screen_000"

    # Build normalized tuples from elements
    tuples = []
    for elem in elements:
        # Normalize text fields
        norm_text = (elem.get('text', '') or '').lower().strip()[:30]
        norm_desc = (elem.get('desc', '') or '').lower().strip()[:30]
        norm_id = (elem.get('id', '') or '').lower()[:20]
        clickable = elem.get('clickable', False)

        # Skip low-signal containers
        if not norm_text and not norm_desc and not clickable:
            continue

        tuples.append((norm_text, norm_desc, norm_id, clickable))

    # Sort for determinism
    tuples.sort()

    # Take first 40 to bound size
    tuples = tuples[:40]

    # Create hash
    sig_str = '|'.join([f"{t[0]}|{t[1]}|{t[2]}|{t[3]}" for t in tuples])
    return hashlib.sha1(sig_str.encode()).hexdigest()[:16]


def summarize_elements(elements: List[Dict], max_elements: int = 20) -> List[Dict]:
    """Create a compact summary of UI elements for logging.

    Args:
        elements: Full list of UI elements.
        max_elements: Maximum number of elements to include.

    Returns:
        List of summarized element dicts.
    """
    summary = []
    for i, elem in enumerate(elements[:max_elements]):
        summary.append({
            'idx': i,
            'text': (elem.get('text', '') or '')[:50],
            'desc': (elem.get('desc', '') or '')[:50],
            'clickable': elem.get('clickable', False),
            'bounds': elem.get('bounds', ''),
            'center': elem.get('center', [])
        })
    return summary


class FlowLogger:
    """Logs posting flow steps to JSONL files for analysis."""

    def __init__(self, account_name: str, log_dir: str = "flow_logs"):
        """Initialize logger for a posting session.

        Args:
            account_name: Instagram account name being posted to.
            log_dir: Directory to store log files.
        """
        self.account_name = account_name
        self.log_dir = log_dir
        self.session_start = datetime.now()
        self.step_count = 0

        # Create log directory if needed
        os.makedirs(log_dir, exist_ok=True)

        # Generate log filename
        timestamp = self.session_start.strftime("%Y%m%d_%H%M%S")
        self.log_file = os.path.join(log_dir, f"{account_name}_{timestamp}.jsonl")

        # Open file handle
        self._file = open(self.log_file, 'a', encoding='utf-8')

        # Log session start
        self._write_entry({
            'event': 'session_start',
            'account': account_name,
            'timestamp': self.session_start.isoformat(),
        })

    def log_step(
        self,
        elements: List[Dict],
        action: Dict[str, Any],
        ai_called: bool = False,
        ai_tokens: int = 0,
        state: Optional[Dict] = None,
        result: str = "pending"
    ):
        """Log a single step in the posting flow.

        Args:
            elements: UI elements at this step.
            action: Action taken (dict with action, element_index, reason, etc.).
            ai_called: Whether AI was called for this step.
            ai_tokens: Number of AI tokens used (if any).
            state: Current posting state (video_uploaded, caption_entered, etc.).
            result: Result of this step (success, failure, pending).
        """
        self.step_count += 1

        entry = {
            'event': 'step',
            'timestamp': datetime.now().isoformat(),
            'step': self.step_count,
            'screen_signature': compute_screen_signature(elements),
            'elements_count': len(elements),
            'elements_summary': summarize_elements(elements),
            'action': action,
            'ai_called': ai_called,
            'ai_tokens': ai_tokens,
            'state': state or {},
            'result': result
        }

        self._write_entry(entry)

    def log_error(self, error_type: str, error_message: str, elements: Optional[List[Dict]] = None):
        """Log an error during posting.

        Args:
            error_type: Type of error (e.g., 'captcha', 'logged_out', 'infrastructure').
            error_message: Detailed error message.
            elements: UI elements when error occurred (if available).
        """
        entry = {
            'event': 'error',
            'timestamp': datetime.now().isoformat(),
            'step': self.step_count,
            'error_type': error_type,
            'error_message': error_message,
            'screen_signature': compute_screen_signature(elements) if elements else None,
            'elements_summary': summarize_elements(elements) if elements else None
        }

        self._write_entry(entry)

    def log_success(self):
        """Log successful post completion."""
        entry = {
            'event': 'success',
            'timestamp': datetime.now().isoformat(),
            'total_steps': self.step_count,
            'duration_seconds': (datetime.now() - self.session_start).total_seconds()
        }

        self._write_entry(entry)

    def log_failure(self, reason: str):
        """Log posting failure.

        Args:
            reason: Reason for failure.
        """
        entry = {
            'event': 'failure',
            'timestamp': datetime.now().isoformat(),
            'total_steps': self.step_count,
            'duration_seconds': (datetime.now() - self.session_start).total_seconds(),
            'reason': reason
        }

        self._write_entry(entry)

    def _write_entry(self, entry: Dict):
        """Write a log entry to the file.

        Args:
            entry: Dict to write as JSON line.
        """
        try:
            self._file.write(json.dumps(entry, ensure_ascii=False) + '\n')
            self._file.flush()  # Ensure data is written immediately
        except Exception as e:
            print(f"  [FLOW LOG ERROR] Failed to write entry: {e}")

    def close(self):
        """Close the log file."""
        try:
            self._file.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


# Convenience function for quick testing
if __name__ == "__main__":
    # Test the logger
    test_elements = [
        {'text': 'Create', 'desc': '', 'id': 'create_btn', 'clickable': True, 'bounds': '[100,200][200,300]', 'center': [150, 250]},
        {'text': 'Home', 'desc': 'Home tab', 'id': 'home_tab', 'clickable': True, 'bounds': '[0,1800][200,1920]', 'center': [100, 1860]},
    ]

    with FlowLogger("test_account") as logger:
        logger.log_step(
            elements=test_elements,
            action={'action': 'tap', 'element_index': 0, 'reason': 'Tap Create button'},
            ai_called=True,
            ai_tokens=500,
            state={'video_uploaded': False, 'caption_entered': False}
        )
        logger.log_success()

    print(f"Test log written to: {logger.log_file}")
