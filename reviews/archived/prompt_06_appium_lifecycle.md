# Prompt 6 – Ensure Appium server lifecycle is tied to worker lifecycle

> The system uses `AppiumServerManager` to handle Appium servers per worker. Observed bug: Appium servers on ports 4723, 4725, 4727, 4729, 4731 remain running after the orchestrator exits, but no phones are running.
>
> Tasks:
> - In `parallel_worker.py`, trace every use of `AppiumServerManager`: creation, starting the server, retrieving ports, and shutdown.
> - In `appium_server_manager.py`, document:
>   - How servers are started (command line, subprocess, PID tracking).
>   - How they are stopped (kill by PID, kill by port, or both).
> - Identify any missing `try/finally` or `with`-style blocks where a worker can crash or `sys.exit()` before shutting down its Appium server.
> - Check if the orchestrator ever attempts global Appium cleanup and whether it knows **which** ports belong to which worker/campaign.
>
> Output:
> - A list of all exit paths in `parallel_worker.py` and whether each guarantees stopping the Appium server.
> - Recommended refactor to:
>   - Wrap the entire worker main loop in a `try/finally` that always calls `AppiumServerManager.stop()` or equivalent.
>   - Optionally add a "server lease file" per worker with PID and port, so external cleanup tools can kill orphans safely.
