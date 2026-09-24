import csv
import json
import os
import sys
import textwrap
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

try:
    # When imported as a package (e.g. tests: `from app.time_logger import ...`).
    from app import ledger
except ImportError:
    # When run directly as a script (`uv run app/time_logger.py`), the script's
    # own directory is on sys.path, so ledger.py is importable by bare name.
    import ledger


def clean_description(description: str) -> str:
    """
    Descriptions include any tags by default and they need to be stripped. Splits into multiple strings using '#'. Strips trailing spaces.

    :param description: A work log description item. Output from TimeTagger defaults to the description plus any tags for the item. Example: "This is a description. #tag-123".
    :type description: str

    :return: Cleaned description string.
    :rtype: str
    """
    if not isinstance(description, str):
        raise ValueError("Work log description should be a string.")
    tag_split = description.split("#")
    tagless_description = tag_split[0]
    clean_description = tagless_description.rstrip()

    return clean_description


def get_timezone():
    """The timezone the CSV's wall-clock times are in (.env TIMEZONE)."""
    return ZoneInfo(os.getenv("TIMEZONE") or DEFAULT_TIMEZONE)


def create_datetime(date, started_time, timezone=None):
    """
    Build the ISO-8601 'started' value JIRA expects from a CSV row's date and
    start time.

    TimeTagger gives local wall-clock time as DD-MM-YYYY and HH:MM. The local
    time is attached to a real timezone so the correct UTC offset is emitted,
    rather than shifting the hour by hand and claiming +0000 -- which is what
    produced unpadded hours, a negative hour before 01:00, and an offset that
    was only right part of the year (BUGS.md B2-B4).

    :param date: Date as DD-MM-YYYY, e.g. "09-07-2025".
    :param started_time: 24-hour start time as HH:MM, e.g. "08:30".
    :return: e.g. "2025-07-09T08:30:00.000+0200"
    """
    day, month, year = (int(part) for part in date.split("-"))
    hour, minute = (int(part) for part in started_time.split(":"))
    local = datetime(year, month, day, hour, minute, tzinfo=timezone or get_timezone())

    return local.strftime("%Y-%m-%dT%H:%M:%S.000%z")


def create_time_spent(time_spent):
    hours_minutes = time_spent.split(":")
    hours_to_secs = int(hours_minutes[0]) * 60 * 60
    mins_to_secs = int(hours_minutes[1]) * 60

    return hours_to_secs + mins_to_secs


def create_issue_str(issue_str):
    issue = issue_str.strip("#")
    # if issue == "untagged":
    #     raise Exception("No JIRA issue for this item.")
    return issue

REPORT_WIDTH = 78

# TimeTagger exports four rows of headers/subtotals before the first work item.
HEADER_ROWS = 4

# CSV times are local wall-clock; overridable via TIMEZONE in .env.
DEFAULT_TIMEZONE = "Africa/Johannesburg"


def format_duration(seconds) -> str:
    """Human-readable duration, e.g. '23m' or '1h 35m'."""
    minutes = int(seconds) // 60
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


def format_started(started) -> str:
    """
    Display form of the JIRA 'started' timestamp, e.g. '2025-07-09 08:30'.

    Deliberately lenient: a malformed timestamp (see BUGS.md B2-B4) is shown as
    it actually is rather than hidden behind an exception.
    """
    if not started:
        return ""
    date_part, _, time_part = str(started).partition("T")
    if not time_part:
        return date_part
    return f"{date_part} {':'.join(time_part.split(':')[:2])}"


def classify_items(time_data):
    """
    Split parsed rows into (valid, invalid). Invalid items are never sent to JIRA.

    :return: tuple(list, list)
    """
    valid_list = []
    invalid_list = []
    for data in time_data:
        time_spent, started, description, jira_issue = data[0], data[1], data[2], data[3]

        if (
            not isinstance(time_spent, int) or
            time_spent <= 0 or
            not description or
            not jira_issue or
            jira_issue == "untagged" or
            started is None
        ):
            invalid_list.append(data)
        else:
            valid_list.append(data)

    return valid_list, invalid_list


