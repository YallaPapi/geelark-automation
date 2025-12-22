"""
Comprehensive Error Debugger with Screenshots.

Captures EVERYTHING when an error occurs:
- Full screenshot
- Complete error message (no truncation)
- Full stack trace
- UI elements at time of error
- Device state
- All context needed for debugging

All data saved to error_logs/ directory with unique timestamp.
"""

import os
import json
import traceback
from datetime import datetime
from typing import Optional, Dict, List, Any
import base64


class ErrorDebugger:
    """
    Comprehensive error capture for debugging posting failures.

    Usage:
        debugger = ErrorDebugger(account="testaccount", job_id="video123")

        try:
            # ... posting code ...
        except Exception as e:
            debugger.capture_error(
                error=e,
                driver=appium_driver,  # For screenshot
                ui_elements=elements,  # Current UI state
                context={"step": "clicking_button", "caption": caption}
            )
    """

    def __init__(self, account: str, job_id: str, output_dir: str = "error_logs"):
        """
        Initialize error debugger.

        Args:
            account: Instagram account name
            job_id: Job identifier
            output_dir: Directory to save error logs
        """
        self.account = account
        self.job_id = job_id
        self.output_dir = output_dir
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Create output directory
        self.session_dir = os.path.join(output_dir, f"{account}_{self.session_id}")
        os.makedirs(self.session_dir, exist_ok=True)

        # Error counter for this session
        self.error_count = 0

        # Log file for this session
        self.log_file = os.path.join(self.session_dir, "errors.jsonl")

    def capture_error(
        self,
        error: Exception,
        driver=None,
        ui_elements: List[Dict] = None,
        context: Dict[str, Any] = None,
        error_type: str = None,
        phase: str = None
    ) -> str:
        """
        Capture complete error state with screenshot.

        Args:
            error: The exception that occurred
            driver: Appium WebDriver instance (for screenshot)
            ui_elements: List of UI elements at time of error
            context: Additional context dict
            error_type: Classification of error (e.g., 'adb_timeout', 'account_disabled')
            phase: Which phase of posting (e.g., 'connect', 'navigate', 'upload')

        Returns:
            Path to error log file
        """
        self.error_count += 1
        timestamp = datetime.now().isoformat()
        error_id = f"error_{self.error_count:03d}"

        # Build comprehensive error record
        error_record = {
            "error_id": error_id,
            "timestamp": timestamp,
            "account": self.account,
            "job_id": self.job_id,
            "phase": phase or "unknown",
            "error_type": error_type or type(error).__name__,

            # Full error details - NO TRUNCATION
            "error_class": type(error).__name__,
            "error_message": str(error),  # Complete message
            "error_repr": repr(error),
            "stack_trace": traceback.format_exc(),  # Full stack trace

            # Context
            "context": context or {},

            # UI state
            "ui_elements_count": len(ui_elements) if ui_elements else 0,
            "ui_elements": ui_elements,  # Full element data

            # Screenshot info
            "screenshot_file": None,
            "screenshot_base64": None,
        }

        # Capture screenshot if driver available
        if driver:
            try:
                screenshot_file = os.path.join(
                    self.session_dir,
                    f"{error_id}_screenshot.png"
                )
                driver.save_screenshot(screenshot_file)
                error_record["screenshot_file"] = screenshot_file
                print(f"  [DEBUG] Screenshot saved: {screenshot_file}")

                # Also save base64 for embedding in logs
                with open(screenshot_file, "rb") as f:
                    error_record["screenshot_base64"] = base64.b64encode(f.read()).decode()

            except Exception as ss_error:
                error_record["screenshot_error"] = str(ss_error)
                print(f"  [DEBUG] Screenshot failed: {ss_error}")

        # Capture page source if available
        if driver:
            try:
                page_source_file = os.path.join(
                    self.session_dir,
                    f"{error_id}_page_source.xml"
                )
                with open(page_source_file, "w", encoding="utf-8") as f:
                    f.write(driver.page_source)
                error_record["page_source_file"] = page_source_file
            except Exception as ps_error:
                error_record["page_source_error"] = str(ps_error)

        # Save to JSONL log (one error per line)
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(error_record, ensure_ascii=False) + "\n")

        # Also save individual error JSON for easy viewing
        error_json_file = os.path.join(self.session_dir, f"{error_id}.json")
        with open(error_json_file, "w", encoding="utf-8") as f:
            # Don't include base64 in individual file (too large)
            record_copy = {k: v for k, v in error_record.items() if k != "screenshot_base64"}
            json.dump(record_copy, f, indent=2, ensure_ascii=False)

        print(f"  [DEBUG] Error logged: {error_json_file}")

        return error_json_file

    def capture_state(
        self,
        driver=None,
        ui_elements: List[Dict] = None,
        context: Dict[str, Any] = None,
        label: str = "state"
    ) -> str:
        """
        Capture current state (not an error) for debugging.

        Useful for capturing state at key moments even when no error occurs.

        Args:
            driver: Appium WebDriver instance
            ui_elements: Current UI elements
            context: Additional context
            label: Label for this state capture

        Returns:
            Path to state file
        """
        timestamp = datetime.now().strftime("%H%M%S")
        state_id = f"{label}_{timestamp}"

        state_record = {
            "state_id": state_id,
            "timestamp": datetime.now().isoformat(),
            "account": self.account,
            "job_id": self.job_id,
            "label": label,
            "context": context or {},
            "ui_elements": ui_elements,
        }

        # Screenshot
        if driver:
            try:
                screenshot_file = os.path.join(
                    self.session_dir,
                    f"{state_id}_screenshot.png"
                )
                driver.save_screenshot(screenshot_file)
                state_record["screenshot_file"] = screenshot_file
            except:
                pass

        # Save state
        state_file = os.path.join(self.session_dir, f"{state_id}.json")
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state_record, f, indent=2, ensure_ascii=False)

        return state_file

    def log_step(
        self,
        step_name: str,
        success: bool,
        details: Dict[str, Any] = None,
        driver=None
    ):
        """
        Log a step in the posting process.

        Creates a timeline of what happened for debugging.
        """
        step_log_file = os.path.join(self.session_dir, "steps.jsonl")

        step_record = {
            "timestamp": datetime.now().isoformat(),
            "step": step_name,
            "success": success,
            "details": details or {},
        }

        # Capture screenshot on every step for full timeline
        if driver:
            try:
                step_num = sum(1 for _ in open(step_log_file)) if os.path.exists(step_log_file) else 0
                screenshot_file = os.path.join(
                    self.session_dir,
                    f"step_{step_num:03d}_{step_name}.png"
                )
                driver.save_screenshot(screenshot_file)
                step_record["screenshot"] = screenshot_file
            except:
                pass

        with open(step_log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(step_record, ensure_ascii=False) + "\n")

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all errors in this session."""
        return {
            "account": self.account,
            "job_id": self.job_id,
            "session_id": self.session_id,
            "session_dir": self.session_dir,
            "error_count": self.error_count,
            "log_file": self.log_file,
        }


def create_debugger(account: str, job_id: str) -> ErrorDebugger:
    """Factory function to create error debugger."""
    return ErrorDebugger(account=account, job_id=job_id)


# Convenience function for quick error capture
def capture_posting_error(
    account: str,
    job_id: str,
    error: Exception,
    driver=None,
    ui_elements: List[Dict] = None,
    phase: str = None,
    context: Dict[str, Any] = None
) -> str:
    """
    Quick one-shot error capture.

    Creates a debugger and captures the error in one call.

    Returns:
        Path to error log file
    """
    debugger = ErrorDebugger(account=account, job_id=job_id)
    return debugger.capture_error(
        error=error,
        driver=driver,
        ui_elements=ui_elements,
        phase=phase,
        context=context
    )
