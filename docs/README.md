# Geelark Automation Documentation

Automated Instagram Reels posting system using Geelark cloud phones, Appium, and Claude AI.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Documentation Index](#documentation-index)

## Overview

This system automates posting videos to Instagram Reels through Geelark cloud Android phones. It uses:

- **Geelark API** - Cloud phone management (start/stop phones, ADB access, file uploads)
- **Appium** - Android UI automation via UiAutomator2
- **Claude AI** - Intelligent UI analysis and navigation decisions
- **Parallel Workers** - Multi-phone concurrent posting with file-locked job tracking

### Key Features

- **Smart Navigation**: Claude AI analyzes UI screenshots to determine next actions
- **Parallel Execution**: Run multiple workers posting to different phones simultaneously
- **Retry Logic**: Automatic retry with configurable attempts and delays
- **Error Classification**: Distinguishes retryable errors from permanent failures (suspended, banned)
- **Progress Tracking**: File-locked CSV ensures no duplicate posts across workers
- **Humanization**: Optional random actions before posting to appear more natural

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
├── config.py                 # Centralized configuration
├── geelark_client.py         # Geelark API client
├── device_connection.py      # Device connection lifecycle
├── post_reel_smart.py        # Core posting logic + Claude AI
├── claude_analyzer.py        # Claude UI analysis
├── appium_ui_controller.py   # Appium UI interactions
├── progress_tracker.py       # File-locked job tracking
├── parallel_orchestrator.py  # Multi-worker orchestration
├── parallel_worker.py        # Individual worker process
├── parallel_config.py        # Parallel execution config
├── posting_scheduler.py      # Alternative single-threaded scheduler
└── docs/                     # Documentation
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
| [Parallel Execution](parallel-execution.md) | Multi-worker setup and usage |

## Support

- **Issues**: [GitHub Issues](https://github.com/YallaPapi/geelark-automation/issues)
- **Geelark API Docs**: Check `geelark_api.log` for API response debugging