def render_items(items, indent="  ") -> list:
    """
    Render work items as aligned columns: issue, duration, start, description.

    Column widths are sized to the items passed in, and the description comes
    last (truncated if needed) so a long one can never push the other columns
    out of alignment.
    """
    if not items:
        return []

    issue_width = max(len(str(item[3])) for item in items)
    duration_width = max(len(format_duration(item[0])) for item in items)
    started_width = max(len(format_started(item[1])) for item in items)
    description_width = max(
        20, REPORT_WIDTH - len(indent) - issue_width - duration_width - started_width - 6
    )

    lines = []
    for item in items:
        description = str(item[2])
        if len(description) > description_width:
            description = description[:description_width - 1] + "…"
        lines.append(
            f"{indent}{str(item[3]):<{issue_width}}  {format_duration(item[0]):>{duration_width}}  "
            f"{format_started(item[1]):<{started_width}}  {description}"
        )
    return lines


def render_section(title, items, note="") -> list:
    """A titled, ruled block of items. Empty sections render as nothing at all."""
    if not items:
        return []
    heading = f"{title} ({len(items)})"
    if note:
        heading += f"  -  {note}"
    return [heading, "-" * REPORT_WIDTH, *render_items(items), ""]


def render_report(source_name, invalid_items, already_logged, new_items) -> str:
    """
    The pre-flight report. Each item appears in exactly one section: invalid,
    already logged, or to be logged.
    """
    lines = [
        "=" * REPORT_WIDTH,
        f"Time Logger  -  {source_name}",
        "=" * REPORT_WIDTH,
        "",
    ]
    lines += render_section("INVALID - will not be logged", invalid_items)
    lines += render_section("ALREADY LOGGED - skipping", already_logged)
    lines += render_section(
        "TO LOG", new_items,
        note=f"total {format_duration(sum(item[0] for item in new_items))}",
    )
    return "\n".join(lines)


def describe_failure(response) -> str:
    """Condense a JIRA error response into a single line."""
    try:
        detail = response.json()
    except ValueError:
        body = (response.text or "").strip().replace("\n", " ")
        return body[:120] if body else "no response body"

    if isinstance(detail, dict):
        messages = detail.get("errorMessages") or []
        field_errors = [f"{field}: {msg}" for field, msg in (detail.get("errors") or {}).items()]
        combined = "; ".join([*messages, *field_errors])
        if combined:
            return combined[:200]
    return str(detail)[:200]


def log_time(issue, description, date_time, time_spent):
    """Actually log the time to JIRA... Please be careful :)"""
    # print(f'{type(time_spent)} - {time_spent}')
    load_dotenv()

    jira_email = os.getenv("JIRA_EMAIL")
    jira_api_token = os.getenv("JIRA_API_TOKEN")

    url = f"https://innosys.atlassian.net/rest/api/3/issue/{issue}/worklog"

    auth = HTTPBasicAuth(f"{jira_email}",
                         f"{jira_api_token}")

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    payload = json.dumps({
        "comment": {
            "content": [
                {
                    "content": [
                        {
                            "text": description,
                            "type": "text"
                        }
                    ],
                    "type": "paragraph"
                }
            ],
            "type": "doc",
            "version": 1
        },
        "started": date_time,
        "timeSpentSeconds": time_spent
    })

    response = requests.request(
        "POST",
        url,
        data=payload,
        headers=headers,
        auth=auth
    )

    return response

def build_data(time_file_path: str):
    """
    Parse the TimeTagger CSV into work items.

    A row that cannot be parsed is recorded and skipped. Previously the append
    sat outside the try, so a bad row silently re-appended the *previous* row's
    values -- duplicating that worklog onto the wrong issue, or raising
    NameError if the very first data row failed (BUGS.md B1).

    :return: tuple(list of work items, list of (row_number, reason) skipped)
    """
    time_data = []
    skipped = []

    with open(time_file_path, "r", newline="") as csvfile:
        reader = csv.reader(csvfile)

        for row_number, row in enumerate(reader, start=1):
            if row_number <= HEADER_ROWS:
                continue
            if not any(field.strip() for field in row):
                continue  # trailing blank line

            try:
                time_spent = create_time_spent(row[2])
                started = create_datetime(row[3], row[4])
                description = clean_description(row[6])
                jira_issue = create_issue_str(row[8])
            except (ValueError, IndexError) as exc:
                skipped.append((row_number, f"{type(exc).__name__}: {exc}"))
                continue

            time_data.append([time_spent, started, description, jira_issue])

    return time_data, skipped

