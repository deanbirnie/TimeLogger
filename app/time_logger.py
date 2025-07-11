import csv
import json
import os
import sys

import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv


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


def create_datetime(date, started_time):
    """
    Takes
    """
    date_split = date.split("-")
    time_split = started_time.split(":")
    # JIRA expects EU/UK time so subtract an hour (careful if clocks go back)
    hour = int(time_split[0]) - 1

    date_time_str = f"{date_split[2]}-{date_split[1]}-{date_split[0]}T{hour}:{time_split[1]}:00.000+0000"

    return date_time_str


def create_time_spent(time_spent):
    hours_minutes = time_spent.split(":")
    hours_to_secs = int(hours_minutes[0]) * 60 * 60
    mins_to_secs = int(hours_minutes[1]) * 60

    return hours_to_secs + mins_to_secs


def create_issue_str(issue):
    return issue.strip("#")

def print_list(i_list):
    work_str = ""
    for item in i_list:
        str_to_print = f"[{item[3]}] - '{item[2]}': Time Spent -> {(item[0] / 60)}m, Started at: {item[1]}\n"
        work_str += str_to_print
    
    if len(work_str) > 0:
        return work_str
    return ""

def create_report(time_data):
    valid_list = []
    invalid_list = []
    for data in time_data:
        time_spent = data[0]
        started = data[1]
        description = data[2]
        jira_issue = data[3]        

        if (
            time_spent <= 0 or
            not isinstance(time_spent, int) or
            description == None or
            description == "" or
            not jira_issue or
            jira_issue == "" or
            jira_issue == None or
            started == None
        ):
            invalid_list.append(data)
        else:
            valid_list.append(data)

    title_spacer = "=" * 100
    spacer = "-" * 100

    report_intro = f"{title_spacer}\nLogging time\n{title_spacer}"
    if len(invalid_list) == 0:
        report_invalid = ""
    else:
        report_invalid = f"The following items are invalid and will not be logged:\n{print_list(invalid_list)}\n{spacer}\n"

    if len(valid_list) == 0:
        report_valid = ""
    else:
        report_valid = f"The following items will be logged:\n{print_list(valid_list)}\n{spacer}"
    
    report = f"{report_intro}\n{report_invalid}\n{report_valid}"
    
    return report, valid_list


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

def build_data(time_file_path: str) -> None:
    time_data = []
    with open(time_file_path, 'r+') as csvfile:
        reader = csv.reader(csvfile)

        # report = report(reader)

        # This loop logs the time
        row_count = 0
        for row in reader:
            if row_count < 4:
                row_count += 1
                continue
            row_count += 1

            time_spent = create_time_spent(row[2])
            started = create_datetime(row[3], row[4])
            description = clean_description(row[6])
            jira_issue = create_issue_str(row[8])

            row_list = [time_spent, started, description, jira_issue]
            time_data.append(row_list)

    return time_data

def find_file(win_path_to_file):
    file_path = win_path_to_file.strip('"')
    split_path = file_path.split("\\")

    file_name = split_path[-1]

    load_dotenv()

    download_dir = os.getenv("DOWNLOAD_DIR")
    time_file = f"{download_dir}{file_name}"

    return time_file


if __name__ == "__main__":
    win_file_path = input("Please paste the path to the file you wish to log to JIRA: ")
    clean_file_path = find_file(win_file_path)
    data = build_data(clean_file_path)
    report, valid_list = create_report(data)
    print(report)
    if input("Would you like to continue logging time? (Y/n)\t") == "n":
        sys.exit()
    for work_item in valid_list:
        time_spent = work_item[0]
        started = work_item[1]
        description = work_item[2]
        jira_issue = work_item[3]
        response = log_time(jira_issue, description, started, time_spent)

        if response.status_code == 201:
            print(f"[{jira_issue}] Time spent: {(time_spent / 60)}m -> ✅ Successful")
        else:
            print(f"❌ Failed to log time to {jira_issue} (Status {response.status_code})")
            try:
                error_detail = response.json()
                print("🔍 Error detail:")
                print(json.dumps(error_detail, indent=2))
            except json.JSONDecodeError:
                print("⚠️ Could not decode error response. Raw content:")
                print(response.text)

    print("-" * 100)
    print("Time logging completed.")

"""
JIRA Documentation found here:
https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-worklogs/#api-rest-api-3-issue-issueidorkey-worklog-post
"""