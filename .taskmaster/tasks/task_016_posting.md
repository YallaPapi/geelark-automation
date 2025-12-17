# Task ID: 16

**Title:** Ensure ANDROID_HOME / ANDROID_SDK_ROOT Are Recognized by Appium Server

**Status:** done

**Dependencies:** 11 ✓, 13 ✓

**Priority:** high

**Description:** Make Appium reliably detect the Android SDK by standardizing how ANDROID_HOME and ANDROID_SDK_ROOT are set, exported, and propagated into the Appium server process across all deployment environments.

**Details:**

## Goal
Guarantee that when the Appium server is started (locally, via scripts, or inside workers/containers), it always has valid access to the Android SDK through **ANDROID_HOME** and/or **ANDROID_SDK_ROOT**, so errors like “Neither ANDROID_HOME nor ANDROID_SDK_ROOT environment variable was exported” do not occur.[7][8]

## High-Level Approach
1. **Standardize environment variable configuration** for Android SDK on all supported OSes (Linux/macOS; Windows only if relevant).
2. **Ensure variables are set in a *non-interactive* context** (systemd services, cron, Docker, background workers), not just in interactive shells.[7]
3. **Unify Appium startup** through a single entry point (Python helper or shell script) that validates and, if needed, sets or maps ANDROID_SDK_ROOT/ANDROID_HOME before launching the server.
4. **Add diagnostics** so misconfiguration is obvious in logs.

## Implementation Steps

### 1. Discover Current SDK Paths and Usage
- Inspect how Appium is currently started:
  - Python wrapper (e.g., `post_reel_smart.py` / scheduler), direct `appium` CLI, Docker, or a service unit.
  - Note whether `appium` is started via `subprocess` in Python.
- On at least one working dev machine and one production-like host:
  - Run `echo $ANDROID_HOME` and `echo $ANDROID_SDK_ROOT` (or `set` on Windows) to see what is set.[4][6]
  - Run `sdkmanager --list` from the same shell that starts Appium to confirm SDK accessibility.
  - If using Android Studio, open SDK Manager and capture the **Android SDK Location** to use as canonical ANDROID_HOME.[5][6]

### 2. Standard OS-Level Environment Setup (Best Practices)
Follow current best-practice patterns for SDK env configuration so that Appium’s CLI sees them by default.[2][4][5][6]

**Linux/macOS:**
- In the system or service user profile, set (example):
  ```bash
  export ANDROID_HOME="$HOME/Android/Sdk"
  export ANDROID_SDK_ROOT="$ANDROID_HOME"
  export PATH="$PATH:$ANDROID_HOME/emulator:$ANDROID_HOME/platform-tools:$ANDROID_HOME/tools:$ANDROID_HOME/tools/bin"
  ```[4][5][6]
- Add to the appropriate file for non-interactive shells (e.g., `/etc/profile.d/android-sdk.sh` or the service user’s `.profile`), not just `.bashrc`.

**Windows (if used for Appium host):**
- In *System Properties → Environment Variables*:
  - Add **ANDROID_HOME** and/or **ANDROID_SDK_ROOT** pointing to the SDK directory (e.g., `C:\Users\<User>\AppData\Local\Android\Sdk`).[2][3][5][6]
  - Add to **PATH**:
    - `%ANDROID_HOME%\emulator`
    - `%ANDROID_HOME%\platform-tools`
    - `%ANDROID_HOME%\tools`
    - `%ANDROID_HOME%\tools\bin`[2][5]
- Reboot or restart relevant services after setting system variables.[5]

Document the canonical SDK path and env configuration in `docs/appium_env.md` so all environments can be made consistent.

### 3. Central Appium Launcher With Env Validation
Create a central launcher responsible for starting Appium with a guaranteed-good environment.

