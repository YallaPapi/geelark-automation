# Task ID: 2

**Title:** Implement CSV input parsing and output logging

**Status:** done

**Dependencies:** 1 ✓

**Priority:** high

**Description:** Create robust utilities to read posting instructions from a CSV and log results to an output CSV log file.

**Details:**

Implementation details:
- Define required input columns: `account_name`, `video_path`, `caption`.
- Implement `read_jobs(csv_path: str) -> list[PostJob]` where `PostJob` is a dataclass with `account_name`, `video_path`, `caption`.
- Validate CSV: check mandatory columns exist; trim whitespace; skip or flag empty rows.
- Normalize `video_path` by joining with `video_root_dir` if it is not absolute.
- Implement `append_log_row(log_path, account, video, status, error=None, timestamp=None)` that appends to CSV, creating header if file does not exist.
- Ensure logs are flushed after every job for crash resilience.
- Pseudo-code:
```python
# csv_io.py
from dataclasses import dataclass
import csv, os, datetime

@dataclass
class PostJob:
    account_name: str
    video_path: str
    caption: str

def read_jobs(path: str, video_root_dir: str) -> list[PostJob]:
    jobs = []
    with open(path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row.get('account_name') or not row.get('video_path'):
                continue
            vp = row['video_path']
            if not os.path.isabs(vp):
                vp = os.path.join(video_root_dir, vp)
            jobs.append(PostJob(row['account_name'].strip(), vp, row.get('caption', '')))
    return jobs

def append_log_row(path: str, account: str, video: str, status: str, error: str | None = None):
    file_exists = os.path.exists(path)
    with open(path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['timestamp', 'account', 'video', 'status', 'error'])
        ts = datetime.datetime.utcnow().isoformat()
        writer.writerow([ts, account, video, status, error or ''])
```

**Test Strategy:**

- Unit test `read_jobs` with:
  - Valid CSV.
  - Missing columns (expect exception or empty list based on design).
  - Relative vs absolute video paths.
- Unit test `append_log_row`:
  - First write creates header.
  - Subsequent calls append new rows.
  - Inspect resulting CSV to match expected line count and fields.
- Perform an end-to-end dry run reading a small sample CSV and writing a sample log.
