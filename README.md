# Time Logger

A script designed to accept a CSV file from [TimeTagger](https://github.com/almarklein/timetagger) (selfhosted) and post to the work log REST API provided by JIRA. It significantly reduces the amount of time it takes to log time each day, especially when hours are split amongst numerous small tasks.

## Pre-Requisites

This intended to be a CLI script executed from WSL on Windows as this is my personally preferred method. To adapt it to your needs you will need to change the script to accept your preffered input file path (the report from TimeTagger) and adapt the execution process to your specific environment, for example, if you wish to execute the script from CMD or Powershell.

Required:
 - Python >= 3.10
 - WSL (Windows Subsytem for Linux) version 2
 - [uv](https://docs.astral.sh/uv/) (Tooling for Python to manage dependencies & launch the script)
 - A MySQL or MariaDB server reachable from wherever you run the script (self-hosted is fine — this is what stores the ledger of logged items, see "Database setup" below). If you log time from more than one device, point them all at the same server and de-duplication works automatically across all of them.

## Installation

### Quick install (recommended)

CD into your desired directory:
`cd /path/to/directory`

Clone the repo and enter it:
```bash
git clone https://github.com/deanbirnie/TimeLogger.git
cd TimeLogger
```

Run the installer:
`./install.sh`

The script checks prerequisites, creates the virtual environment and installs
dependencies, creates a `.env` from `.env.example` for you to fill in, and adds a
shell alias (default `logtime`) that runs the tool from anywhere. It is safe to
re-run and can be pointed at a different shell:

```bash
./install.sh --command logtime      # choose the alias/command name
./install.sh --rc ~/.zshrc          # target a specific shell rc file
./install.sh --no-alias             # set up the project without touching your shell rc
./install.sh --help                 # see all options
```

After it finishes, edit `.env` with your JIRA details, then reload your shell:
`source ~/.bashrc`   (or `~/.zshrc`)

You can now run the tool with your chosen command (e.g. `logtime`).

### Manual install

If you'd rather set things up by hand:

Create the virtual environment and install dependencies:
`uv sync`

Copy the example config and edit it with your details:
`cp .env.example .env`

Add an alias to your shell config (`~/.bashrc`, `~/.zshrc`, ...). Note the script
lives at `app/time_logger.py`, and `uv run --project` means you don't need to
activate the venv manually:
```bash
logtime() {
    uv run --project /path/to/your/project /path/to/your/project/app/time_logger.py "$@"
}
```

Finally, reload your shell:
`source ~/.bashrc`

## Database setup

The ledger of already-logged items (used to avoid logging the same worklog twice) lives in a MySQL/MariaDB database rather than a local file, so it can be shared across every device you log time from.

Against your MySQL/MariaDB server:

1. Edit the password in `sql/01_create_database.sql`, then run it (as an admin user, e.g. `root`, that can create databases/users):
   `mysql -u root -p < sql/01_create_database.sql`
2. Create the table — also as the admin user, **not** the `timelogger` user created above: that user is deliberately granted only `SELECT`/`INSERT`/`UPDATE` (never `CREATE`), so the running app can never alter its own schema.
   `mysql -u root -p timelogger < sql/02_schema.sql`
3. Set `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD` in your `.env` to match (see `.env.example`) — these should be the `timelogger` app user, not the admin user used above.

Do this once per database (not per device) — every machine you log time from should point at the *same* server so they share one ledger. If the app can't reach the database when you run it, it stops immediately with a clear error rather than logging time it can't record.

### Migrating existing history

If you were using an older version of this tool that stored the ledger as a local `state/logged.json` file, migrate that history into the database with:

```bash
uv run scripts/migrate_ledger_to_db.py path/to/logged.json
```

It's safe to run more than once (already-migrated items are skipped, not duplicated), and you can pass more than one file — e.g. one `logged.json` copied over from each device you'd been using separately:

```bash
uv run scripts/migrate_ledger_to_db.py device1_logged.json device2_logged.json
```

## Usage

Once you've completed the installation instructions, you can run the script from WSL:

First download the time report from TimeTagger or create a CSV file according to the CSV example in the repo.

Then right click on the file in Windows File Explorer wherever it was downloaded to. Select "Copy as path".

Open WSL and use the alias command you configured above (e.g. `logtime`):
`logtime`

Then paste the Windows file path when prompted.

The script will analyse and validate all your work items. If there are any invalid items it will warn you accordingly, the script will not attempt to log these.

The valid work items are then split into two groups: items that were logged on a previous run (skipped) and items that are new. Only the new items are logged. You'll be prompted to continue or cancel — the prompt is `(y/N)`, so `y`/`yes` continues and anything else (including just pressing Enter) cancels.

Each item is logged using the JIRA REST API and there is some reporting to ensure that each item was logged.

Check your output carefully as the script will inform you of any items that JIRA rejected. The status code 201 is returned for success, any other status code will output an error or a warning for you to resolve manually or fix and run again.

Once complete, you can close the WSL terminal/shell.

### Re-running a file & de-duplication

You can safely re-run the same day's file multiple times — and from multiple devices. Every worklog that JIRA accepts (HTTP 201) is recorded in the `logged_worklogs` table (see "Database setup" above), and on subsequent runs those items are skipped — so if you add a few more entries to the same CSV later in the day and re-run, only the newly added items are logged. Because the ledger is a shared database rather than a per-device file, this works the same way whether you're re-running on the same machine or logging the rest of the day from a different one.

An item's identity is `JIRA issue + start time + duration`; the description is deliberately excluded, so fixing a typo in a description and re-running will **not** create a duplicate worklog.

Items are recorded one at a time, only after JIRA confirms them, so a failed item is retried on the next run and an interrupted run never double-logs the items that already succeeded.

If you ever genuinely need to re-log something the ledger already knows about, delete the matching row from `logged_worklogs` (e.g. `DELETE FROM logged_worklogs WHERE jira_issue = 'JIRA-123';`) and run again. Truncating the table resets all history.

### Archiving

Each run that reaches the logging stage copies the source CSV into an archive directory (`archive/` by default), timestamp-prefixed (e.g. `2026-07-29T14-03-05_TimeFile.csv`), so you keep a history of exactly what was processed. The original downloaded file is left untouched.

The archive directory can be overridden in `.env` via `ARCHIVE_DIR` (see `.env.example`). It's a local, per-device directory — unlike the ledger, archived CSVs are not shared between devices. `archive/` is git-ignored.


## Future Features
 - Implement adding invalid work log items to a file and remind user each time the program runs of items that have yet to be logged from the past. Case in point would be if a JIRA issue hasn't yet been created but the user has captured the time and given it a description.
 - Better exception handling.
 - Args parsing so the file path can be inserted as an argument to the bash alias > $log_time "path\to\file\TimeFile.csv"
 - Use tabs to better space out console output for clarity and neatness.
 - Include total time logged for each day or total time logged in the current run.
 - As a safety net for when the ledger database is temporarily unreachable, or as an alternative to it: check JIRA directly (via the worklog API) for a matching entry before creating a new one.
