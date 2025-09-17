# Time Logger

A script designed to accept a CSV file from [TimeTagger](https://github.com/almarklein/timetagger) (selfhosted) and post to the work log REST API provided by JIRA. It significantly reduces the amount of time it takes to log time each day, especially when hours are split amongst numerous small tasks.

## Pre-Requisites

This intended to be a CLI script executed from WSL on Windows as this is my personally preferred method. To adapt it to your needs you will need to change the script to accept your preffered input file path (the report from TimeTagger) and adapt the execution process to your specific environment, for example, if you wish to execute the script from CMD or Powershell.

Required:
 - Python >= 3.10
 - WSL (Windows Subsytem for Linux) version 2
 - [uv](https://docs.astral.sh/uv/) (Tooling for Python to manage dependencies & launch the script) 

## Installation

CD into your desired directory:
`cd /path/to/directory`

Clone the repo:
`git clone https://github.com/deanbirnie/TimeLogger.git`

Edit the .env.example file so it contains your required configuration information and rename it to '.env':
`mv .env.example .env`

Create the virtual environment which isolates this Python project from others on your machine:
`uv venv`

We can now setup our shell to alias a command of our choosing. I've chosen `log_time` as my command and `nano` as my text editor for simplicity.
First edit bash config (or your shell env of choice):
`nano ~/.bashrc`

Next, at the bottom, add the bash alias:
``` bash
logjira() {
    source /path/to/your/project/.venv/bin/activate
    uv run /path/to/your/project/time_logger.py "$@"
    deactivate
}
```

Finally, reload your shell:
`source ~/.bashrc`

## Usage

Once you've completed the installation instructions, you can run the script from WSL:

First download the time report from TimeTagger or create a CSV file according to the CSV example in the repo.

Then right click on the file in Windows File Explorer wherever it was downloaded to. Select "Copy as path".

Open WSL and use the alias command you configured above:
`log time`

Then paste the Windows file path when prompted.

The script will analyse and validate all your work items. If there are any invalid items it will warn you accordingly, the script will not attempt to log these.

The valid work items will be reported (if any exist) and you will be prompted to continue or cancel. "n" cancels the process while any other key will continue.

Each item is logged using the JIRA REST API and there is some reporting to ensure that each item was logged.

Check your output carefully as the script will inform you of any items that JIRA rejected. The status code 201 is returned for success, any other status code will output an error or a warning for you to resolve manually or fix and run again. Be sure to remove any work items previously logged so as to avoid duplicates.

Once complete, you can close the WSL terminal/shell.


## Future Features
 - Implement adding invalid work log items to a file and remind user each time the program runs of items that have yet to be logged from the past. Case in point would be if a JIRA issue hasn't yet been created but the user has captured the time and given it a description.
 - Better exception handling.
 - Args parsing so the file path can be inserted as an argument to the bash alias > $log_time "path\to\file\TimeFile.csv"
 - Use tabs to better space out console output for clarity and neatness.
 - Include total time logged for each day or total time logged in the current run.