**Option A – Shell wrapper (for CLI/containers):**
- Add a script `scripts/start_appium.sh`:
  ```bash
  #!/usr/bin/env bash
  set -euo pipefail

  # 1. Infer or normalize SDK env
  if [[ -z "${ANDROID_HOME:-}" && -n "${ANDROID_SDK_ROOT:-}" ]]; then
    export ANDROID_HOME="$ANDROID_SDK_ROOT"
  elif [[ -z "${ANDROID_SDK_ROOT:-}" && -n "${ANDROID_HOME:-}" ]]; then
    export ANDROID_SDK_ROOT="$ANDROID_HOME"
  fi

  # 2. Fallback: attempt to detect SDK in common locations (optional)
  if [[ -z "${ANDROID_HOME:-}" ]]; then
    for candidate in "$HOME/Android/Sdk" \
                    "$HOME/Library/Android/sdk" \
                    "/usr/local/android-sdk"; do
      if [[ -d "$candidate/platform-tools" ]]; then
        export ANDROID_HOME="$candidate"
        export ANDROID_SDK_ROOT="$candidate"
        break
      fi
    done
  fi

  # 3. Validate
  if [[ -z "${ANDROID_HOME:-}" || ! -d "$ANDROID_HOME/platform-tools" ]]; then
    echo "[FATAL] ANDROID_HOME/ANDROID_SDK_ROOT not set or invalid. Please install Android SDK and configure env vars." >&2
    exit 1
  fi

  export PATH="$PATH:$ANDROID_HOME/emulator:$ANDROID_HOME/platform-tools:$ANDROID_HOME/tools:$ANDROID_HOME/tools/bin"

  echo "[INFO] Using ANDROID_HOME=$ANDROID_HOME" >&2
  echo "[INFO] Using ANDROID_SDK_ROOT=${ANDROID_SDK_ROOT:-$ANDROID_HOME}" >&2

  # 4. Finally run Appium
  exec appium "$@"
  ```
- Ensure all automation (scheduler, local dev docs, CI, systemd unit) uses this script instead of invoking `appium` directly.

**Option B – Python-side launcher (if Appium is started from Python):**
- Implement a helper (e.g., in a shared module `appium_env.py`):
  ```python
  import os
  import shutil
  import subprocess

  class AndroidEnvError(RuntimeError):
      pass

  def ensure_android_env() -> dict:
      env = os.environ.copy()
      home = env.get("ANDROID_HOME")
      root = env.get("ANDROID_SDK_ROOT")

      if not home and root:
          home = root
          env["ANDROID_HOME"] = root
      elif not root and home:
          root = home
          env["ANDROID_SDK_ROOT"] = home

      if not home:
          # Optional: probe common locations
          for candidate in [
              os.path.expanduser("~/Android/Sdk"),
              os.path.expanduser("~/Library/Android/sdk"),
              "/usr/local/android-sdk",
          ]:
              if os.path.isdir(os.path.join(candidate, "platform-tools")):
                  home = root = candidate
                  env["ANDROID_HOME"] = candidate
                  env["ANDROID_SDK_ROOT"] = candidate
                  break

      if not home or not os.path.isdir(os.path.join(home, "platform-tools")):
          raise AndroidEnvError(
              "ANDROID_HOME/ANDROID_SDK_ROOT not set or invalid; install Android SDK and configure env vars."
          )

      pt = os.path.join(home, "platform-tools")
      emulator = os.path.join(home, "emulator")
      tools = os.path.join(home, "tools")
      tools_bin = os.path.join(tools, "bin")
      extra = os.pathsep.join(p for p in [pt, emulator, tools, tools_bin] if os.path.isdir(p))
      if extra:
          env["PATH"] = env.get("PATH", "") + os.pathsep + extra

      return env

  def start_appium_server(args: list[str]) -> subprocess.Popen:
      env = ensure_android_env()
      appium_cmd = shutil.which("appium") or "appium"
      return subprocess.Popen([appium_cmd, *args], env=env)
  ```
- Refactor all places that start Appium (e.g., utilities used by Task 11 and 13 flows) to use `start_appium_server` instead of raw `subprocess.Popen`.

### 4. Integrate with Existing Reliability / Health Logic
- In the same place where Appium health checks and restarts are wired (Task 15) and connection stability is being improved (Task 13), ensure the restart path *also* uses the standardized launcher so restarted servers see the correct env.
- When an Appium startup or health check fails due to env problems (e.g., server logs mention missing `adb` or ANDROID_HOME), log a distinct error code / message so future analysis (Task 14) can differentiate env configuration problems from device/Appium bugs.

### 5. Diagnostics and Logging
- At Appium startup, log the detected **ANDROID_HOME**, **ANDROID_SDK_ROOT**, and whether `adb` is found on PATH (e.g., `which adb` / `where adb`).
- Optionally, run a lightweight `adb version` and `adb devices` check immediately after starting the server and log the output to quickly spot SDK vs. device issues.[4][6]
- Update developer/ops documentation with:
  - Required env vars and their purpose.
  - Example configuration snippets for each OS.
  - How to run `appium-doctor --android` to validate setup before running tests.[1][2][6]