def find_file(win_path_to_file):
    file_path = win_path_to_file.strip('"')
    split_path = file_path.split("\\")

    file_name = split_path[-1]

    load_dotenv()

    download_dir = os.getenv("DOWNLOAD_DIR")
    time_file = f"{download_dir}{file_name}"

    return time_file


if __name__ == "__main__":
    # Connect to the ledger database first and fail fast: logging without being
    # able to record the result risks duplicate worklogs on the next run.
    load_dotenv()
    try:
        db_conn = ledger.connect()
    except ledger.DatabaseConnectionError as exc:
        print(f"❌ {exc}")
        sys.exit(1)

    win_file_path = input("Please paste the path to the file you wish to log to JIRA: ")
    clean_file_path = find_file(win_file_path)
    source_name = os.path.basename(clean_file_path)

    data, skipped_rows = build_data(clean_file_path)
    valid_list, invalid_items = classify_items(data)

    # Split the valid items against the ledger so re-running a file only logs
    # items that haven't already been accepted by JIRA.
    logged_ledger = ledger.load_ledger(db_conn)
    new_items, already_logged = ledger.filter_new(logged_ledger, valid_list)

    print()
    print(render_report(source_name, invalid_items, already_logged, new_items))

    if skipped_rows:
        print(f"⚠️ {len(skipped_rows)} row(s) could not be read and were skipped:")
        for row_number, reason in skipped_rows:
            print(f"  row {row_number}: {reason}")
        print()

    if not new_items:
        print("Nothing new to log - everything valid in this file is already logged.")
    else:
        total_seconds = sum(item[0] for item in new_items)
        answer = input(
            f"Log {len(new_items)} item(s) totalling {format_duration(total_seconds)}? (y/N)  "
        ).strip().lower()
        if answer not in ("y", "yes"):
            print("Cancelled - nothing was logged.")
            db_conn.close()
            sys.exit()

        print()
        print("-" * REPORT_WIDTH)
        issue_width = max(len(str(item[3])) for item in new_items)
        duration_width = max(len(format_duration(item[0])) for item in new_items)

        logged_seconds = 0
        failures = 0
        for work_item in new_items:
            time_spent = work_item[0]
            started = work_item[1]
            description = work_item[2]
            jira_issue = work_item[3]
            response = log_time(jira_issue, description, started, time_spent)

            row = (f"  {str(jira_issue):<{issue_width}}  "
                   f"{format_duration(time_spent):>{duration_width}}  ")
            if response.status_code == 201:
                # Record only on success, immediately, so a crash never double-logs.
                ledger.record_logged(db_conn, logged_ledger, work_item, source_name)
                logged_seconds += time_spent
                print(f"{row}✅ Logged")
            else:
                failures += 1
                status = f"❌ Failed ({response.status_code})"
                reason = describe_failure(response)
                inline = f"{row}{status} {reason}"
                if len(inline) <= REPORT_WIDTH:
                    print(inline)
                else:
                    # Keep the row within the report width without losing the
                    # reason: wrap it onto indented continuation lines.
                    print(f"{row}{status}")
                    for line in textwrap.wrap(reason, width=REPORT_WIDTH - 6):
                        print(f"      {line}")

        print("-" * REPORT_WIDTH)
        summary = (f"Logged {len(new_items) - failures} of {len(new_items)} item(s), "
                   f"{format_duration(logged_seconds)} of {format_duration(total_seconds)}.")
        if failures:
            summary += f"  {failures} failed - fix and run again."
        print(summary)

    # Archive the processed file for history (every run that reaches this stage).
    try:
        archived_path = ledger.archive_file(clean_file_path, ledger.get_archive_dir())
        print(f"📁 Archived to {archived_path}")
    except OSError as exc:
        print(f"⚠️ Could not archive source file: {exc}")

    db_conn.close()

"""
JIRA Documentation found here:
https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-worklogs/#api-rest-api-3-issue-issueidorkey-worklog-post
"""