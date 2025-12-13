"""
Appium Server Manager for Multi-Process Workers.

This module handles the lifecycle of Appium server instances:
- Start an Appium server on a specific port with proper Android SDK environment
- Wait for server to become healthy (HTTP /status check)
- Stop server gracefully (SIGTERM then SIGKILL if needed)
- Clean up orphaned UiAutomator2 processes

Each worker process uses this to manage its own dedicated Appium instance.
"""

import os
import sys
import time
import signal
import subprocess
import json
import logging
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError

from parallel_config import WorkerConfig, ParallelConfig

logger = logging.getLogger(__name__)


class AppiumServerError(Exception):
    """Raised when Appium server fails to start or becomes unhealthy."""
    pass


class AppiumServerManager:
    """
    Manages the lifecycle of a single Appium server instance.

    Usage:
        manager = AppiumServerManager(worker_config, parallel_config)
        try:
            manager.start()
            # ... use Appium ...
        finally:
            manager.stop()

    Or as context manager:
        with AppiumServerManager(worker_config, parallel_config) as manager:
            # ... use Appium at manager.appium_url ...
    """

    def __init__(self, worker_config: WorkerConfig, parallel_config: ParallelConfig):
        self.worker_config = worker_config
        self.parallel_config = parallel_config
        self.process: Optional[subprocess.Popen] = None
        self._started = False

    @property
    def appium_url(self) -> str:
        """Get the Appium server URL."""
        return self.worker_config.appium_url

    @property
    def port(self) -> int:
        """Get the Appium server port."""
        return self.worker_config.appium_port

    @property
    def worker_id(self) -> int:
        """Get the worker ID."""
        return self.worker_config.worker_id

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False  # Don't suppress exceptions

    def _get_env(self) -> dict:
        """Get environment variables with Android SDK paths."""
        env = os.environ.copy()
        env.update(self.parallel_config.get_env_vars())
        return env

    def _build_command(self) -> list:
        """Build the Appium server command."""
        # Use full path on Windows to avoid PATH issues in subprocess
        if sys.platform == 'win32':
            npm_path = os.path.join(os.environ.get('APPDATA', ''), 'npm')
            appium_cmd = os.path.join(npm_path, 'appium.cmd')
        else:
            appium_cmd = 'appium'

        return [
            appium_cmd,
            '--address', '127.0.0.1',
            '--port', str(self.port),
            '--log-timestamp',
            '--local-timezone',
            '--allow-insecure', 'uiautomator2:adb_shell',  # Appium v3 format: driver:feature
        ]

    def is_healthy(self, timeout: float = 5.0) -> bool:
        """
        Check if Appium server is running and healthy.

        Args:
            timeout: HTTP request timeout in seconds

        Returns:
            True if server responds with ready=True
        """
        try:
            url = f"{self.appium_url}/status"
            req = Request(url, method='GET')
            with urlopen(req, timeout=timeout) as response:
                data = json.loads(response.read().decode())
                return data.get('value', {}).get('ready', False)
        except (URLError, TimeoutError, json.JSONDecodeError, Exception) as e:
            logger.debug(f"Worker {self.worker_id}: Health check failed: {e}")
            return False

    def wait_for_healthy(self, timeout: float = 30.0, poll_interval: float = 1.0) -> bool:
        """
        Wait for Appium server to become healthy.

        Args:
            timeout: Maximum time to wait in seconds
            poll_interval: Time between health checks

        Returns:
            True if server became healthy, False if timeout
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.is_healthy():
                return True
            time.sleep(poll_interval)
        return False

    def start(self, timeout: float = 30.0) -> None:
        """
        Start the Appium server and wait for it to become healthy.

        If a healthy Appium server is already running on our port, we reuse it
        instead of killing and restarting. This allows efficient handoff between
        runs and workers.

        Args:
            timeout: Maximum time to wait for server to start

        Raises:
            AppiumServerError: If server fails to start or become healthy
        """
        # Check if Appium is already running and healthy on our port
        if self.is_healthy():
            logger.info(f"Worker {self.worker_id}: Reusing existing healthy Appium on port {self.port}")
            self._started = True
            self.process = None  # We didn't start it, so we won't stop it
            return

        # Ensure logs directory exists
        self.parallel_config.ensure_logs_dir()

        # Port is in use but not healthy Appium - kill whatever is there
        self._kill_existing_on_port()

        # Start Appium server
        cmd = self._build_command()
        env = self._get_env()

        logger.info(f"Worker {self.worker_id}: Starting Appium on port {self.port}")
        logger.debug(f"Worker {self.worker_id}: Command: {' '.join(cmd)}")

        try:
            # Open log file for Appium output
            log_file = open(self.worker_config.appium_log_file, 'w', encoding='utf-8')

            if sys.platform == 'win32':
                # Windows: use CREATE_NEW_PROCESS_GROUP for clean shutdown
                self.process = subprocess.Popen(
                    cmd,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    env=env,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                )
            else:
                # Unix: use start_new_session for process group isolation
                self.process = subprocess.Popen(
                    cmd,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    env=env,
                    start_new_session=True
                )

            logger.info(f"Worker {self.worker_id}: Appium started with PID {self.process.pid}")

        except FileNotFoundError:
            raise AppiumServerError(
                f"Worker {self.worker_id}: 'appium' command not found. "
                "Install with: npm install -g appium"
            )
        except Exception as e:
            raise AppiumServerError(f"Worker {self.worker_id}: Failed to start Appium: {e}")

        # Wait for server to become healthy
        if not self.wait_for_healthy(timeout=timeout):
            # Server didn't start - check if process died
            if self.process.poll() is not None:
                raise AppiumServerError(
                    f"Worker {self.worker_id}: Appium process died immediately. "
                    f"Check log: {self.worker_config.appium_log_file}"
                )
            else:
                self.stop()
                raise AppiumServerError(
                    f"Worker {self.worker_id}: Appium didn't become healthy within {timeout}s"
                )

        self._started = True
        logger.info(f"Worker {self.worker_id}: Appium ready on {self.appium_url}")

    def stop(self, timeout: float = 10.0) -> None:
        """
        Stop the Appium server gracefully.

        Args:
            timeout: Maximum time to wait for graceful shutdown before force kill
        """
        if self.process is None:
            return

        logger.info(f"Worker {self.worker_id}: Stopping Appium server (PID {self.process.pid})")

        try:
            # First try graceful shutdown
            if sys.platform == 'win32':
                # Windows: send CTRL_BREAK_EVENT to process group
                self.process.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                # Unix: send SIGTERM
                self.process.terminate()

            # Wait for graceful shutdown
            try:
                self.process.wait(timeout=timeout)
                logger.info(f"Worker {self.worker_id}: Appium stopped gracefully")
            except subprocess.TimeoutExpired:
                # Force kill if graceful shutdown failed
                logger.warning(f"Worker {self.worker_id}: Appium didn't stop gracefully, force killing")
                self.process.kill()
                self.process.wait(timeout=5)

        except Exception as e:
            logger.error(f"Worker {self.worker_id}: Error stopping Appium: {e}")

        finally:
            self.process = None
            self._started = False

    def ensure_healthy(self, restart_timeout: float = 60.0) -> bool:
        """
        Ensure Appium is healthy before processing a job.

        Call this before each job to verify Appium is still responding.
        If unhealthy, attempts to restart automatically.

        Args:
            restart_timeout: Timeout for restart attempt if needed

        Returns:
            True if Appium is healthy (or was restarted successfully)

        Raises:
            AppiumServerError: If Appium cannot be made healthy
        """
        if self.is_healthy():
            return True

        logger.warning(f"Worker {self.worker_id}: Appium unhealthy, attempting restart...")

        # Kill whatever is there (might be hung)
        self._kill_existing_on_port()
        time.sleep(2)

        # Try to restart
        try:
            self.start(timeout=restart_timeout)
            logger.info(f"Worker {self.worker_id}: Appium restarted successfully")
            return True
        except AppiumServerError as e:
            logger.error(f"Worker {self.worker_id}: Failed to restart Appium: {e}")
            raise

    def _kill_existing_on_port(self) -> None:
        """Kill any existing process using our Appium port."""
        if sys.platform == 'win32':
            try:
                # Find process using the port
                result = subprocess.run(
                    ['netstat', '-ano'],
                    capture_output=True, text=True, timeout=10
                )
                for line in result.stdout.split('\n'):
                    if f':{self.port}' in line and 'LISTENING' in line:
                        parts = line.split()
                        if parts:
                            pid = parts[-1]
                            if pid.isdigit():
                                subprocess.run(['taskkill', '/F', '/PID', pid],
                                             capture_output=True, timeout=10)
                                logger.info(f"Worker {self.worker_id}: Killed existing process on port {self.port}")
                                time.sleep(1)
            except Exception as e:
                logger.debug(f"Worker {self.worker_id}: Error killing existing process: {e}")
        else:
            try:
                # Unix: use lsof to find and kill
                result = subprocess.run(
                    ['lsof', '-ti', f':{self.port}'],
                    capture_output=True, text=True, timeout=10
                )
                if result.stdout.strip():
                    for pid in result.stdout.strip().split('\n'):
                        if pid.isdigit():
                            subprocess.run(['kill', '-9', pid], capture_output=True, timeout=5)
                            logger.info(f"Worker {self.worker_id}: Killed existing process on port {self.port}")
                            time.sleep(1)
            except Exception as e:
                logger.debug(f"Worker {self.worker_id}: Error killing existing process: {e}")


def cleanup_all_appium_servers(config: ParallelConfig) -> int:
    """
    Kill all Appium servers for all configured workers.

    Args:
        config: Parallel configuration

    Returns:
        Number of servers killed
    """
    killed = 0
    for worker in config.workers:
        manager = AppiumServerManager(worker, config)
        if manager.is_healthy(timeout=2):
            logger.info(f"Found running Appium on port {worker.appium_port}, killing...")
            manager._kill_existing_on_port()
            killed += 1
    return killed


def check_all_appium_servers(config: ParallelConfig) -> dict:
    """
    Check health status of all configured Appium servers.

    Args:
        config: Parallel configuration

    Returns:
        Dict mapping worker_id to health status
    """
    status = {}
    for worker in config.workers:
        manager = AppiumServerManager(worker, config)
        status[worker.worker_id] = {
            'port': worker.appium_port,
            'healthy': manager.is_healthy(timeout=2),
            'url': worker.appium_url
        }
    return status


if __name__ == "__main__":
    # Demo/test: start and stop an Appium server
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )

    from parallel_config import get_config

    config = get_config(num_workers=1)
    worker = config.workers[0]

    print(f"\nTesting AppiumServerManager for worker {worker.worker_id}")
    print(f"  Port: {worker.appium_port}")
    print(f"  systemPort: {worker.system_port_start}-{worker.system_port_end}")

    manager = AppiumServerManager(worker, config)

    print("\n1. Checking if Appium already running...")
    if manager.is_healthy():
        print("   Appium is already running!")
    else:
        print("   Appium not running, starting...")
        try:
            manager.start(timeout=30)
            print(f"   Appium started successfully at {manager.appium_url}")
        except AppiumServerError as e:
            print(f"   Failed to start: {e}")
            sys.exit(1)

    print("\n2. Health check...")
    print(f"   Healthy: {manager.is_healthy()}")

    print("\n3. Stopping Appium...")
    manager.stop()
    print("   Stopped.")

    print("\n4. Verifying stopped...")
    print(f"   Healthy: {manager.is_healthy()}")
