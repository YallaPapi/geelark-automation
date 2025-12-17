# Task ID: 14

**Title:** Analyze overnight scheduler run results (Dec 11-12)

**Status:** cancelled

**Dependencies:** 2 ✓, 9 ✓

**Priority:** medium

**Description:** Review batch_results_20251211*.csv files and scheduler logs to compute comprehensive metrics including success rates, error patterns, time correlations, and priority fixes needed.

**Details:**

## Implementation Details

### 1. Create analysis script `analyze_scheduler_results.py`

```python
import os
import csv
import json
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Tuple, Optional
import statistics

class SchedulerAnalyzer:
    def __init__(self, csv_pattern: str = "batch_results_20251211*.csv"):
        self.csv_pattern = csv_pattern
        self.records = []
        
    def load_data(self):
        """Load all matching CSV files"""
        import glob
        for filepath in glob.glob(self.csv_pattern):
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    row['source_file'] = filepath
                    row['timestamp_parsed'] = datetime.fromisoformat(row['timestamp']) if row.get('timestamp') else None
                    self.records.append(row)
```

### 2. Metric Calculations

#### Success Rate by Account
```python
def success_rate_by_account(self) -> Dict[str, dict]:
    """Calculate success/fail/error counts per phone/account"""
    by_account = defaultdict(lambda: {'success': 0, 'failed': 0, 'error': 0, 'total': 0})
    for r in self.records:
        account = r.get('phone', 'unknown')
        status = r.get('status', 'unknown')
        by_account[account][status] = by_account[account].get(status, 0) + 1
        by_account[account]['total'] += 1
    # Calculate rates
    for acc, data in by_account.items():
        data['success_rate'] = data['success'] / data['total'] * 100 if data['total'] > 0 else 0
    return dict(sorted(by_account.items(), key=lambda x: x[1]['success_rate']))
```

#### Success Rate by Hour
```python
def success_rate_by_hour(self) -> Dict[int, dict]:
    """Calculate success rates grouped by hour of day"""
    by_hour = defaultdict(lambda: {'success': 0, 'total': 0})
    for r in self.records:
        if r.get('timestamp_parsed'):
            hour = r['timestamp_parsed'].hour
            by_hour[hour]['total'] += 1
            if r.get('status') == 'success':
                by_hour[hour]['success'] += 1
    for hour, data in by_hour.items():
        data['success_rate'] = data['success'] / data['total'] * 100 if data['total'] > 0 else 0
    return dict(sorted(by_hour.items()))
```

#### Error Type Classification
```python
def classify_errors(self) -> Dict[str, List[dict]]:
    """Categorize errors by type based on error message patterns"""
    error_patterns = {
        'upload_timeout': ['Upload timeout', 'status: 1'],
        'uiautomator_crash': ['UiAutomator2', 'instrumentation process is not running', 'crashed'],
        'adb_timeout': ['timed out after', 'adb.exe'],
        'connection_failed': ['connection', 'offline', 'refused'],
        'instagram_blocked': ['action blocked', 'suspended', 'captcha'],
    }
    
    classified = defaultdict(list)
    for r in self.records:
        if r.get('status') in ['error', 'failed']:
            error_msg = r.get('error', '')
            error_type = 'unknown'
            for etype, patterns in error_patterns.items():
                if any(p.lower() in error_msg.lower() for p in patterns):
                    error_type = etype
                    break
            classified[error_type].append(r)
    return dict(classified)
```

#### Average Attempts Before Success
```python
def avg_attempts_before_success(self) -> dict:
    """Calculate average attempts needed for successful posts.
    Requires correlation with scheduler_state.json for attempt tracking."""
    # Load from scheduler_state.json if available
    state_file = "scheduler_state.json"
    attempts_data = []
    try:
        with open(state_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for job in data.get('jobs', []):
            if job.get('status') == 'success':
                attempts_data.append(job.get('attempts', 1))
    except Exception:
        pass
    
    if attempts_data:
        return {
            'mean': statistics.mean(attempts_data),
            'median': statistics.median(attempts_data),
            'max': max(attempts_data),
            'samples': len(attempts_data)
        }
    return {'error': 'No attempt data available'}
```

#### Phones with Highest Failure Rates
```python
def phones_by_failure_rate(self, min_attempts: int = 2) -> List[Tuple[str, float, int]]:
    """Return phones sorted by failure rate (highest first)"""
    rates = self.success_rate_by_account()
    failures = []
    for phone, data in rates.items():
        if data['total'] >= min_attempts:
            failure_rate = 100 - data['success_rate']
            failures.append((phone, failure_rate, data['total']))
    return sorted(failures, key=lambda x: -x[1])
```

#### Time Patterns in Failures
```python
def failure_time_patterns(self) -> dict:
    """Analyze when failures occur - time of day, day of week, gaps between attempts"""
    failures_by_hour = defaultdict(int)
    failures_by_minute_bucket = defaultdict(int)  # 10-min buckets
    
    for r in self.records:
        if r.get('status') in ['error', 'failed'] and r.get('timestamp_parsed'):
            ts = r['timestamp_parsed']
            failures_by_hour[ts.hour] += 1
            bucket = ts.hour * 6 + ts.minute // 10
            failures_by_minute_bucket[bucket] += 1
    
    return {
        'by_hour': dict(failures_by_hour),
        'peak_failure_hour': max(failures_by_hour.items(), key=lambda x: x[1]) if failures_by_hour else None,
        'failure_distribution': failures_by_minute_bucket
    }
```

