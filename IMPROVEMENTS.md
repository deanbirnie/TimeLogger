# Improvements

Non-bug enhancements: things that work today but could be more robust, portable,
testable, or pleasant to use. IDs are referenced from `TODO.md`.

---

## I1 — Installation script *(requested)*

A single `install.sh` that a user can run on a fresh machine to:

- verify prerequisites (`git`, `python >= 3.10`, `uv`),
- create the virtual environment and install dependencies (`uv sync`),
- create `.env` from `.env.example` if it doesn't exist and prompt the user to edit it,
- install/refresh a shell alias that points at the **correct** script path
  (`app/time_logger.py`) using `uv run --project`, written into an idempotent marker block
  in the user's shell rc file.

This directly resolves the README inconsistencies in B13 and becomes the canonical setup
path. Delivered in this change as `install.sh`.

## I2 — Configuration via `.env` instead of hardcoding

Move the hardcoded JIRA base URL (B6) and the timezone (B4) into `.env`
(`JIRA_BASE_URL`, `TIMEZONE`). Update `.env.example` accordingly. Makes the tool usable by
anyone without editing source.

## I3 — Argument parsing for the file path

Currently the path is only ever read from an interactive `input()` prompt. Add `argparse`
so the alias can be used as `logtime "C:\path\to\file.csv"` (already listed in the README's
"Future Features"). Fall back to the prompt when no argument is given.

## I4 — Define a console-script entry point

`pyproject.toml` has no `[project.scripts]`, so there is no packaged entry point; the alias
must reference the file directly. Adding e.g. `timelogger = "app.time_logger:main"` (after
refactoring `__main__` into a `main()`), lets `uv run timelogger` work and simplifies the
alias.

## I5 — HTTP robustness: timeout, retries, session reuse

`requests.request(...)` has no `timeout`, so a network stall hangs the CLI indefinitely.
Add a timeout, a small retry/backoff for transient 5xx/429, and reuse a single
`requests.Session` (also lets `.env`/auth be read once rather than per item — see B5/perf).

## I6 — Structured skip/error reporting for rows

Tie in with B1/B9: instead of silently dropping unparseable rows, collect them with the
reason they failed and surface them in the report ("3 rows skipped: …"). Aligns with the
README "Future Features" idea of remembering un-logged items.

## I7 — Expand test coverage

Only `clean_description` is tested. Add unit tests for `create_datetime` (padding, midnight,
timezone), `create_time_spent`, `create_issue_str`, `create_report` (valid/invalid
partitioning), and `build_data` (including the malformed-row case from B1). These tests
would have caught B1–B3.

## I8 — Trim/clarify dependencies

`pyproject.toml` lists both `dotenv` (0.9.9, a confusingly-named shim) and `python-dotenv`
— only `python-dotenv` is needed. `requests-auth` is declared but the code uses
`requests.auth.HTTPBasicAuth` from `requests` itself, so `requests-auth` appears unused.
Prune to reduce install surface and confusion.

## I9 — Replace `print` with the `logging` module

Swap ad-hoc `print()` calls for `logging` with levels, so success/warning/error output can
be filtered and optionally written to a file. Supports the "remember un-logged items" goal.

## I10 — Run-summary output

Print total time logged per day and per run (from the README "Future Features"), plus a
count of successes/failures at the end, for quick reconciliation against JIRA.

## I11 — Safer confirmation UX

Pair with B10: normalise the prompt response, default to cancel on empty/ambiguous input,
and echo back a short summary ("About to log N items totalling Hh Mm — continue?").

## I12 — Tidy dead/commented code and docstrings

Remove commented-out scaffolding (`# report = report(reader)`, the commented `untagged`
raise, `# print(...)`), complete the truncated `create_datetime` docstring ("Takes"), and
make type hints consistent (B12).

## I13 — Correct `.env.example` guidance

The `DOWNLOAD_DIR` example uses `/wsl/path/...`; under WSL, Windows drives mount at
`/mnt/c/...`. Provide a realistic example and document the trailing-slash requirement more
prominently (or normalise it in code with `os.path.join`).
