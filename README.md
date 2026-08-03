# Time Logger

A script designed to accept a CSV file from [TimeTagger](https://github.com/almarklein/timetagger) (selfhosted) and post to the work log REST API provided by JIRA. It significantly reduces the amount of time it takes to log time each day, especially when hours are split amongst numerous small tasks.

## Pre-Requisites

This intended to be a CLI script executed from WSL on Windows as this is my personally preferred method. To adapt it to your needs you will need to change the script to accept your preffered input file path (the report from TimeTagger) and adapt the execution process to your specific environment, for example, if you wish to execute the script from CMD or Powershell.

Required:
 - Python >= 3.10
 - WSL (Windows Subsytem for Linux) version 2
 - [uv](https://docs.astral.sh/uv/) (Tooling for Python to manage dependencies & launch the script) 

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

You can safely re-run the same day's file multiple times. Every worklog that JIRA accepts (HTTP 201) is recorded in a local ledger (`state/logged.json` by default), and on subsequent runs those items are skipped — so if you add a few more entries to the same CSV later in the day and re-run, only the newly added items are logged.

An item's identity is `JIRA issue + start time + duration`; the description is deliberately excluded, so fixing a typo in a description and re-running will **not** create a duplicate worklog.

Items are recorded one at a time, only after JIRA confirms them, so a failed item is retried on the next run and an interrupted run never double-logs the items that already succeeded.

If you ever genuinely need to re-log something the ledger already knows about, edit or delete the matching entry in `state/logged.json` (it's plain JSON) and run again. Deleting the whole file resets all history.

### Archiving

Each run that reaches the logging stage copies the source CSV into an archive directory (`archive/` by default), timestamp-prefixed (e.g. `2026-07-29T14-03-05_TimeFile.csv`), so you keep a history of exactly what was processed. The original downloaded file is left untouched.

Both locations can be overridden in `.env` via `LEDGER_PATH` and `ARCHIVE_DIR` (see `.env.example`). Both `state/` and `archive/` are git-ignored.

### Using across multiple devices

The ledger is per-machine, so a second device won't know what the first has already logged. The file that matters for de-duplication is the **ledger** (`state/logged.json`), not the archive.

- **Manual copy:** after logging on one device, copy its `state/logged.json` to the other device (same location, or wherever `LEDGER_PATH` points). Only copy when no run is in progress, so you don't grab a half-written file.
- **File sync:** point `LEDGER_PATH` at a synced folder (OneDrive, Dropbox, a network share) on every device so they share one ledger automatically:

  ```
  LEDGER_PATH="/mnt/c/Users/you/OneDrive/timelogger/logged.json"
  ```

  This works well for a single user; just avoid logging from two devices at the exact same moment, which could cause a sync conflict.

A future option (see below) is to have the tool ask JIRA directly whether a worklog already exists, which would remove the need to share the ledger at all.


## Future Features
 - Implement adding invalid work log items to a file and remind user each time the program runs of items that have yet to be logged from the past. Case in point would be if a JIRA issue hasn't yet been created but the user has captured the time and given it a description.
 - Better exception handling.
 - Args parsing so the file path can be inserted as an argument to the bash alias > $log_time "path\to\file\TimeFile.csv"
 - Use tabs to better space out console output for clarity and neatness.
 - Include total time logged for each day or total time logged in the current run.
 - Cross-device de-duplication: before creating a worklog, check JIRA directly (via the worklog API) for a matching entry, so logging from multiple devices never creates duplicates without needing to share the local ledger.
