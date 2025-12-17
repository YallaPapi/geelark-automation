# Task ID: 10

**Title:** MVP validation and scaling to multiple accounts/devices

**Status:** done

**Dependencies:** 4 ✓, 7 ✓, 8 ✓, 9 ✓

**Priority:** medium

**Description:** Validate the MVP by successfully posting one video with caption on a single Geelark device, then extend to handle multiple accounts/devices from the spreadsheet.

**Details:**

Implementation details:
- MVP validation steps:
  - Configure one `account_name` in the CSV, one `video_path`, and a simple caption.
  - Map that account to a Geelark device in the controller configuration.
  - Run the tool and visually confirm that the video is posted with the correct caption.
  - Confirm that the output log records `success` for this job.
- Scaling steps:
  - Extend account-to-device mapping to support many accounts; use a config file like `devices.yaml` with entries `{account_name, device_id}`.
  - In `connect(account_name)`, look up the correct `device_id` and fall back to a default or raise an error if unmapped.
  - If Geelark supports parallel control, optionally add a future-ready abstraction to run jobs concurrently (e.g. via a worker pool); for now keep them sequential to minimize complexity.
  - Ensure that proxy rotation is still called once per job and that rate-limit logic is per account/device.
- Add documentation (README) describing:
  - How to prepare the CSV.
  - How to organize video files.
  - How to configure API keys and device mappings.
  - Known edge cases and limitations.

**Test Strategy:**

- For MVP:
  - Run manual test: verify the real post appears on Instagram from the target account with the expected caption and time.
  - Check that logs show a single `success` entry with accurate timestamp and video path.
- For multi-account:
  - Prepare a CSV with at least 2 accounts mapped to different devices (or sequential runs on same device if that is the Geelark constraint).
  - Run and verify that each account posts its respective video.
  - Inspect logs to ensure each row has correct `account`, `video`, and `status`.
- Perform a small load test with ~10 rows to confirm there are no memory leaks or unhandled exceptions across many iterations.
