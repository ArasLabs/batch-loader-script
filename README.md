# Minimal Aras BatchLoader CLI

A small, scriptable wrapper around the Aras Batch Loader to run data loads from the command line and in automation.

Subscribers receive the Batch Loader tool (GUI) and the `BatchLoaderCmd.exe` CLI utility as part of the Aras Innovator product. This repository is a sample script that wraps `BatchLoaderCmd.exe` to help automate repeatable, CLI‑first data loads and integrate them into pipelines. It is not a replacement for the product utilities.

## Overview

This script makes Batch Loader easier to use in a CLI‑only workflow:

- Keep CLI connection settings separate from the UI’s BatchLoader config.
- Run from any folder while pointing to the BatchLoader runtime (DLLs resolve).
- Discover matching AML templates for each data file automatically.
- Process files in a predictable order so base items load before relationships.
- Write a per‑file log for fast troubleshooting.

## Prerequisites

- Python 3.10+ (3.11+ recommended).
- Access to the BatchLoader runtime folder (contains `BatchLoaderCmd.exe` and DLLs).
- Network access and permissions to load data into your Innovator instance.

---

## Quick Start (Windows)

1) Verify Python is on PATH

```powershell
python --version
# or
py --version
```

2) Copy the runtime config (one‑time)
```powershell
python .\batchloader.py --init-config --init-from-runtime --bl-dir "C:\\path\\to\\BatchLoader" --bl-config .\CLIBatchLoaderConfig.xml
```

3) Edit the CLI config

- Open `CLIBatchLoaderConfig.xml` and set `server`, `db`, `user`, `password`.
- Ensure `<loader_dir>` points to the BatchLoader runtime folder. Adjust `delimiter` and `first_row` if needed.

4) Run the loader

```powershell
# Using loader_dir embedded in CLIBatchLoaderConfig.xml
python .\batchloader.py

# OR override at runtime
python .\batchloader.py --bl-dir "C:\\innovator\\Release 35 CD Image\\BatchLoader"
```

5) Review logs in `./logs`

That’s it for a first run. For more details, see Install / Setup and Conventions.

---

## Install / Setup

### Step 0: Install Python (Windows)

1) [Download Python 3.11+](https://www.python.org/downloads/windows/)
2) Run the installer and check “Add python.exe to PATH”.
3) Verify in a new PowerShell window:

```powershell
python --version
# or
py --version
```

Dependencies: this project uses only the Python standard library (no pip installs). A virtual environment is optional:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### Step 1: Locate the BatchLoader runtime

Obtain the BatchLoader runtime folder that contains `BatchLoaderCmd.exe` and all DLLs (shipped with Aras Innovator). Note its path, for example:

```
C:\\innovator\\Release 35 CD Image\\BatchLoader
```

### Step 2: Get the project files

Clone this repo (or copy `batchloader.py` + `CLIBatchLoaderConfig.xml` into a working folder). The repo includes sample data in `./data`.

Example layout:

```
.
├─ batchloader.py                  # Python CLI wrapper
├─ CLIBatchLoaderConfig.xml        # CLI-only config
├─ data/                           # Sample data + templates
└─ logs/                           # Created on first run
```

Important: Your BatchLoader runtime folder may live outside this repo. Point to it via `--bl-dir` or `<loader_dir>` inside `CLIBatchLoaderConfig.xml`. DLLs must be in the same folder as `BatchLoaderCmd.exe`.

### Step 3: Create a CLI config from the runtime (recommended)

If you already have a working runtime `BatchLoaderConfig.xml` (used by the UI), clone it into a clean CLI config and inject the loader path:

```powershell
python .\batchloader.py --init-config --init-from-runtime --bl-dir "C:\\path\\to\\BatchLoader" --bl-config .\CLIBatchLoaderConfig.xml
```

This copies `BatchLoaderConfig.xml` from the runtime folder and adds a `<loader_dir>` element so future runs don’t need `--bl-dir`.

After copying, open `CLIBatchLoaderConfig.xml` and edit the connection settings (`server`, `db`, `user`, `password`). The script reads connection info from this file and runs will fail without valid values.

### Step 4: Fill in connection and loader settings

Open `CLIBatchLoaderConfig.xml` and set values:

```xml
<BatchLoaderConfig>
  <server>https://YOUR-INNOVATOR-URL</server>
  <db>YOUR_DATABASE_NAME</db>
  <user>admin</user>
  <password>innovatorpassword123</password>
  <max_processes>1</max_processes>
  <threads>1</threads>
  <lines_per_process>250</lines_per_process>
  <delimiter>\t</delimiter>
  <encoding>utf-8</encoding>
  <first_row>2</first_row>
  <log_level>3</log_level>
  <loader_dir>..\..\..\BatchLoader</loader_dir>
 </BatchLoaderConfig>
```

Guidance:

- `server`: your Innovator site URL (without the trailing `/Server`).
- `db`: the SQL Server database name for your environment.
- `user/password`: an Innovator account with permissions to load data.
- `first_row`: 2 if files include a header row; 1 if not.
  - **Headerless rule:** when `first_row = 1`, **column 1 must be the GUID**
    used for deletes (required header name with headers: `id`).
