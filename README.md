# Minimal Aras BatchLoader CLI – README

A scriptable wrapper around **Aras BatchLoaderCmd.exe** that lets you load delimited data files into an Aras Innovator database **without** mixing your CLI runs with the UI’s configuration. It discovers the matching AML template for each data file, runs the BatchLoader from the proper runtime folder (so DLLs are found), and writes a log per dataset.

## Overview

Aras Innovator ships a Windows BatchLoader and a UI-driven tooling model. Teams often want a **more customizable, CLI-only pipeline** that:

* keeps **CLI connection settings separate** from the UI’s BatchLoader config,
* supports running from **any folder** while pointing to the real BatchLoader runtime,
* **orders uploads** so base items come **before** relationship rows

---

## Prerequisites

* **Python 3.10+** (3.11+ recommended).
* **Aras BatchLoader runtime folder** (the directory that contains `BatchLoaderCmd.exe` and its DLLs).
* Network access and permissions to your **Aras Innovator** instance.

---

## Quick Start (Windows)

1) Verify Python is installed and on PATH

```powershell
python --version
# or
py --version
```

2) Locate your BatchLoader runtime folder (contains `BatchLoaderCmd.exe`), e.g.:

```
"C:\\innovator\\Release 35 CD Image\\BatchLoader"
```

3) Initialize a CLI-only config (one-time)

```powershell
python .\batchloader.py --init-config --init-from-runtime --dl-dir "C:\\path\\to\\BatchLoader" --bl-config .\CLIBatchLoaderConfig.xml
```

4) Edit `CLIBatchLoaderConfig.xml`

- Set `server`, `db`, `user`, `password`, and verify `loader_dir` (auto-injected by step 3).

5) Put data files and templates in `./data`

- Example: `001-User.txt` and `001-User_Template.xml`.

> Important: **Before you load**, back up your Innovator database so you can revert if needed.

6) Run the loader

```powershell
python .\batchloader.py
# or override runtime path at run time:
python .\batchloader.py --dl-dir "C:\\innovator\\Release 35 CD Image\\BatchLoader"
```

Logs are written to `./logs` (one per data file).