#### Video Size Correlation (placeholder - needs video file access)
```python
def video_size_correlation(self, video_folder: str = "chunk_01c") -> dict:
    """Correlate video file sizes with success/failure rates.
    Requires access to video files to get sizes."""
    # Map shortcodes to file sizes
    shortcode_sizes = {}
    success_sizes = []
    fail_sizes = []
    
    # Walk video folder to build size map
    for root, dirs, files in os.walk(video_folder):
        for f in files:
            if f.endswith('.mp4'):
                shortcode = f.replace('.mp4', '')
                path = os.path.join(root, f)
                shortcode_sizes[shortcode] = os.path.getsize(path)
    
    for r in self.records:
        shortcode = r.get('shortcode', '')
        if shortcode in shortcode_sizes:
            size_mb = shortcode_sizes[shortcode] / (1024 * 1024)
            if r.get('status') == 'success':
                success_sizes.append(size_mb)
            else:
                fail_sizes.append(size_mb)
    
    return {
        'avg_success_size_mb': statistics.mean(success_sizes) if success_sizes else 0,
        'avg_fail_size_mb': statistics.mean(fail_sizes) if fail_sizes else 0,
        'success_samples': len(success_sizes),
        'fail_samples': len(fail_sizes),
    }
```

### 3. Report Generator

```python
def generate_report(self) -> str:
    """Generate a comprehensive markdown report"""
    report = []
    report.append("# Scheduler Run Analysis Report - Dec 11, 2025\n")
    
    # Overall stats
    total = len(self.records)
    success = sum(1 for r in self.records if r.get('status') == 'success')
    report.append(f"## Overall Statistics")
    report.append(f"- Total attempts: {total}")
    report.append(f"- Successful: {success} ({success/total*100:.1f}%)")
    report.append(f"- Failed/Error: {total - success}")
    
    # Add each metric section...
    # (success by account, by hour, error types, etc.)
    
    # Priority Fixes section
    report.append("\n## Priority Fixes Needed")
    errors = self.classify_errors()
    if errors.get('upload_timeout'):
        report.append("1. **Upload Timeout** - Increase upload timeout beyond 180s or implement chunked upload")
    if errors.get('uiautomator_crash'):
        report.append("2. **UiAutomator2 Crashes** - Implement phone restart recovery per Task 13")
    
    return "\n".join(report)
```

### 4. CLI Interface

```python
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Analyze scheduler results')
    parser.add_argument('--date', default='20251211', help='Date pattern YYYYMMDD')
    parser.add_argument('--output', default='scheduler_analysis_report.md', help='Output report file')
    parser.add_argument('--json', action='store_true', help='Output raw data as JSON')
    
    args = parser.parse_args()
    
    analyzer = SchedulerAnalyzer(f"batch_results_{args.date}*.csv")
    analyzer.load_data()
    
    if args.json:
        data = {
            'by_account': analyzer.success_rate_by_account(),
            'by_hour': analyzer.success_rate_by_hour(),
            'errors': analyzer.classify_errors(),
            'failure_patterns': analyzer.failure_time_patterns(),
        }
        print(json.dumps(data, indent=2, default=str))
    else:
        report = analyzer.generate_report()
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"Report saved to {args.output}")
```

### 5. Files to Read

- `batch_results_20251211*.csv` - All CSV files from Dec 11 runs
- `scheduler_state.json` - For attempt counts and job metadata
- `geelark_batch.log` - For detailed error stack traces and phase timing
- `chunk_01c/` - Video folder for file size analysis

**Test Strategy:**

## Test Strategy

### 1. Data Loading Tests
- Verify all Dec 11 CSV files are found and loaded (expect ~14 files based on glob results)
- Confirm all expected columns are present: shortcode, phone, status, error, timestamp
- Test handling of empty error fields and malformed timestamps

### 2. Metric Calculation Validation
- **Success rate by account**: Cross-reference with manual count from sample CSV files
- **Success rate by hour**: Verify hour extraction from ISO timestamps (e.g., "2025-12-11T18:22:34" → hour 18)
- **Error classification**: Test pattern matching against known error strings:
  - "Upload timeout after 180s (last status: 1)" → upload_timeout
  - "UiAutomator2 server...instrumentation process is not running" → uiautomator_crash
  - "timed out after 30 seconds" → adb_timeout

### 3. Report Verification
- Run analysis and verify report includes all 7 requested metrics
- Compare overall success count with sum across all CSVs
- Verify phones with highest failure rates list shows accounts that appear in error records

### 4. Edge Cases
- Test with empty CSV files
- Test with single-record files
- Test when scheduler_state.json is unavailable or malformed
- Test when video folder doesn't exist (video size correlation should gracefully report 0 samples)

### 5. Manual Spot-Check
```bash
# Quick validation commands
python analyze_scheduler_results.py --json | jq '.by_account | length'
# Should return number of unique accounts

python analyze_scheduler_results.py --json | jq '.errors | keys'
# Should show error type categories found
```

### 6. Cross-Reference with Raw Data
- Compare report findings with direct CSV inspection
- Verify error messages in report match actual error strings from CSVs
- Confirm time patterns align with file timestamps on batch_results_*.csv files
