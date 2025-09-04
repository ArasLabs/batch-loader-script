# Minimal Aras BatchLoader CLI

CLI wrapper for Aras BatchLoader that separates CLI config from UI, resolves templates, orders loads, and writes per‑file logs.

A scriptable wrapper around **Aras BatchLoaderCmd.exe** that lets you load delimited data files into an Aras Innovator database **without** mixing your CLI runs with the UI’s configuration. It discovers the matching AML template for each data file, runs the BatchLoader from the proper runtime folder (so DLLs are found), and writes a log per dataset.

## Overview

Aras Innovator ships a Windows BatchLoader and a UI-driven tooling model. If you prefer a **CLI-only workflow**, this tool:

* keeps **CLI connection settings separate** from the UI’s BatchLoader config,
* supports running from **any folder** while pointing to the real BatchLoader runtime,
* **orders uploads** so base items come **before** relationship rows

---

## Prerequisites

* **Python 3.10+** (3.11+ recommended).
* **Aras BatchLoader runtime folder** (the directory that contains `BatchLoaderCmd.exe` and its DLLs).
* Make sure you can reach Innovator and have rights to load data.

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
C:\innovator\Release 35 CD Image\BatchLoader
```

3) Initialize a CLI-only config (one-time)

```powershell
python .\batchloader.py --init-config --init-from-runtime --bl-dir "C:\path\to\BatchLoader" --bl-config .\CLIBatchLoaderConfig.xml
```

4) Edit `CLIBatchLoaderConfig.xml`

- Set `server`, `db`, `user`, `password`, and verify `loader_dir` (auto-injected by step 3).

5) Put data files and templates in `./data`

- Example: `001-User.txt` and `001-User_Template.xml`.

> Important: **Before you load**, back up your Innovator database (or use a disposable environment). This writes/deletes data. Check the logs after each run.

6) Run the loader

```powershell
# Load all data
python .\batchloader.py

# Delete all data (reverse order)
python .\batchloader.py --delete

# Clean up failed files
python .\batchloader.py --clean-failed

# Override runtime path at run time:
python .\batchloader.py --bl-dir "C:\innovator\Release 35 CD Image\BatchLoader"
```

Logs are written to `./logs` (one per data file).

See [Install / Setup (Detailed)](#install--setup-detailed) and [Data & Template Conventions](#data--template-conventions) for more detailed install instructions.

### Flags at a glance

- `--bl-dir`: Runtime folder with `BatchLoaderCmd.exe` and DLLs.
- `--bl-config`: CLI config path (default `./CLIBatchLoaderConfig.xml`).
- `--data-dir`: Data directory (default `./data`).
- `--templates-dir`: Optional separate templates directory.
- `--logs-dir`: Where to write logs (default `./logs`; deletes -> `./logs/delete`, retries -> `./logs/retry`).
- `--retry` [`--retry-dir`]: Replay `.failed` files.
- `--delete` [`--delete-templates-dir`]: Reverse delete using generated templates.
- `--clean-failed`: Remove all `.failed` files.
- `--init-config --init-from-runtime`: Create a CLI config from the runtime.

See all options: `python .\batchloader.py -h`.

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

> **Important:** Your **BatchLoader runtime folder** (with `BatchLoaderCmd.exe` and DLLs) may live *outside* this repo. You’ll point to it via `--bl-dir` or via `<loader_dir>` inside `CLIBatchLoaderConfig.xml`. DLLs must reside in the same folder as `BatchLoaderCmd.exe`.

## What it does

For every `*.txt` data file in your `--data-dir` (default: `./data`), the script:

1. **Finds the matching template**

   * Looks for `<stem>.xml` in `--templates-dir`, **or**
   * `<stem>_Template.xml` **next to** the data file.
2. **Runs** `BatchLoaderCmd.exe` **from the runtime folder** you specify (or that's embedded in the CLI config).
3. **Writes a log** to `--logs-dir` (default: `./logs`).
4. Skips files with missing templates with a clear `[SKIP]` message.

**Sorts files case-insensitively by name**, so you can control load order with filename prefixes (e.g., `001-User.txt`, `018-Document.txt`, `200-PartBOM.txt`, etc.).

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
C:\innovator\Release 35 CD Image\BatchLoader
```

---

### Step 2: Get the project files

Clone this repo (or copy `batchloader.py` + `CLIBatchLoaderConfig.xml` into a working folder). From that folder, you can initialize and run the loader.

---

### Step 3: Create a CLI config from the runtime (recommended)

If you already have a working **runtime** `BatchLoaderConfig.xml` (used by the UI), you can clone it into a clean **CLI** config and inject the loader path:

```powershell
python .\batchloader.py --init-config --init-from-runtime --bl-dir "C:\path\to\BatchLoader" --bl-config .\CLIBatchLoaderConfig.xml
```

This copies `BatchLoaderConfig.xml` from the runtime folder and adds a `<loader_dir>` element so future runs don’t need `--bl-dir`.

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

Security note: This file contains credentials. Use least‑privileged accounts and avoid committing real passwords. Commit sanitized examples instead.

</details>

## Data & Template Conventions

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

Retry mapping: For a `.failed` file named `001-Parts_TopAndAssemblies.failed`, the script looks for the template `001-Parts_TopAndAssemblies.xml` (in `--templates-dir`) or `001-Parts_TopAndAssemblies_Template.xml` (next to the data).

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

### Template & data structure

- Main items (e.g., Part, Document, User): map `@1`, `@2`, … to columns in your data files. Commonly `@1` is the item key (`id` or `item_number`) depending on template design.
  **Important for deletes:** For `Part` items, the generated delete template uses `where="item_number='@1'"`, so the **first** column in your Part TSV must be `item_number`.
