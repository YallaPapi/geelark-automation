# Task ID: 12

**Title:** Investigate and fix empty Appium page_source on Android 15 Instagram sessions

**Status:** done

**Dependencies:** 4 ✓, 11 ✓

**Priority:** medium

**Description:** Debug and instrument the Appium-based Android 15 setup so that page_source / dump_ui() returns a non-empty, correctly structured UI hierarchy for the Instagram app, and determine whether issues stem from app launch, hierarchy generation, or XML parsing.

**Details:**

Implementation plan:

1. **Set up a focused Android 15/Appium debug harness**
- Create a standalone Python script or test module (e.g. `debug/appium_source_debug.py`) that:
  - Connects to the same Geelark Android 15 device configuration used in Task 11.
  - Uses the same Appium capabilities (platformName, platformVersion, deviceName/UDID, automationName=UiAutomator2, appPackage/appActivity for Instagram, noReset, etc.).
  - Logs all capabilities and the Appium server version at startup for reproducibility.
- Ensure the harness is runnable independently from the main posting flow to speed up iteration.

2. **Compare Appium page_source vs. uiautomator dump formats**
- Use Appium’s `driver.page_source` and log the raw return value to a file (e.g. `artifacts/appium_source_raw.xml`) for multiple states: before Instagram launch, after launch, and after navigating to a known screen.[2]
- On the same device and screen, use `adb shell uiautomator dump /sdcard/view.xml && adb pull /sdcard/view.xml artifacts/uiautomator_view.xml` and compare:
  - Root element tag names and attributes (`hierarchy`, `node`, bounds, text, resource-id, content-desc).
  - Character encoding and XML declaration.
  - Presence/absence of expected views (e.g., Instagram home feed, buttons, bottom nav).
- Document differences in a short markdown note (`docs/appium_vs_uiautomator.md`), highlighting any fields Appium normalizes or omits and confirming that Appium is returning **application hierarchy XML**, not a raw uiautomator dump.[2]

3. **Verify that Instagram is truly launching and in foreground**
- From the debug harness, add explicit steps:
  - Call `driver.start_activity(appPackage, appActivity)` (or equivalent) and wait for a few seconds.
  - Use `adb shell dumpsys window windows | grep -E 'mCurrentFocus|mFocusedApp'` to verify that the Instagram activity is in the foreground; log this output.
  - Capture a screenshot via Appium (`driver.get_screenshot_as_png()`) and save to `artifacts/instagram_launch.png`; visually confirm the app is open.
- If Appium connects but Instagram is not foregrounded, log this and add retries/explicit waits (e.g. wait for known accessibility id or resource-id) before calling `page_source`.

4. **Instrument the page_source / dump_ui() call itself**
- Wrap `driver.page_source` and any `dump_ui()` helper used in Task 11 in a small utility (e.g. `debug/get_hierarchy.py`) that:
  - Measures call latency.
  - Catches and logs exceptions.
  - Logs the length of the returned XML string and the first 500–1000 characters.
- Add verbose Appium server logging (log level `debug`) for these calls, capturing:
  - The `Get Page Source` requests and responses.
  - Any UiAutomator2/Android errors when traversing the hierarchy.
- If `page_source` returns an empty hierarchy but no exception, investigate whether this is a known limitation with background apps, webviews, or Android 15 specifics.[1][6]

5. **Check for webview / context or invisible-element issues**
- Enumerate contexts using `driver.contexts` and log them; if a `WEBVIEW_` context exists for Instagram, switch contexts and compare `page_source` results to the native context.
- Confirm whether the expected elements are off-screen or lazily created (e.g., lists or RecyclerViews)[3]; scroll a small amount and re-fetch `page_source` to see if the hierarchy populates.
- Ensure that the harness requests **native context** when expecting native XML, and document how Instagram’s UI composition (native vs webview) affects what Appium can see.[4]

6. **Rule out XML parsing issues in our code**
- If Appium returns non-empty XML but our `dump_ui()` / parser reports no nodes, add unit-level diagnostics:
  - Create a minimal parser module (e.g. `ui_parsing/xml_utils.py`) that loads the raw Appium XML using both `xml.etree.ElementTree` and `lxml` (if available) to handle any namespace/encoding quirks.
  - Log any parsing errors, invalid characters, or namespace prefixes.
  - Add defensive parsing: strip BOMs, normalize encoding to UTF‑8, and handle default namespaces.
- Implement a small CLI (`python -m ui_parsing.debug_parse artifacts/appium_source_raw.xml`) that prints root tag, number of nodes, and a few sample attributes to quickly validate parsing.

7. **Constrain work to Android 15 devices**
- Ensure the harness inspects the device’s SDK level from `adb shell getprop ro.build.version.sdk` and asserts it is 35 (Android 15); otherwise, exit with a clear message.
- If needed, parameterize the target device but keep the scope of this task to documenting and resolving the Android 15 behavior (other OS versions can be future work).

8. **Output and documentation**
- Produce a short troubleshooting doc `docs/android15_appium_empty_source.md` summarizing:
  - Root cause(s): app not foregrounded, context mismatch, Android 15 UiAutomator behavior, or XML parsing bug.
  - The final, recommended way to:
    - Confirm Instagram is open.
    - Fetch reliable page source.
    - Parse and inspect the hierarchy.
  - Any Appium capabilities or flags that improved results (e.g., waitForIdleTimeout, disableWindowAnimation, etc., if changed).
- Expose any reusable utilities (e.g., `get_page_source_debug()`, `assert_instagram_foreground()`) in a `debug_utils` module so other tasks (like Task 11 and orchestrator work) can reuse them.

**Test Strategy:**

1. **Environment and connectivity sanity checks**
- Run the debug harness against an Android 15 Geelark device and verify:
  - Appium session is created without errors.
  - Device SDK level is detected as 35; the script exits with an error on non‑15 devices.

2. **Instagram launch verification**
- Execute the harness with Instagram launch enabled and confirm:
  - `dumpsys window` logs show an Instagram activity in `mCurrentFocus`/`mFocusedApp`.
  - The saved screenshot clearly shows Instagram in the foreground.

3. **Page source vs uiautomator comparison**
- On the same screen, generate both `artifacts/appium_source_raw.xml` and `artifacts/uiautomator_view.xml`.
- Manually inspect or script-compare them to confirm:
  - Non-empty XML in both files.
  - Similar numbers of nodes and presence of expected Instagram UI elements.

4. **XML parsing validation**
- Run the XML parser CLI against `appium_source_raw.xml` and verify it prints:
  - Correct root element name.
  - A positive node count (> 0).
  - At least a few nodes with sensible attributes (e.g., text/resource-id not all empty).
- Intentionally corrupt the XML file (e.g., truncate it) and confirm the parser reports clear parsing errors instead of silently returning zero nodes.

5. **Context and visibility behavior tests**
- From the harness, log `driver.contexts` and switch between native and any webview context, calling `page_source` in each and confirming non-empty output where expected.
- Scroll within Instagram and re-run `page_source`, verifying the hierarchy updates and that elements entering/leaving the visible region appear/disappear from the XML.

6. **Regression guard for empty source condition**
- Add an automated check in the harness that fails if `page_source` length is below a small threshold (e.g., < 1 KB) while Instagram is reported as foreground.
- Run the harness multiple times (at least 5) and confirm the check consistently passes on Android 15.

7. **Documentation review**
- Have a team member follow `docs/android15_appium_empty_source.md` on a fresh environment and verify they can reproduce the debug steps and obtain non-empty page source and parsed node counts without additional help.
