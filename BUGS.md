# Bugs

A catalogue of confirmed and suspected bugs in TimeLogger, most severe first.
Severity reflects the risk of logging **wrong or duplicate time to JIRA**, since
that is the tool's whole purpose and such errors are tedious to unwind by hand.

> IDs are stable references used by `TODO.md`.

---

## B1 — Malformed CSV row duplicates the previous row's worklog *(Critical)*

**File:** `app/time_logger.py` — `build_data()` (lines ~168–184)

The per-row parse is wrapped in `try / except: pass`, but the lines that build and
append the row are **outside** the `try`:

```python
try:
    time_spent = create_time_spent(row[2])
    started = create_datetime(row[3], row[4])
    description = clean_description(row[6])
    jira_issue = create_issue_str(row[8])
except:
    pass

row_list = [time_spent, started, description, jira_issue]  # <-- outside try
time_data.append(row_list)
```

When a row fails to parse, the exception is swallowed and the code falls through
to `row_list = [...]` using the **stale values from the previous successful row**.
That duplicate is then appended and (if valid) logged to JIRA a second time.

Reproduced: a CSV with a good row (`JIRA-1`), a malformed row, and another good row
(`JIRA-3`) returns `[JIRA-1, JIRA-1, JIRA-3]` — `JIRA-2` is dropped and `JIRA-1` is
duplicated.

Additionally, if the **first** data row fails to parse, `time_spent` et al. are never
assigned and the fall-through raises `NameError`, crashing the whole run.

**Fix direction:** move `row_list`/`append` inside the `try`, or `continue` in the
`except`. Skipped rows should be collected and reported, not silently absorbed.

---

## B2 — Hours/minutes are not zero-padded in the JIRA timestamp *(High)*

**File:** `app/time_logger.py` — `create_datetime()` (line ~39)

```python
date_time_str = f"{...}T{hour}:{time_split[1]}:00.000+0000"
```

`hour` is an `int`, so `09:05` produces `...T8:05:...` instead of `...T08:05:...`.
The `started` field JIRA expects is ISO‑8601, which requires two-digit hours. JIRA
may reject the timestamp or silently misinterpret it.

**Fix direction:** format with `f"{hour:02d}"`, and pad/validate minutes too.

---

## B3 — Times before 01:00 produce a negative hour *(High)*

**File:** `app/time_logger.py` — `create_datetime()` (line ~37)

```python
hour = int(time_split[0]) - 1
```

For a start time of `00:30`, `hour` becomes `-1`, yielding the invalid string
`...T-1:30:00.000+0000`. Any task started between 00:00 and 00:59 is corrupted.

**Fix direction:** do the offset with a real datetime/timezone conversion (see B4)
rather than integer subtraction on the hour field.

---

## B4 — Timezone conversion is a hardcoded "subtract one hour" hack *(High)*

**File:** `app/time_logger.py` — `create_datetime()` (lines ~36–39)

The code subtracts a fixed hour to convert local time to UTC and then hardcodes the
`+0000` offset. The inline comment even warns *"careful if clocks go back."* This is
only correct during British Summer Time; for roughly half the year (GMT) every logged
time is shifted an hour early. It is also wrong for any user not in the UK.

**Fix direction:** parse the naive local datetime and convert using `zoneinfo`
(e.g. a configurable `TIMEZONE` in `.env`, defaulting to `Europe/London`), emitting
the correct offset. This also fixes B2 and B3 for free.

---

## B5 — `.env` is loaded relative to the current directory, not the project *(Medium)*

**File:** `app/time_logger.py` — `log_time()` / `find_file()` (`load_dotenv()`)

`load_dotenv()` with no path searches upward from the **current working directory**.
The README's alias runs the script by absolute path from wherever the user happens to
be, so `.env` is usually not found. `JIRA_EMAIL`, `JIRA_API_TOKEN`, and `DOWNLOAD_DIR`
then silently resolve to `None`, causing auth failures and malformed file paths with no
clear message.

**Fix direction:** `load_dotenv(Path(__file__).resolve().parent.parent / ".env")` (or
similar), loaded once at startup.

---

## B6 — JIRA base URL is hardcoded *(Medium)*

**File:** `app/time_logger.py` — `log_time()` (line ~119)

```python
url = f"https://innosys.atlassian.net/rest/api/3/issue/{issue}/worklog"
```

The Atlassian site is baked in, so the tool only works for one organisation despite the
README inviting others to "adapt it to your needs."

**Fix direction:** read a `JIRA_BASE_URL` from `.env`.

---

## B7 — CSV opened with `'r+'` (read/write) instead of read-only *(Medium)*

**File:** `app/time_logger.py` — `build_data()` (line ~161)

```python
with open(time_file_path, 'r+') as csvfile:
```

The file is only ever read. Opening `r+` requires write permission and fails outright on
a read-only file or mount. Use `'r'`.

---

## B8 — No handling when the input file is missing *(Medium)*

**File:** `app/time_logger.py` — `find_file()` / `build_data()`

`find_file()` blindly concatenates `DOWNLOAD_DIR + file_name` with no existence check, and
`build_data()` opens it directly. A wrong path (or unset `DOWNLOAD_DIR`, see B5) raises an
uncaught `FileNotFoundError`/`TypeError` and a raw traceback instead of a helpful message.

---

## B9 — Bare `except:` swallows everything *(Low)*

**File:** `app/time_logger.py` — `build_data()` (line ~179)

A bare `except:` also catches `KeyboardInterrupt` and `SystemExit`, and hides *why* a row
was skipped. At minimum use `except Exception` and record the offending row (ties into B1).

---

## B10 — Cancel prompt only honours lowercase `n` *(Low)*

**File:** `app/time_logger.py` — `__main__` (line ~207)

```python
if input("Would you like to continue logging time? (Y/n)\t") == "n":
    sys.exit()
```

The prompt shows `(Y/n)`, but only an exact lowercase `n` cancels. Typing `N`, `no`, or
anything else proceeds to log time. For a network-writing action the safe default should be
stricter (normalise case, treat `n`/`no` as cancel).

---

## B11 — `create_report` validation can raise on a non-int duration *(Low)*

**File:** `app/time_logger.py` — `create_report()` (lines ~77–87)

`time_spent <= 0` is evaluated **before** `not isinstance(time_spent, int)`. If a non-int
ever reaches this check (e.g. via the B1 stale-value path), the comparison raises
`TypeError` instead of classifying the row as invalid. Reorder so the type check comes first.

---

## B12 — `build_data` return type hint is wrong *(Low / cosmetic)*

**File:** `app/time_logger.py` — `build_data()` (line ~159)

Annotated `-> None` but returns a `list`. Misleading to readers and tooling.

---

## B13 — README install instructions do not produce a working command *(Doc — High for onboarding)*

**File:** `README.md`

Three separate defects mean following the README verbatim yields a broken setup:

1. The prose says the chosen command is `log_time`, the alias **function is named
   `logjira`**, and the Usage section says to run **`log time`** (with a space). None match.
2. The alias runs `uv run /path/to/your/project/time_logger.py`, but the script actually
   lives at **`app/time_logger.py`** — the documented path does not exist.
3. The alias both `source`s the venv *and* calls `uv run`, which is redundant (`uv run`
   manages the environment itself).

Addressed by the new `install.sh` (see `IMPROVEMENTS.md` I1), which becomes the single
source of truth for setup.
