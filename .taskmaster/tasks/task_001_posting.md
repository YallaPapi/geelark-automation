# Task ID: 1

**Title:** Set up project structure, configuration, and API key management

**Status:** done

**Dependencies:** None

**Priority:** high

**Description:** Initialize a Python project for Geelark Instagram posting automation, including config management for CSV paths, Claude Vision, proxy rotation URL, and 2Captcha keys.

**Details:**

Implementation details:
- Use Python 3.11+.
- Create a package structure, e.g. `geelark_ig_bot/` with modules: `config.py`, `csv_io.py`, `geelark_control.py`, `instagram_flow.py`, `logging_utils.py`, `main.py`.
- Use `python-dotenv` or similar to load secrets from `.env` (ANTHROPIC_API_KEY, CAPTCHA_API_KEY, PROXY_ROTATION_URL, etc.).
- Define a `Config` dataclass in `config.py` holding: `input_csv_path`, `output_log_csv_path`, `video_root_dir`, `proxy_rotation_url`, `anthropic_api_key`, `captcha_api_key`, `geelark_api_base`, `mvp_mode` (single device vs multi-account).
- Add a `requirements.txt` including: `requests`, `pandas` or `python-csv` (standard), `python-dotenv`, `anthropic` (official Claude client), and any chosen Geelark control SDK or ADB wrapper.
- Provide a simple YAML or JSON config file for non-secret settings (file paths, default timeouts, retry counts).
- Pseudo-code example:
```python
# config.py
from dataclasses import dataclass
import os

@dataclass
class Config:
    input_csv_path: str
    output_log_csv_path: str
    video_root_dir: str
    proxy_rotation_url: str
    anthropic_api_key: str
    captcha_api_key: str | None
    geelark_api_base: str
    mvp_mode: bool = True

def load_config() -> Config:
    return Config(
        input_csv_path=os.getenv("INPUT_CSV", "input.csv"),
        output_log_csv_path=os.getenv("OUTPUT_LOG_CSV", "post_log.csv"),
        video_root_dir=os.getenv("VIDEO_ROOT_DIR", "./videos"),
        proxy_rotation_url=os.getenv("PROXY_ROTATION_URL", ""),
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        captcha_api_key=os.getenv("CAPTCHA_API_KEY"),
        geelark_api_base=os.getenv("GEELARK_API_BASE", "http://localhost:8000"),
    )
```

**Test Strategy:**

- Unit test `load_config()` with different environment variable scenarios.
- Verify that secrets are not hardcoded (only read from env/.env).
- Run a dry `python -m geelark_ig_bot.main --dry-run` to confirm project imports and config loading work without runtime errors.
