# Geelark Automation Documentation

Automated Instagram posting and follow campaigns using Geelark cloud phones, Appium, and hybrid AI+rule-based navigation.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Documentation Index](#documentation-index)

## Overview

This system automates Instagram actions through Geelark cloud Android phones. It supports:

- **Reel Posting** - Automated video posting with captions
- **Follow Campaigns** - Automated following of target accounts

### Technology Stack

- **Geelark API** - Cloud phone management (start/stop phones, ADB access, file uploads)
- **Appium** - Android UI automation via UiAutomator2
- **Hybrid Navigation** - Rule-based screen detection with optional Claude AI fallback
- **Parallel Workers** - Multi-phone concurrent execution with file-locked job tracking

### Key Features

- **Hybrid Navigation**: Rule-based detection eliminates AI API costs for most screens
- **Parallel Execution**: Run multiple workers on different phones simultaneously
- **Retry Logic**: Automatic retry with configurable attempts and delays
- **Error Classification**: Distinguishes retryable errors from permanent failures
- **Progress Tracking**: File-locked CSV ensures no duplicate actions across workers
- **Flow Logging**: JSONL logs for debugging navigation decisions
- **Global Deduplication**: Prevents duplicate follows across campaigns

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Parallel Orchestrator                        │
│                  (parallel_orchestrator.py)                      │
└──────────────────────────┬──────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│   Worker 0    │  │   Worker 1    │  │   Worker 2    │
│ Appium:4723   │  │ Appium:4725   │  │ Appium:4727   │
└───────┬───────┘  └───────┬───────┘  └───────┬───────┘
        │                  │                  │
        ▼                  ▼                  ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│ Cloud Phone A │  │ Cloud Phone B │  │ Cloud Phone C │
│  (Geelark)    │  │  (Geelark)    │  │  (Geelark)    │
└───────────────┘  └───────────────┘  └───────────────┘

        All workers share: parallel_progress.csv (file-locked)
```

### Module Structure

```
geelark-automation/
├── config.py                    # Centralized configuration
├── geelark_client.py            # Geelark API client
├── device_connection.py         # Device connection lifecycle
├── appium_ui_controller.py      # Appium UI interactions
│
├── # Posting System
├── parallel_orchestrator.py     # Multi-worker posting orchestration
├── parallel_worker.py           # Posting worker process
├── post_reel_smart.py           # Core posting logic
├── progress_tracker.py          # Posting job tracking
│
├── # Follow System
├── follow_orchestrator.py       # Multi-worker follow orchestration
├── follow_worker.py             # Follow worker process
├── follow_single.py             # Core follow logic
├── follow_tracker.py            # Follow job tracking
│
├── # Hybrid Navigation (Posting)
├── screen_detector.py           # Posting screen detection
├── action_engine.py             # Posting action rules
├── hybrid_navigator.py          # Posting hybrid coordinator
│
├── # Hybrid Navigation (Follow)
├── follow_screen_detector.py    # Follow screen detection
├── follow_action_engine.py      # Follow action rules
├── hybrid_follow_navigator.py   # Follow hybrid coordinator
│
├── # AI & Logging
├── claude_analyzer.py           # Claude AI fallback
├── flow_logger.py               # JSONL flow logging
│
├── # Infrastructure
├── parallel_config.py           # Parallel execution config
├── appium_server_manager.py     # Appium server lifecycle
└── docs/                        # Documentation
```

## Quick Start

### Prerequisites

1. **Python 3.8+** with pip
2. **Node.js 16+** (for Appium)
3. **Geelark Account** with API access
4. **Anthropic API Key** (for Claude)

### Installation

```bash
# Clone repository
git clone https://github.com/YallaPapi/geelark-automation.git
cd geelark-automation

# Install Python dependencies
pip install -r requirements.txt

# Install Appium globally
npm install -g appium
appium driver install uiautomator2
```

### Environment Setup

Create a `.env` file:

```env
GEELARK_TOKEN=your_geelark_api_token
ANTHROPIC_API_KEY=your_anthropic_api_key
```

### Running

#### Single Post (Testing)

```bash
# Start Appium server first
appium --address 127.0.0.1 --port 4723

# Post a single video
python post_reel_smart.py <phone_name> <video_path> "<caption>"
```

#### Parallel Posting (Production)

```bash
# Add jobs to scheduler state
python posting_scheduler.py --add-folder chunk_01 --add-accounts phone1 phone2 phone3

# Run parallel workers
python parallel_orchestrator.py --workers 3 --run

# Check status
python parallel_orchestrator.py --status

# Stop all workers and phones
python parallel_orchestrator.py --stop-all
```

## Documentation Index

| Document | Description |
|----------|-------------|
| [API Reference](api-reference.md) | GeelarkClient API documentation |
| [Core Modules](modules.md) | SmartInstagramPoster, DeviceConnectionManager, etc. |
| [Configuration](configuration.md) | Config class reference |
| [Parallel Execution](parallel-execution.md) | Multi-worker posting setup |
| [Follow System](follow-system.md) | Follow campaign orchestration |
| [Hybrid Navigation](hybrid-navigation.md) | Rule-based screen detection |

## Support

- **Issues**: [GitHub Issues](https://github.com/YallaPapi/geelark-automation/issues)
- **Geelark API Docs**: Check `geelark_api.log` for API response debugging
