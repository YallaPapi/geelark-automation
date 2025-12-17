# Prompt 2 – Coupling & Cohesion Analysis for Posters

## Objective
Evaluate the coupling between SmartInstagramPoster, device/Appium controllers, and orchestrator/worker so you can safely introduce BasePoster with minimal regression risk.

## Instructions

1. Identify where SmartInstagramPoster directly calls subprocess/ADB/Appium versus going through DeviceConnectionManager and AppiumUIController.

2. List dependencies from SmartInstagramPoster to:
   - Geelark client,
   - Claude navigator,
   - logging/progress tracker,
   - config loading.

3. Flag any unnecessary or bidirectional coupling that would make it dangerous to move code into posters/.

4. Recommend 2–3 small refactors to:
   - route all device calls via DeviceConnectionManager,
   - keep SmartInstagramPoster focused on "Instagram UI navigation" instead of infra,
   - expose a small surface that a BasePoster adapter can wrap.

## Expected Output
A short report highlighting hidden coupling and suggesting specific interface boundaries to keep posters isolated and easier to test.
