# Task ID: 7

**Title:** Orchestrate Instagram posting flow with device control and Claude Vision

**Status:** done

**Dependencies:** 2 ✓, 4 ✓, 5 ✓, 6 ✓

**Priority:** high

**Description:** Combine CSV jobs, Geelark control, proxy rotation, and Claude Vision navigation to automate the full Instagram posting flow per row, including caption entry and success verification for one device (MVP).

**Details:**

Implementation details:
- Implement a high-level function `run_post_job(job: PostJob, config: Config, controller: GeelarkDeviceController, navigator: ClaudeNavigator)` that:
  1) Rotates proxy.
  2) Connects to the Geelark device for `job.account_name`.
  3) Ensures the Instagram app is running (`launch_app`).
  4) Transfers the video file to the device via `upload_file` and records the device path.
  5) Enters a loop to perform the posting flow:
     - Take a `screenshot`.
     - Provide `context` to Claude, including:
       - `goal`: "Post the specified video to this Instagram account as a Reel or standard video post."
       - `step_state`: track state such as `{"video_uploaded": false, "caption_pasted": false}`.
       - `video_device_path` and `caption`.
     - Receive `Action` from `ClaudeNavigator`.
     - Map `Action` to `GeelarkDeviceController` calls (`tap`, `type_text`, etc.).
     - Track timeouts and max steps (e.g. 30 steps) to avoid infinite loops.
  6) After `Action.kind == 'done'`, confirm success by having Claude inspect a final screenshot with a `verify_posted` context.
- Ensure that errors (exceptions, invalid actions, timeouts) raise a `PostJobError` that carries a human-readable message.
- Pseudo-code skeleton:
```python
def run_post_job(job, config, controller, navigator):
    rotate_proxy(config.proxy_rotation_url)
    device = controller.connect(job.account_name)
    controller.launch_app(device, app_id="com.instagram.android")
    remote_video_path = controller.upload_file(device, job.video_path, "/sdcard/Download/post_video.mp4")

    state = {"video_uploaded": False, "caption_pasted": False, "remote_video_path": remote_video_path}
    for step in range(30):
        screenshot = controller.screenshot(device)
        context = {"goal": "post_video", "caption": job.caption, "state": state}
        action = navigator.plan_next_action(screenshot, context)
        if action.kind == "tap":
            controller.tap(device, action.x, action.y)
        elif action.kind == "type":
            controller.type_text(device, action.text)
        elif action.kind == "wait":
            time.sleep(action.seconds)
        elif action.kind == "done":
            break
        else:
            raise PostJobError(f"Unknown action: {action.kind}")

    # final verification screenshot
    final_shot = controller.screenshot(device)
    verify_action = navigator.plan_next_action(final_shot, {"goal": "verify_posted"})
    if verify_action.kind != "done":
        raise PostJobError("Unable to verify post was successful")
```
- Make the orchestrator initially target MVP: one device and single job; then scale to loop over all jobs from CSV in `main.py`.
- Capture and return a success/failure status and error message to the caller for logging.

**Test Strategy:**

- Implement integration tests in a `--dry-run` mode where `GeelarkDeviceController` is a mock and `ClaudeNavigator` is replaced by a deterministic fake that returns a scripted sequence of actions; verify steps executed in correct order.
- On a real Geelark device, manually run one job and visually confirm that Instagram opens, video is selected, caption is filled, and post is shared.
- Test failure paths: simulate `upload_file` failure, invalid actions from navigator, and assert that errors propagate to logging.
- Verify that the loop stops when max steps are reached and logs an appropriate error.
