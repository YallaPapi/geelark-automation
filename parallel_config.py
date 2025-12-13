"""
Parallel Worker Configuration for Multi-Process Appium Orchestration.

This module defines the configuration for running multiple posting workers
in parallel, each with its own isolated Appium server instance.

Architecture:
    - Each worker is a separate Python PROCESS (not thread)
    - Each worker gets its own Appium server on a unique port
    - Each worker gets a unique systemPort range for UiAutomator2
    - Workers communicate only via filesystem (CSV progress tracking)
    - No shared memory or threading - true process isolation

Port Allocation Strategy:
    - Appium ports: 4723, 4725, 4727, ... (odd numbers to avoid conflicts)
    - systemPort ranges: 8200-8209, 8210-8219, 8220-8229, ...
    - Each worker reserves 10 systemPorts for UiAutomator2 sessions
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class WorkerConfig:
    """Configuration for a single worker process."""
    worker_id: int
    appium_port: int
    system_port_start: int
    system_port_end: int
    log_file: str
    appium_log_file: str

    @property
    def system_port(self) -> int:
        """Get the primary systemPort for this worker."""
        return self.system_port_start

    @property
    def appium_url(self) -> str:
        """Get the Appium server URL for this worker."""
        return f"http://127.0.0.1:{self.appium_port}"

    def validate(self) -> None:
        """Validate this worker configuration."""
        if self.appium_port < 1024 or self.appium_port > 65535:
            raise ValueError(f"Worker {self.worker_id}: Invalid Appium port {self.appium_port}")
        if self.system_port_start < 1024 or self.system_port_end > 65535:
            raise ValueError(f"Worker {self.worker_id}: Invalid systemPort range")
        if self.system_port_start >= self.system_port_end:
            raise ValueError(f"Worker {self.worker_id}: systemPort start must be < end")


@dataclass
class ParallelConfig:
    """
    Configuration for the parallel posting orchestrator.

    Attributes:
        num_workers: Number of parallel worker processes to run
        workers: List of per-worker configurations
        progress_file: Path to the shared progress CSV (file-locked)
        logs_dir: Directory for worker and Appium logs
        shutdown_timeout: Seconds to wait for workers to finish on shutdown
        job_timeout: Maximum seconds for a single job before timeout
        delay_between_jobs: Seconds to wait between jobs (per worker)
        max_posts_per_account_per_day: Maximum successful posts per account per day (1-4)
        android_sdk_path: Path to Android SDK
        adb_path: Path to ADB executable
    """
    num_workers: int = 3
    workers: List[WorkerConfig] = field(default_factory=list)
    progress_file: str = "parallel_progress.csv"
    logs_dir: str = "logs"
    shutdown_timeout: int = 60
    job_timeout: int = 300  # 5 minutes per job
    delay_between_jobs: int = 10
    max_posts_per_account_per_day: int = 1  # CRITICAL: Default 1, can be 1-4
    max_attempts: int = 3  # Max retry attempts per job
    retry_delay_minutes: float = 5.0  # Minutes to wait before retry
    android_sdk_path: str = r"C:\Users\asus\Downloads\android-sdk"
    adb_path: str = r"C:\Users\asus\Downloads\android-sdk\platform-tools\adb.exe"

    def __post_init__(self):
        """Generate worker configs if not provided."""
        if not self.workers:
            self.workers = self._generate_worker_configs(self.num_workers)
        self._validate()

    def _generate_worker_configs(self, n: int) -> List[WorkerConfig]:
        """
        Generate N worker configurations with non-overlapping resources.

        Port allocation:
            - Appium: 4723, 4725, 4727, ... (odd ports starting from 4723)
            - systemPort: 8200-8209, 8210-8219, 8220-8229, ...
        """
        configs = []
        base_appium_port = 4723
        base_system_port = 8200
        system_port_range = 10  # Each worker gets 10 ports

        for i in range(n):
            worker = WorkerConfig(
                worker_id=i,
                appium_port=base_appium_port + (i * 2),  # 4723, 4725, 4727...
                system_port_start=base_system_port + (i * system_port_range),
                system_port_end=base_system_port + (i * system_port_range) + system_port_range - 1,
                log_file=os.path.join(self.logs_dir, f"worker_{i}.log"),
                appium_log_file=os.path.join(self.logs_dir, f"appium_{i}.log"),
            )
            configs.append(worker)

        return configs

    def _validate(self) -> None:
        """Validate the entire configuration for conflicts."""
        # Validate max_posts_per_account_per_day
        if not 1 <= self.max_posts_per_account_per_day <= 4:
            raise ValueError(f"max_posts_per_account_per_day must be 1-4, got {self.max_posts_per_account_per_day}")

        # Validate each worker
        for worker in self.workers:
            worker.validate()

        # Check for Appium port conflicts
        appium_ports = [w.appium_port for w in self.workers]
        if len(appium_ports) != len(set(appium_ports)):
            raise ValueError("Duplicate Appium ports detected!")

        # Check for systemPort range overlaps
        for i, w1 in enumerate(self.workers):
            for j, w2 in enumerate(self.workers):
                if i >= j:
                    continue
                # Check if ranges overlap
                if (w1.system_port_start <= w2.system_port_end and
                    w2.system_port_start <= w1.system_port_end):
                    raise ValueError(
                        f"Worker {w1.worker_id} and {w2.worker_id} have overlapping systemPort ranges!"
                    )

    def get_worker(self, worker_id: int) -> WorkerConfig:
        """Get configuration for a specific worker."""
        for w in self.workers:
            if w.worker_id == worker_id:
                return w
        raise ValueError(f"Worker {worker_id} not found in configuration")

    def ensure_logs_dir(self) -> None:
        """Create logs directory if it doesn't exist."""
        os.makedirs(self.logs_dir, exist_ok=True)

    def get_env_vars(self) -> dict:
        """Get environment variables needed for Appium/ADB."""
        # Include npm global path for appium command
        npm_path = os.path.join(os.environ.get('APPDATA', ''), 'npm')
        return {
            'ANDROID_HOME': self.android_sdk_path,
            'ANDROID_SDK_ROOT': self.android_sdk_path,
            'PATH': os.pathsep.join([
                os.path.join(self.android_sdk_path, 'platform-tools'),
                npm_path,  # For appium command
                os.environ.get('PATH', '')
            ])
        }


