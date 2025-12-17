# Prompt 7 – Harden `ProgressTracker` and schema alignment

> The CSV progress file is central to job state. There is a known bug: `seed_from_campaign` does not populate the `pass_number` column even though `COLUMNS` defines it. This can subtly break downstream logic.
>
> Tasks:
> - List the full schema (`COLUMNS`) in `progress_tracker.py` and show where each column is written/updated.
> - Examine `seed_from_campaign` and ensure the dict used to append `new_jobs` matches every column, including `pass_number`.
> - Search for all reads/writes of `pass_number` to see how it is used in retry logic or statistics.
> - Check file-locking mechanisms around the CSV: are there any code paths where reads/writes are performed without acquiring the lock (especially new TikTok paths)?
>
> Output:
> - A corrected `seed_from_campaign` job dict that fully matches `COLUMNS`.
> - A checklist of invariants for the CSV (e.g., non-null `status`, numeric `attempts`, valid `pass_number`).
> - Suggestions for a lightweight "progress file validator" script that can be run before/after campaigns to catch schema drift and corrupt rows.