- Relationships (Part BOM): include a stable `rel_id` as the FIRST column in your data. This enables precise deletes and loads.

Example Part BOM data (TSV):

| rel_id                           | source_item_number  | related_item_number | quantity | sort_order | reference_designator |
|----------------------------------|---------------------|---------------------|----------|------------|----------------------|
| 8EA46F18376246F891DDBADB9B9AEFCD | FRONT-WHEEL-700C    | HUB-FR-100QR        | 1        | 10         |                      |
| 9118A3A222BA451382CD26E0FF0B9B92 | FRONT-WHEEL-700C    | RIM-700C-24H        | 1        | 20         |                      |
| F96C5749C70544DF84F183D9A5BEF02F | FRONT-WHEEL-700C    | SPOKE-272           | 24       | 30         |                      |
| 5FD53E12231A4C238D22620E13BEB7AE | FRONT-WHEEL-700C    | NIPPLE-14G          | 24       | 40         |                      |

Reference designators may be blank if not used.

Example Part BOM template (add):

```xml
<AML>
  <Item type="Part BOM" action="add" id="@1">
    <source_id>
      <Item type="Part" action="get" select="id">
        <item_number>@2</item_number>
      </Item>
    </source_id>
    <related_id>
      <Item type="Part" action="get" select="id">
        <item_number>@3</item_number>
      </Item>
    </related_id>
    <quantity>@4</quantity>
    <sort_order>@5</sort_order>
    <reference_designator>@6</reference_designator>
  </Item>
</AML>
```

Notes:
- For deletes, the CLI generates a delete-template that deletes by `id` for Part BOM and by `item_number` for Parts.

</details>

## Usage

### Windows

For a minimal first run on Windows, see Quick Start above.

```powershell 
# Using loader_dir embedded in CLIBatchLoaderConfig.xml
python .\batchloader.py

# OR: override at runtime (if no <loader_dir> in the CLI config)
python .\batchloader.py --bl-dir "C:\innovator\Release 35 CD Image\BatchLoader"
```

<details>
<summary>Non‑Windows (Linux/macOS) via Wine</summary>

Windows: primary/known-good target. Linux/macOS: should work via Wine (ensure `wine` is on PATH and .NET 4.8 is installed in the Wine prefix, e.g., `winetricks dotnet48`).

- Install Wine (works with 7+); ensure `wine` is on PATH.
- BatchLoader is a Windows .NET app; install .NET Framework in your Wine prefix (e.g., `winetricks dotnet48`). Wine‑Mono alone may not suffice.
- Use `--bl-dir` to the BatchLoader runtime folder (with DLLs) accessible to Wine.
- Prefer absolute paths for `--bl-dir` and run from a directory Wine can access.

Example:

```bash
# Load data
python3 ./batchloader.py --bl-dir "/innovator/CDImage35Release/BatchLoader"

# Delete data
python3 ./batchloader.py --delete --bl-dir "/innovator/CDImage35Release/BatchLoader"

# Clean failed files
python3 ./batchloader.py --clean-failed
```

</details>

---

## Logs, Exit Codes, and Retries

* Each run writes a **per-file log** into `--logs-dir`, e.g., `logs/001-User.log`.
* If `BatchLoaderCmd.exe` returns non-zero, the script prints:
  `-> non-zero exit (<code>); check <logfile>`
*  BatchLoader writes a `<stem>.failed` file containing rows that did not load.

### Fast retries

If a run generates `.failed` row files, they’ll be written to your data directory using the data file’s stem (no `.txt`).
Example:
`data\001-Parts_TopAndAssemblies.txt` ➜ `data\001-Parts_TopAndAssemblies.failed`

```powershell
# Looks in ./data for *.failed and replays them
python .\batchloader.py --retry

# If your .failed files are in a different location:
python .\batchloader.py --retry --retry-dir .\some\other\folder

# You can still provide a separate templates directory if you keep templates out of /data
python .\batchloader.py --retry --templates-dir .\templates
```

**Notes**

- Looks for files ending in `.failed` in `--retry-dir` (if provided) or `--data-dir` (default: `./data`).
- `.failed` filenames match the original data file’s stem (no `.txt`). Example mapping:
  - Data file: `001-Parts_TopAndAssemblies.txt`
  - Retry file: `001-Parts_TopAndAssemblies.failed`
- Template resolution during retries:
  - `--templates-dir/001-Parts_TopAndAssemblies.xml`, else
  - `data/001-Parts_TopAndAssemblies_Template.xml`.
- Logs go to `./logs/retry/<stem>.retry.log` (e.g., `logs/retry/001-Parts_TopAndAssemblies.retry.log`).



**Run with default locations (data in `./data`, logs to `./logs`):** See the Windows section under [Usage](#usage).

**Run from macOS/Linux with Wine:** See the macOS/Linux section under [Usage](#usage).

---

## Delete Mode

The `--delete` flag provides a straight-forward way to remove what you just loaded:

```powershell
# Delete everything in reverse order (BOMs first, then Parts)
python .\batchloader.py --delete

# Specify custom delete templates directory
python .\batchloader.py --delete --delete-templates-dir .\custom_delete_templates
```

How it works:
- Processes files in reverse order (BOMs before Parts to respect dependencies).
- Auto-generates delete templates based on your existing insert templates.
- For Part BOM relationships: uses the custom `rel_id` from your data files for precise deletion.
- For Parts: uses a `where="item_number='@1'"` clause. Ensure column 1 of your Part file is `item_number`.
- Logs all deletions to `./logs/delete/`.

Safety tip: Try `--delete` on a disposable environment first; deletes are irreversible.

 

## Clean Failed Files

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