- `delimiter`: `\t`, `,`, or `|` to match your file format.
- `loader_dir`: folder that contains `BatchLoaderCmd.exe` and DLLs.

### Non‑Windows (Linux/macOS) via Wine

Windows is the primary and most tested target. Linux/macOS can work via Wine:

- Install Wine; ensure `wine` is on PATH.
- BatchLoader is a Windows .NET app. Install the .NET Framework in Wine. Wine‑Mono alone may not suffice.
- Use `--bl-dir` pointing to the BatchLoader runtime folder accessible to Wine; prefer absolute paths.

Examples:

```bash
# Load data
python3 ./batchloader.py --bl-dir "/innovator/CDImage35Release/BatchLoader"

# Delete data
python3 ./batchloader.py --delete --bl-dir "/innovator/CDImage35Release/BatchLoader"

# Clean failed files
python3 ./batchloader.py --clean-failed
```

---

## Conventions

Data formatting and ordering are critical for correct results.

See [CONVENTIONS.md](CONVENTIONS.md) for data and template organization, load order, and CSV/TSV format expectations.

---

## Usage

### Flags

- `--bl-dir`: Runtime folder with `BatchLoaderCmd.exe` and DLLs.
- `--bl-config`: CLI config path (default `./CLIBatchLoaderConfig.xml`).
- `--data-dir`: Data directory (default `./data`).
- `--templates-dir`: Optional separate templates directory.
- `--logs-dir`: Where to write logs (default `./logs`; deletes → `./logs/delete`, retries → `./logs/retry`).
- `--retry` [`--retry-dir`]: Replay `.failed` files.
- `--delete` [`--delete-templates-dir`]: Reverse delete using generated templates (default delete-templates dir: `./templates_delete`).
- `--clean-failed`: Remove all `.failed` files.
- `--init-config --init-from-runtime`: Create a CLI config from the runtime.

See all options: `python .\batchloader.py -h`.

### Basic commands (Windows)

```powershell
# Using loader_dir embedded in CLIBatchLoaderConfig.xml
python .\batchloader.py

# OR override at runtime (if <loader_dir> is not set)
python .\batchloader.py --bl-dir "C:\\innovator\\Release 35 CD Image\\BatchLoader"
```

### Logs, exit codes, and retries

- Each run writes a per‑file log into `--logs-dir`, e.g., `logs/001-User.log`.
- If `BatchLoaderCmd.exe` returns non‑zero, the script prints: `-> non-zero exit (<code>); check <logfile>`.
- BatchLoader writes a `<stem>.failed` file containing rows that did not load.

Fast retries

If a run generates `.failed` row files, they’re written alongside your data using the data file’s stem (no `.txt`). Example: `data\001-Parts_TopAndAssemblies.failed`.

```powershell
# Looks in ./data for *.failed and replays them
python .\batchloader.py --retry

# If your .failed files are in a different location:
python .\batchloader.py --retry --retry-dir .\some\other\folder

# Provide a separate templates directory if templates aren’t in /data
python .\batchloader.py --retry --templates-dir .\templates
```

Notes

- Searches for `.failed` in `--retry-dir` (if provided) or `--data-dir` (default: `./data`).
- Retry file name matches the original data file’s stem.
- Template resolution during retries: `--templates-dir/<stem>.xml`, else `data/<stem>_Template.xml`.
- Logs go to `./logs/retry/<stem>.retry.log` (e.g., `logs/retry/001-Parts_TopAndAssemblies.retry.log`).

### Delete mode

The `--delete` flag provides a straightforward way to remove what you just loaded:

```powershell
# Delete everything in reverse order (relationships first, then items)
python .\batchloader.py --delete

# Specify custom delete templates directory
python .\batchloader.py --delete --delete-templates-dir .\custom_delete_templates
```

How it works

- Processes files in reverse order (relationships before items to respect dependencies).
- Auto‑generates delete templates based on your existing insert templates.
  - For relationships: uses the relationship ID from your data files (`id`).
  - For items: uses the Item ID from your data files (`id`).
- Logs all deletions to `./logs/delete/`.
- Generated delete templates are written to `./templates_delete` by default (override with `--delete-templates-dir`).
- Ensure data files satisfy the ID column requirements in `CONVENTIONS.md` so delete mode can identify rows by ID.

Required ID column for deletes

- Items: include an `id` column with the Item’s GUID. With headers, the column can be anywhere; without headers, place the GUID in column 1.
- Relationships: include an `id` column with the relationship row GUID. With headers, the column can be anywhere; without headers, place the GUID in column 1.

### Clean Failed Files

Remove all `*.failed` files from your data directory:

```powershell
# Remove failed files and exit
python .\batchloader.py --clean-failed

# Remove from custom data directory
python .\batchloader.py --clean-failed --data-dir .\custom_data
```

---

## Known Limitations

- Processes only `*.txt` data files (and `*.failed` in retry mode).
- The script does not enforce a specific AML action; whatever your template specifies (`add`, `merge`, etc.) is used. `--delete` is a separate mode that generates delete templates.
- Non-Windows environments require Wine installed and on PATH.
