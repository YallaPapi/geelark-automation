# Parallel Execution Guide

## Overview

The parallel execution system allows multiple workers to post to different phones simultaneously, dramatically increasing throughput.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    parallel_orchestrator.py                  │
│                                                              │
│  • Validates no other orchestrators running                  │
│  • Seeds progress file from scheduler_state.json            │
│  • Spawns worker subprocesses                               │
│  • Monitors health and handles shutdown                     │
└─────────────────────────────────────────────────────────────┘
                              │
           ┌──────────────────┼──────────────────┐
           ▼                  ▼                  ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ parallel_worker │ │ parallel_worker │ │ parallel_worker │
│   (Worker 0)    │ │   (Worker 1)    │ │   (Worker 2)    │
│                 │ │                 │ │                 │
│ • Appium:4723   │ │ • Appium:4725   │ │ • Appium:4727   │
│ • Port:8200-09  │ │ • Port:8210-19  │ │ • Port:8220-29  │
└────────┬────────┘ └────────┬────────┘ └────────┬────────┘
         │                   │                   │
         ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────┐
│              parallel_progress.csv (file-locked)             │
│                                                              │
│  job_id │ account │ status  │ worker_id │ ...               │
│  ───────┼─────────┼─────────┼───────────┤                   │
│  DMx123 │ phone1  │ success │ 0         │                   │
│  DMx124 │ phone2  │ claimed │ 1         │                   │
│  DMx125 │ phone3  │ pending │           │                   │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Prepare Jobs

Add jobs to scheduler state:

```bash
python posting_scheduler.py \
    --add-folder chunk_01 \
    --add-accounts phone1 phone2 phone3
```

### 2. Start Parallel Workers

```bash
python parallel_orchestrator.py --workers 3 --run
```

### 3. Monitor Progress

```bash
# Check status
python parallel_orchestrator.py --status

# View live logs
tail -f logs/worker_0.log logs/worker_1.log logs/worker_2.log
```

### 4. Stop Workers

```bash
# Graceful shutdown (Ctrl+C in orchestrator terminal)
# Or force stop:
python parallel_orchestrator.py --stop-all
```

---

## Command Reference

### parallel_orchestrator.py

```bash
# Start N workers
python parallel_orchestrator.py --workers 3 --run

# Check current status
python parallel_orchestrator.py --status

# Stop all workers and phones
python parallel_orchestrator.py --stop-all

# Seed progress file only (no workers)
python parallel_orchestrator.py --seed-only

# Show configuration
python parallel_orchestrator.py --show-config
```

**Options:**
| Flag | Description |
|------|-------------|
| `--workers N` | Number of parallel workers (default: 3) |
| `--run` | Start the workers |
| `--status` | Show current progress |
| `--stop-all` | Kill workers and stop phones |
| `--seed-only` | Initialize progress file |
| `--show-config` | Display port allocation |

---

## Worker Configuration

Each worker gets isolated resources:

| Worker | Appium Port | systemPort Range | Log File |
|--------|-------------|------------------|----------|
| 0 | 4723 | 8200-8209 | logs/worker_0.log |
| 1 | 4725 | 8210-8219 | logs/worker_1.log |
| 2 | 4727 | 8220-8229 | logs/worker_2.log |
| N | 4723+(N*2) | 8200+(N*10) | logs/worker_N.log |

---

## Job Claiming Process

1. Worker acquires file lock on progress CSV
2. Scans for first `pending` job
3. Checks account hasn't exceeded daily limit
4. Marks job as `claimed` with worker_id and timestamp
5. Releases lock
6. Processes job
7. Updates status to `success` or `failed`

This ensures no two workers process the same job.

---

## Progress File Format

`parallel_progress.csv`:

```csv
job_id,account,video_path,caption,status,worker_id,claimed_at,completed_at,error,attempts,max_attempts,retry_at,error_type
DMx123,phone1,/path/video.mp4,"Caption",success,0,2024-01-01T10:00:00,2024-01-01T10:02:30,,1,3,,
DMx124,phone2,/path/video.mp4,"Caption",claimed,1,2024-01-01T10:01:00,,,1,3,,
DMx125,phone3,/path/video.mp4,"Caption",pending,,,,,,3,,
```

---

## Error Handling

### Retryable Errors

Jobs that fail with transient errors are marked `retrying` and picked up again after a delay:

```
status=retrying, retry_at=2024-01-01T10:10:00
```

### Non-Retryable Errors

Permanent failures (account issues) are marked `failed` immediately:

- `suspended` - Account suspended
- `captcha` - Verification required
- `loggedout` - Session expired
- `actionblocked` - Rate limited
- `banned` - Account disabled

---

## Graceful Shutdown

When pressing Ctrl+C:

1. Orchestrator catches SIGINT
2. Sends SIGTERM to all workers
3. Workers finish current job or abort
4. Workers stop their Appium servers
5. Orchestrator stops all running phones
6. Exit

**Important:** Always use graceful shutdown to avoid orphaned phones (which cost money).

---

## Troubleshooting

### Workers Not Starting

```bash
# Check if ports are in use
netstat -an | findstr "4723 4725 4727"

# Kill orphaned Appium processes
taskkill /F /IM node.exe
```

### Multiple Orchestrators Error

Only one orchestrator can run at a time:

```bash
# Check for running orchestrators
wmic process where "name='python.exe'" get commandline | findstr "parallel_orchestrator"

# Kill if needed
taskkill /F /PID <pid>
```

### Jobs Not Being Claimed

Check that:
1. Progress file exists and has `pending` jobs
2. Account hasn't hit daily limit (`max_posts_per_account_per_day`)
3. File lock isn't stuck (delete `.lock` file if needed)

### Phone Not Stopping

```bash
# Force stop all phones
python -c "
from geelark_client import GeelarkClient
client = GeelarkClient()
for page in range(1, 20):
    result = client.list_phones(page=page, page_size=100)
    for phone in result['items']:
        if phone['status'] == 1:
            client.stop_phone(phone['id'])
            print(f'Stopped: {phone[\"serialName\"]}')
    if len(result['items']) < 100:
        break
"
```

---

## Performance Tips

1. **Use 3-5 workers** - More workers may overwhelm system resources
2. **Stagger start times** - Workers naturally stagger as they claim jobs
3. **Monitor Appium logs** - Check `logs/appium_N.log` for driver issues
4. **SSD recommended** - File locking performs better on SSDs
5. **Stable internet** - Cloud phones need consistent connectivity