### 6. CI / Container Integration (If Applicable)
- For Docker images, bake the SDK and env variables into the image:
  ```dockerfile
  ENV ANDROID_HOME=/opt/android-sdk \
      ANDROID_SDK_ROOT=/opt/android-sdk
  ENV PATH="$PATH:$ANDROID_HOME/emulator:$ANDROID_HOME/platform-tools:$ANDROID_HOME/tools:$ANDROID_HOME/tools/bin"
  ```
- Ensure the CI job that runs mobile tests uses either the shell or Python launcher above.

## Notes / Best Practices
- Prefer **ANDROID_SDK_ROOT** (more modern) but keep **ANDROID_HOME** for compatibility; set both to the same directory.[7]
- Always ensure that at least `platform-tools` and `emulator` are on PATH for Appium Android testing.[2][4][5][6]
- When changing system environment variables on Windows, restart services or the whole machine so Appium inherits them.[5]

**Test Strategy:**

1. **Env Sanity Checks**
- On each supported OS:
  - Open a shell configured the same way the Appium server is started (service user, CI container, or scheduler process).
  - Run `echo $ANDROID_HOME` / `echo $ANDROID_SDK_ROOT` (or `set ANDROID_` on Windows) and confirm they point to the actual SDK directory.
  - Run `adb version` and confirm it succeeds.
  - Run `appium-doctor --android` and verify there are no Android SDK-related errors.[1][2][6]

2. **Launcher-Level Tests (Shell Wrapper)**
- Temporarily unset ANDROID_HOME/ANDROID_SDK_ROOT, then:
  - Create a mock SDK directory at a common default path with a dummy `platform-tools` folder.
  - Run `scripts/start_appium.sh --log-level debug` and confirm:
    - The script discovers the SDK and sets ANDROID_HOME/ANDROID_SDK_ROOT (check printed logs).
    - `adb` from the mock SDK is picked up (check `which adb` output if added).
- Set only ANDROID_HOME and confirm the wrapper mirrors it to ANDROID_SDK_ROOT and logs both.
- Set only ANDROID_SDK_ROOT and confirm the wrapper mirrors it to ANDROID_HOME.
- Intentionally point ANDROID_HOME to a non-existent directory and verify the script exits non‑zero with a clear fatal error message.

3. **Launcher-Level Tests (Python Helper, if implemented)**
- Unit-test `ensure_android_env()` using `monkeypatch`/`os.environ` manipulation:
  - Case: both vars absent, no SDK dirs → expect `AndroidEnvError`.
  - Case: only ANDROID_HOME set → expect ANDROID_SDK_ROOT to be added and PATH extended.
  - Case: only ANDROID_SDK_ROOT set → expect ANDROID_HOME to be added and PATH extended.
  - Case: neither set but a test SDK directory exists in a probed path → expect both vars to be set to that directory.
- Unit-test `start_appium_server()` by stubbing `subprocess.Popen` and asserting it receives an `env` with properly set ANDROID_HOME/ANDROID_SDK_ROOT and PATH.

4. **Integration Test with Appium and Device**
- From the worker/scheduler context that will run real jobs:
  - Start Appium using the new launcher (shell or Python).
  - Check the Appium server logs to confirm:
    - ANDROID_HOME/ANDROID_SDK_ROOT values are logged as expected.
    - No warnings like "Neither ANDROID_HOME nor ANDROID_SDK_ROOT environment variable was exported" appear.[8]
  - Run a minimal Android session (e.g., from Task 11’s test harness):
    - Create an Appium session to a real or cloud Android device.
    - Verify the session initializes, `adb devices` lists the device, and a simple `driver.get_page_source()` succeeds.

5. **Failure-Mode Regression Test**
- Temporarily misconfigure env (e.g., unset ANDROID_HOME in the service config) and start Appium through the new launcher:
  - Confirm the launcher fails fast with a clear error instead of starting a broken server.
  - Ensure higher-level reliability/health logic (from Task 13 and Task 15) logs an explicit env-configuration error category and does not enter an infinite restart loop.

6. **Documentation Validation**
- Follow the updated `docs/appium_env.md` from a clean machine:
  - Configure the SDK and env exactly as documented.
  - Start Appium using the documented command.
  - Confirm that an Android session can be created without additional manual tweaks, demonstrating the docs are accurate and sufficient.