# Default configuration for 3 workers
DEFAULT_CONFIG = ParallelConfig(num_workers=3)


def get_config(num_workers: int = 3) -> ParallelConfig:
    """Get a parallel configuration with the specified number of workers."""
    return ParallelConfig(num_workers=num_workers)


def print_config(config: ParallelConfig) -> None:
    """Print configuration summary."""
    print(f"\n{'='*60}")
    print(f"PARALLEL POSTING CONFIGURATION")
    print(f"{'='*60}")
    print(f"Workers: {config.num_workers}")
    print(f"Progress file: {config.progress_file}")
    print(f"Logs directory: {config.logs_dir}")
    print(f"Max posts per account per day: {config.max_posts_per_account_per_day}")
    print(f"Shutdown timeout: {config.shutdown_timeout}s")
    print(f"Job timeout: {config.job_timeout}s")
    print(f"\nWorker Allocations:")
    print(f"{'-'*60}")
    print(f"{'Worker':<8} {'Appium Port':<12} {'systemPort Range':<20} {'Log File'}")
    print(f"{'-'*60}")
    for w in config.workers:
        print(f"{w.worker_id:<8} {w.appium_port:<12} {w.system_port_start}-{w.system_port_end:<14} {w.log_file}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    # Demo: print configuration for 1, 2, 3, and 5 workers
    for n in [1, 2, 3, 5]:
        config = get_config(n)
        print_config(config)