See [Install / Setup (Detailed)](#install--setup-detailed) and [Data & Template Conventions](#data--template-conventions-critical) for more detailed install instructions.

## What it does

For every `*.txt` data file in your `--data-dir` (default: `./data`), the script:

1. **Finds the matching template**

   * Looks for `<stem>.xml` in `--templates-dir`, **or**
   * `<stem>_Template.xml` **next to** the data file.
2. **Runs** `BatchLoaderCmd.exe` **from the runtime folder** you specify (or that’s embedded in the CLI config).
3. **Writes a log** to `--logs-dir` (default: `./logs`).
4. Skips files with missing templates with a clear `[SKIP]` message.

**Sorts files by name**, so you can control load order with filename prefixes (e.g., `001-User.txt`, `018-Document.txt`, `200-Relationship.txt`, etc.).

---

## Example repository layout

```
.
├─ batchloader.py                  # The Python CLI wrapper
├─ CLIBatchLoaderConfig.xml        # CLI-only config
├─ data/
│  ├─ 001-User.txt                 # Sample data files (tab-delimited)
│  ├─ 001-User_Template.xml        # Matching AML templates
│  ├─ 005-Variable.txt
│  ├─ 005-Variable_Template.xml
│  ├─ 018-Document.txt
│  ├─ 018-Document_Template.xml
│  ├─ 096-Customer.txt
│  └─ 096-Customer_Template.xml
└─ logs/                           # Output logs (created on first run)
```

> **Important:** Your **BatchLoader runtime folder** (with `BatchLoaderCmd.exe` and DLLs) may live *outside* this repo. You’ll point to it via `--dl-dir` or via `<loader_dir>` inside `CLIBatchLoaderConfig.xml`. The .dll files must be in the same folder as the BatchLoader.


---

## Install / Setup (Detailed)

<details>
<summary>Expand for full Windows setup</summary>

### Step 0: Install Python (Windows)

1. Download **Python 3.11+** from: [https://www.python.org/downloads/windows/](https://www.python.org/downloads/windows/)
2. Run the installer and **check** “**Add python.exe to PATH**”.
3. Open a new PowerShell window and verify:

   ```powershell
   python --version
   # or, if your environment uses the launcher:
   py --version
   ```

> **Dependencies / virtual env**
> This project uses only the Python **standard library**. No `pip` installs are required.
> A virtual environment is **optional**:
>
> ```powershell
> python -m venv .venv
> .\.venv\Scripts\Activate.ps1
> ```

---

### Step 1: Get/locate the BatchLoader runtime

Obtain the **BatchLoader runtime folder** that contains `BatchLoaderCmd.exe` **and all DLLs** (typically shipped with Aras Innovator). Note its full path, e.g.:

```
"C:\innovator\Release 35 CD Image\BatchLoader"
```

---

### Step 2: Get the project files

Clone this repo (or copy `batchloader.py` + `CLIBatchLoaderConfig.xml` into a working folder). From that folder, you can initialize and run the loader.

---

### Step 3: Create a CLI config from the runtime (recommended)

If you already have a working **runtime** `BatchLoaderConfig.xml` (used by the UI), you can clone it into a clean **CLI** config and inject the loader path:

```powershell
python .\batchloader.py --init-config --init-from-runtime --dl-dir "C:\path\to\BatchLoader" --bl-config .\CLIBatchLoaderConfig.xml
```

This copies `BatchLoaderConfig.xml` from the runtime folder and adds a `<loader_dir>` element so future runs don’t need `--dl-dir`.

---

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

  <!-- Absolute or relative path to the BatchLoader runtime folder -->
  <loader_dir>..\..\..\BatchLoader</loader_dir>
</BatchLoaderConfig>
```

**Where to find these values (fill in for your org):**

*"Session" option from user's top-right dropdown in Innovator is a good place to start*

* **server** – your Innovator site URL (IIS binding or internal environment map), **without** the `/Server` path at the end. For example, use `https://your-innovator-host` (not `https://your-innovator-host/Server`).
* **db** – the SQL Server database name for your Innovator environment.
* **user/password** – an Innovator account with permissions to load data.
* **first\_row** – `2` if your files include a header row; `1` if they do not.
* **delimiter** – choose `\t`, `,`, or `|` to match your file format.
* **loader\_dir** – the folder that contains `BatchLoaderCmd.exe` and its DLLs.

</details>

## Data & template conventions (critical!)

<details>
<summary>Expand for conventions, ordering, and formats</summary>

### Ordering of loads

* Files are processed in **case-insensitive, lexicographic order**.
  Ex: `001-User.txt` ➜ `005-Variable.txt` ➜ `018-Document.txt` ➜ `096-Customer.txt`.
* Put **base “main items” first** (e.g., `User`, `Document`, `Part`, `Customer`).
* Put **relationship rows after** both sides exist (e.g., `Part Document` relations).

  * Example names: `200-PartDocumentRelationship.txt`, `200-PartDocumentRelationship_Template.xml`.

*This avoids foreign-key or key-lookup failures during relationship inserts.*

### Data and template file organization

By default, place all your data files (`*.txt`) and their corresponding templates (`*_Template.xml`) together in the `/data` directory. This is the standard and simplest setup.

If you want to keep templates in a separate location, you can specify a template directory using the `--templates-dir` option when running the script. The script will still expect your data files in the data directory you provide (default is `/data`), but will look for templates in the template directory if specified.

#### How templates are found

For each data file `<data-dir>/NNN-Name.txt` (where `NNN-Name` is the stem), the script searches for the template as follows:

1. If `--templates-dir` is specified: looks for `<templates-dir>/NNN-Name.xml`
2. Otherwise (or if not found): looks for `<data-dir>/NNN-Name_Template.xml` (next to the data file)

If no template is found, the file is **skipped** and `[SKIP]` is printed.

### CSV/TSV format expectations

* File should match the **`<delimiter>`** and **`<encoding>`** in your config.
* `first_row` controls header skipping (`2` means “skip header row”).
* Template placeholders `@1`, `@2`, … map to the **column index** in your file.
  Example (`001-User_Template.xml`):

  ```xml
  <Item type="User" action="merge" id="@1">
    <last_name>@2</last_name>
    <first_name>@3</first_name>
    <!-- ... -->
  </Item>
  ```

</details>

## Running the loader

### Windows

For a minimal first run on Windows, see Quick Start above.

```powershell 
# Using loader_dir embedded in CLIBatchLoaderConfig.xml
python .\batchloader.py

# OR: override at runtime (if no <loader_dir> in the CLI config)
python .\batchloader.py --dl-dir "C:\innovator\Release 35 CD Image\BatchLoader"
```

---

## Logs, exit codes, and retries

* Each run writes a **per-file log** into `--logs-dir`, e.g., `logs/001-User.log`.
* If `BatchLoaderCmd.exe` returns non-zero, the script prints:
  `-> non-zero exit (<code>); check <logfile>`
* **About `.failed` files:** BatchLoader typically writes a `<stem>.failed` file containing rows that did not load.

### Fast retries

If a run generates `.failed` row files (written to the data directory), you can re-run only those rows:

```powershell
# Looks in ./data for *.failed and replays them
python .\batchloader.py --retry

# If your .failed files are in a different location:
python .\batchloader.py --retry --retry-dir .\some\other\folder

# You can still provide a separate templates directory if you keep templates out of /data
python .\batchloader.py --retry --templates-dir .\Templates
```

**Notes**

* By default, looks for `.failed` files in your `--data-dir` (default: `./data`)
* Templates are resolved as `Templates/<stem>.xml` or fallback `data/<stem>_Template.xml`
* Logs are written to `./logs/retry/<stem>.retry.log`
* The script does **not** delete or rename `.failed` files
* If your `.failed` files don't include a header row, make sure your CLI config uses `<first_row>1</first_row>` for the retry

```

### Manual retry option

Alternatively, you can move/rename `*.failed` ➜ `*.txt` in a separate folder and re-run the script against that folder:

```powershell
mkdir .\data_failed
copy .\logs\*.failed .\data_failed\
# rename files to *.txt as needed, then:
python .\batchloader.py --data-dir .\data_failed
```
---

## Usage examples

**Initialize a CLI config from the runtime (one-time):**

See Quick Start (Windows) step 3 for the `--init-config` command.

```powershell
python .\batchloader.py --init-config --init-from-runtime --dl-dir "C:\path\to\BatchLoader" --bl-config .\CLIBatchLoaderConfig.xml
```

**Run with default locations (data in `./data`, logs to `./logs`):**

```powershell
python .\batchloader.py
```

**Run from macOS/Linux with Wine:**

```bash
python3 ./batchloader.py --dl-dir "/innovator/CDImage35Release/BatchLoader"
```
