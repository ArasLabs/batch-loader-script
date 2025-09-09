#!/usr/bin/env python3
# Minimal Aras BatchLoader driver (CLI-only config with no UI mixing)
# Requires the Aras BatchLoader runtime folder; pass with --bl-dir or embed <loader_dir> in CLIBatchLoaderConfig.xml.

import argparse, platform, shutil, subprocess, sys
from pathlib import Path
import xml.etree.ElementTree as ET
# Required header name for the GUID of the Item/Relationship to delete (case-insensitive)
REQUIRED_ID_NAME = "id"

# Defaults and XML field order used when generating a clean CLI config
DEFAULT_CLI_CFG_NAME = "CLIBatchLoaderConfig.xml"
CLI_CFG_ORDER = [
    "server",
    "db",
    "user",
    "password",
    "max_processes",
    "delimiter",
    "threads",
    "encoding",
    "lines_per_process",
    "first_row",
    "log_level",
    "log_file",
]


#region XML Helpers
def _xml_indent(elem: ET.Element, level: int = 0, indent_char: str = "\t") -> None:
    """Pretty print: add newlines and indentation in-place (tabs by default)."""
    i = "\n" + (indent_char * level)
    if len(elem): 
        if not elem.text or not elem.text.strip(): # If the element has no text or the text is empty, add the indentation
            elem.text = i + indent_char
        for child in elem: # For each child of the element, add the indentation
            _xml_indent(child, level + 1, indent_char)
            if not child.tail or not child.tail.strip(): # If the child has no tail or the tail is empty, add the indentation
                child.tail = i + indent_char
        if not elem[-1].tail or not elem[-1].tail.strip(): # If the last child of the element has no tail or the tail is empty, add the indentation
            elem[-1].tail = i
    else:
        if not elem.text: # If the element has no text, add an empty string
            elem.text = ""
        if level and (not elem.tail or not elem.tail.strip()): # If the element has no tail or the tail is empty, add the indentation
            elem.tail = i


def _pick_first_text(root: ET.Element, tag: str) -> str:
    """First non-empty text for a tag. Then first. Then the empty string."""
    elems = root.findall(f"./{tag}")
    if not elems: 
        return "" 
    for el in elems: # For each element, get the text and strip whitespace
        txt = (el.text or "").strip()
        if txt: # If the text is not empty, return it
            return txt
    return (elems[0].text or "").strip() # If no non-empty text is found, return the first element's text and strip whitespace


def _resolve_init_target_path(bl_config_arg: Path | None) -> Path:
    """Resolve the target CLI config path. If an existing directory is passed, append default name. This is the path to the new CLI config file that will be created."""
    target = bl_config_arg if bl_config_arg is not None else Path(f"./{DEFAULT_CLI_CFG_NAME}")
    if target.exists() and target.is_dir():
        target = target / DEFAULT_CLI_CFG_NAME
    return target


def _build_cli_config_from_runtime(runtime_cfg: Path, loader_dir: Path) -> ET.Element:
    """Create a new minimal CLI config element from the runtime config and loader_dir."""
    src_tree = ET.parse(str(runtime_cfg)) 
    src_root = src_tree.getroot() 

    new_root = ET.Element("BatchLoaderConfig") # Root for new CLI config
    for tag in CLI_CFG_ORDER:
        ET.SubElement(new_root, tag).text = _pick_first_text(src_root, tag)

    new_root.append(ET.Comment(
        " Runtime folder used by the CLI script (absolute or relative to this file) "
    ))
    ET.SubElement(new_root, "loader_dir").text = str(loader_dir)

    return new_root


def _write_xml_pretty(root: ET.Element, target: Path, indent_char: str = "\t") -> None:
    """Write XML to target with pretty indentation and a trailing newline."""
    # Ensure parent directory exists
    if not target.parent.exists():
        target.parent.mkdir(parents=True, exist_ok=True)

    _xml_indent(root, level=0, indent_char=indent_char) 
    ET.ElementTree(root).write(target, encoding="utf-8", xml_declaration=True, short_empty_elements=False)

    # Ensure trailing newline at EOF
    try:
        with target.open("ab") as f:  # Open file in append binary mode
            f.seek(0, 2)  # Seek to end of file
            f.write(b"\n")
    except Exception:
        pass
#endregion


#region Core Helpers
def is_windows() -> bool:
    """Check if the platform is Windows."""
    return platform.system().lower().startswith("win")

def require(p: Path, what: str) -> None:
    """Exit if required file/dir is missing."""
    if not p.exists():
        sys.exit(f"ERROR: {what} not found: {p}")


def find_template(data_file: Path, templates_dir: Path | None = None) -> Path | None:
    """Return the template for a data file: prefer <templates_dir>/<stem>.xml,
    else <data_dir>/<stem>_Template.xml."""
    name = data_file.stem
    candidates: list[Path] = []

    # Search order matters: central templates dir or within data directory
    if templates_dir is not None:
        candidates.append(templates_dir / f"{name}.xml")
    candidates.append(data_file.with_name(f"{name}_Template.xml"))

    # Ensure that the candidate template file exists
    for c in candidates:
        if c.exists():
            return c
    return None


def _read_headers_for(data_file: Path, delimiter: str | None = None) -> list[str]:
    """
    Read the first (header) line from a delimited data file and return a list of header names.
    Returns [] if the file cannot be read.

    Note: This helper is only used when the CLI config indicates headers
    (i.e., <first_row> > 1). For headerless files (<first_row> <= 1) we never
    call this; deletes bind id to column 1 without inspecting headers.
    """
    try:
        with data_file.open("r", encoding="utf-8") as f:
            first_line = f.readline().strip("\r\n")  # Read first line and remove line endings
        # Determine delimiter (default to tab)
        sep = delimiter or "\t"
        # Split by configured delimiter to get raw header columns
        raw_headers = first_line.split(sep)
        
        # Strip whitespace and filter out empty strings
        headers = [header.strip() for header in raw_headers if header.strip()]
        return headers
    except Exception:
        return []  # Return empty list if file can't be read

def _find_id_col(headers: list[str]) -> int | None:
    """Return 1-based index of the required 'id' column (case-insensitive)."""
    lower_headers = [h.lower() for h in headers]
    for idx, header in enumerate(lower_headers):
        if header == REQUIRED_ID_NAME:
            return idx + 1
    return None


def make_delete_template(
    add_template: Path,
    dest_dir: Path,
    data_file: Path | None = None,
    first_row: int | None = None,
    delimiter: str | None = None,
) -> Path:
    """
    Create a 'delete' variant of an existing add-template (ID-only deletes).

    Headerless files are fully supported:
      - If <first_row> <= 1 (no header row), we DO NOT read the data file.
        We bind the delete key as id="@1" (column 1 is assumed to be the GUID).
      - If <first_row> > 1 (headers present), we read the header row from
        the data file and locate the GUID column by the required 'id' header.
        We then bind id="@<index>".

    This function never deletes by business keys (e.g., item_number). Deletes
    are always by GUID, either base Item id or relationship id.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    tree = ET.parse(str(add_template))
    root = tree.getroot()

    # First AML Item node (BatchLoader templates typically have one)
    item_el = root.find(".//Item")
    if item_el is None:
        raise RuntimeError(f"Could not find <Item> in template: {add_template}")

    # Always perform delete by ID on the Item element itself
    item_el.set("action", "delete")
    # Remove all children; delete keying lives on the Item element (id attribute)
    for child in list(item_el):
        item_el.remove(child)

    # Decide header presence strictly from config:
    #   first_row > 1  ⇒ a header row exists in the data file
    #   first_row <= 1 ⇒ headerless data (we do not inspect the file)
    header_expected = (first_row or 1) > 1
    if not header_expected:
        # Headerless mode: GUID must be in column 1 for all types (base/relationship)
        item_el.set("id", "@1")
        if data_file:
            print(f"[WARN] No headers expected (<first_row>={first_row or 1}); "
                  f"assuming column 1 is the GUID in {data_file.name}")
        out_path = dest_dir / add_template.name
        _write_xml_pretty(root, out_path, indent_char="\t")
        return out_path

    # Headers are expected in this branch. We need to read them to locate the GUID column
    if not data_file:
        raise RuntimeError(
            "Delete-template generation expects a data file when <first_row> indicates "
            "a header row (> 1) so the GUID column can be discovered via the 'id' header."
        )
    headers = _read_headers_for(data_file, delimiter)
    if not headers:
        raise RuntimeError(
            f"Could not read header row from '{data_file.name}'. "
            "Verify <first_row> in your CLI config and the file encoding."
        )
    id_idx = _find_id_col(headers)
    if id_idx is None:
        raise RuntimeError(
            f"'{data_file.name}' must include an 'id' column containing the GUID for the item/relationship to delete."
        )

    item_el.set("id", f"@{id_idx}")

    out_path = dest_dir / add_template.name
    _write_xml_pretty(root, out_path, indent_char="\t") # Write the new delete template to the destination directory
    return out_path


def read_loader_dir_from_config(cfg_path: Path) -> Path | None:
    """Return absolute <loader_dir> from config, resolving relative paths against the config file."""
    try:
        tree = ET.parse(str(cfg_path)) 
        root = tree.getroot() 
        elem = root.find("./loader_dir") 
        if elem is None:
            return None
        value = (elem.text or "").strip()
        if not value:
            return None
        p = Path(value)
        if not p.is_absolute():
            # Resolve relative loader_dir against the config file's folder.
            p = (cfg_path.parent / p).resolve()
        return p
    except ET.ParseError:
        return None            

def _normalize_delimiter_text(raw: str | None) -> str | None:
    """Convert config <delimiter> text to an actual single-character delimiter.
    Supports literal tab, "\\t", and common names ("tab", "comma", "pipe").
    Defaults to tab when unrecognized or empty.
    """
    if raw is None:
        return None
    # Preserve a literal tab. do not strip() before checking
    if raw == "\t":
        return "\t"
    # Common textual encodings
    val = raw.strip()
    if not val:
        return "\t"
    lower = val.lower()
    if lower in {"\\t", "tab"}:
        return "\t"
    if lower in {",", "comma"}:
        return ","
    if lower in {"|", "pipe"}:
        return "|"
    # Single character custom delimiter
    if len(val) == 1:
        return val
    # Fallback to tab
    return "\t"

def read_delimiter_from_config(cfg_path: Path) -> str | None:
    """Read <delimiter> from XML config and normalize to a single character. Used for header parsing in delete mode."""
    try:
        tree = ET.parse(str(cfg_path))
        root = tree.getroot()
        elem = root.find("./delimiter")
        if elem is None:
            return None
        return _normalize_delimiter_text(elem.text)
    except ET.ParseError:
        return None


def read_first_row_from_config(cfg_path: Path) -> int | None:
    """
    Reads the <first_row> value from the given XML config file and returns it as an int.
    Returns None if the element is missing or invalid.
    """
    try:
        tree = ET.parse(str(cfg_path))
        root = tree.getroot()
        elem = root.find("./first_row") # Find the <first_row> element directly under the root
        if elem is None:
            return None
        value = (elem.text or "").strip() # Get the text value and strip whitespace
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None
    except ET.ParseError:
        return None            

def build_cmd(
    exe: Path,
    bl_cfg: Path,
    data: Path,
    template: Path,
    log: Path,
    use_wine: bool,
) -> list[str]:
    """Build the BatchLoaderCmd.exe invocation."""
    data = data.resolve()
    template = template.resolve()
    log = log.resolve()
    bl_cfg = bl_cfg.resolve()
    # Prefix command with 'wine' on non-Windows hosts so the EXE can run
    cmd = ["wine", str(exe)] if use_wine else [str(exe)] 
    return cmd + ["-d", str(data), "-c", str(bl_cfg), "-t", str(template), "-l", str(log)]
#endregion


#region CLI & Execution
def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Minimal BatchLoader runner (separate CLI config).")
    ap.add_argument(
        "--bl-dir",
        dest="bl_dir",
        type=Path,
        required=False,
        help="Folder that contains BatchLoaderCmd.exe and DLLs (runtime).",
    )
    ap.add_argument(
        "--bl-config",
        type=Path,
        default=None,
        help=(
            "Path to your CLI config XML. If omitted, uses ./CLIBatchLoaderConfig.xml."
        ),
    )
    ap.add_argument(
        "--data-dir",
        type=Path,
        default=Path("./data"),
        help="Directory containing *.txt data files (default: ./data)",
    )
    ap.add_argument(
        "--templates-dir",
        type=Path,
        default=None,
        help="Directory containing XML templates; fallback is next to each data file.",
    )
    ap.add_argument("--logs-dir", type=Path, default=Path("./logs"))

    ap.add_argument(
        "--retry",
        action="store_true",
        help="Retry mode: process *.failed files (from --retry-dir or --data-dir) instead of normal data/*.txt files.",
    )
    ap.add_argument(
        "--retry-dir",
        type=Path,
        default=None,
        help="Directory to search for *.failed files (defaults to --data-dir).",
    )

    ap.add_argument(
        "--delete",
        action="store_true",
        help="Delete mode: process files in reverse order using generated delete-templates."
    )
    ap.add_argument(
        "--delete-templates-dir",
        type=Path,
        default=Path("./templates_delete"),
        help="Directory where delete-templates will be generated (default: ./templates_delete)."
    )
    
    ap.add_argument(
        "--clean-failed",
        action="store_true",
        help="Remove all *.failed files from the data directory and exit."
    )

    ap.add_argument(
        "--init-config",
        action="store_true",
        help=(
            "Copy runtime BatchLoaderConfig.xml to local CLI config. "
            "Requires --init-from-runtime and --bl-dir."
        ),
    )
    ap.add_argument(
        "--init-from-runtime",
        action="store_true",
        help="Required with --init-config. Copies runtime's BatchLoaderConfig.xml.",
    )
    return ap.parse_args()

def handle_clean_failed(args: argparse.Namespace) -> bool:
    # Handle --clean-failed flag
    if not args.clean_failed: 
        return False
    failed_files = list(args.data_dir.glob("*.failed"))
    if not failed_files:
        print(f"No .failed files found in {args.data_dir}")
    else:
        print(f"Found {len(failed_files)} .failed file(s) to remove:")
        for f in failed_files:
            print(f"  - {f.name}")
            f.unlink() # Remove the failed file
        print(f"\nRemoved {len(failed_files)} .failed file(s).")
    return True


def resolve_cli_cfg(args: argparse.Namespace) -> Path:
    """Determine which config file to use"""
    if args.bl_config is not None:
        return args.bl_config
    else:
        return Path("./CLIBatchLoaderConfig.xml")

def run_init_config_if_requested(args: argparse.Namespace, cli_cfg: Path) -> bool:
    """Initialize a clean CLI config from the runtime config when requested."""
    if not args.init_config:
        return False

    if not args.init_from_runtime:
        sys.exit("ERROR: --init-config requires --init-from-runtime")
    if not args.bl_dir:
        sys.exit("ERROR: --init-from-runtime requires --bl-dir to locate the runtime config")

    target = _resolve_init_target_path(args.bl_config)

    runtime_cfg = args.bl_dir / "BatchLoaderConfig.xml"
    require(runtime_cfg, "Runtime BatchLoaderConfig.xml")

    try:
        new_root = _build_cli_config_from_runtime(runtime_cfg, args.bl_dir)
        _write_xml_pretty(new_root, target, indent_char="\t")
    except Exception as e:
        sys.exit(f"ERROR: failed to initialize CLI config: {e}")

    print(f"Initialized clean CLI config from runtime: {target.resolve()}")
    return True


def setup_runtime_env(args: argparse.Namespace, cli_cfg: Path) -> tuple[Path, Path, bool]:
    """Validate paths and setup directories"""
    require(cli_cfg, "CLI config XML (e.g., CLIBatchLoaderConfig.xml)")
    
    runtime_dir = args.bl_dir or read_loader_dir_from_config(cli_cfg)
    if not runtime_dir:
        sys.exit("ERROR: No runtime provided. Set --bl-dir or <loader_dir> in your CLI config")
    exe = runtime_dir / "BatchLoaderCmd.exe"
    require(exe, "BatchLoaderCmd.exe")

    if not args.data_dir.exists():
        sys.exit(f"ERROR: data dir not found: {args.data_dir}")
    if args.templates_dir and not args.templates_dir.exists():
        sys.exit(f"ERROR: templates dir not found: {args.templates_dir}")
    args.logs_dir.mkdir(parents=True, exist_ok=True)

    # Check if we need Wine for non-Windows systems
    use_wine = False
    if not is_windows():
        if shutil.which("wine"):
            use_wine = True
        else:
            sys.exit("ERROR: Windows EXE detected and no 'wine' found. Run on Windows/WSL or install wine.")

    return exe, runtime_dir, use_wine


def print_header(exe: Path, cli_cfg: Path, args: argparse.Namespace) -> None:
    print(f"Runtime : {exe.parent}")
    print(f"Config  : {cli_cfg.resolve()}")
    print(f"Data    : {args.data_dir.resolve()}")
    print(f"Templates: {(str(args.templates_dir.resolve()) if args.templates_dir else '(next to data)')}")
    print(f"Logs    : {args.logs_dir.resolve()}")
    print(f"Mode    : {'RETRY' if args.retry else ('DELETE' if args.delete else 'NORMAL')}\n")


def run_retry_mode(args: argparse.Namespace, exe: Path, cli_cfg: Path, runtime_dir: Path, use_wine: bool) -> None:
    failed_root = args.retry_dir or args.data_dir
    if not failed_root.exists():
        sys.exit(f"ERROR: retry dir not found: {failed_root}")
    failed_files = sorted(failed_root.glob("*.failed"), key=lambda p: p.name.lower())
    if not failed_files:
        sys.exit(f"ERROR: --retry specified but no *.failed files found in {failed_root}")

    retry_logs_dir = args.logs_dir / "retry"
    retry_logs_dir.mkdir(parents=True, exist_ok=True)

    print(f"Retrying {len(failed_files)} file(s) from: {failed_root.resolve()}\n")
    for data in failed_files:
        # '001-User.failed' -> stem '001-User'; we re-use the original template name
        name = data.stem
        # Retry uses the same template selection logic as normal mode
        # Try templates_dir/<name>.xml, else fallback to data/<name>_Template.xml
        template = find_template(data, args.templates_dir)
        if not template:
            candidate = args.data_dir / f"{name}_Template.xml" # Fallback to data/<name>_Template.xml
            if candidate.exists():
                template = candidate
        if not template:
            print(f"[SKIP] {name}: missing template (Templates/{name}.xml or {name}_Template.xml)") 
            continue

        log = retry_logs_dir / f"{name}.retry.log"
        print(f"[RETRY] {name}")

        # Run from runtime_dir so BatchLoaderCmd.exe can resolve its DLLs
        rc = subprocess.run(
            build_cmd(exe, cli_cfg, data, template, log, use_wine),
            cwd=str(runtime_dir),
        ).returncode
        if rc != 0:
            print(f"  -> non-zero exit ({rc}); check {log}")
    print("\nDone.")


def collect_data_files(args: argparse.Namespace) -> list[Path]:
    """Collect all *.txt files in the data directory"""
    data_files = sorted(args.data_dir.glob("*.txt"), key=lambda p: p.name.lower())
    if not data_files:
        sys.exit(f"ERROR: No *.txt files found in {args.data_dir}")
    if args.delete:
        # Reverse order: high-prefixed files (BOMs) first, then base items last
        data_files = list(reversed(data_files))
    return data_files


def process_normal_mode(
    args: argparse.Namespace,
    exe: Path,
    cli_cfg: Path,
    runtime_dir: Path,
    use_wine: bool,
    first_row: int | None,
    delimiter: str | None,
) -> None:
    data_files = collect_data_files(args)

    # Process each data file
    for data in data_files:
        name = data.stem

        # Resolve the "add" template as the source
        add_tpl = find_template(data, args.templates_dir)
        if not add_tpl:
            missing_hint = f"Templates/{name}.xml or {name}_Template.xml"
            print(f"[SKIP] {name}: missing template ({missing_hint})")
            continue

        # If deleting, transform to a delete template on the fly
        template = add_tpl
        logs_dir = args.logs_dir
        if args.delete:
            try:
                template = make_delete_template(
                    add_tpl,
                    args.delete_templates_dir,
                    data_file=data,
                    first_row=first_row,
                    delimiter=delimiter,
                )
            except Exception as e:
                print(f"[SKIP] {name}: could not build delete template: {e}")
                continue
            logs_dir = args.logs_dir / "delete"
            logs_dir.mkdir(parents=True, exist_ok=True)

        

        log = logs_dir / f"{name}.log"
        print(f"[{'DELETE' if args.delete else 'LOAD'}] {name}")

        # Run from runtime_dir so BatchLoaderCmd.exe can resolve its DLLs
        rc = subprocess.run(
            build_cmd(exe, cli_cfg, data, template, log, use_wine),
            cwd=str(runtime_dir),
        ).returncode
        if rc != 0:
            print(f"  -> non-zero exit ({rc}); check {log}")

    print("\nDone.")


def main() -> None:
    """CLI entrypoint."""
    args = parse_args()
    
    # Handle --clean-failed flag
    if handle_clean_failed(args):
        return

    # Determine which config file to use
    cli_cfg = resolve_cli_cfg(args)

    # Handle config initialization workflow
    if run_init_config_if_requested(args, cli_cfg):
        return

    exe, runtime_dir, use_wine = setup_runtime_env(args, cli_cfg)
    # Read first_row from CLI config to determine header presence for delete-template generation
    first_row = read_first_row_from_config(cli_cfg)
    # Read delimiter from CLI config for header parsing in delete mode
    delimiter = read_delimiter_from_config(cli_cfg)

    # Header
    print_header(exe, cli_cfg, args)

    # ----- RETRY MODE -----
    if args.retry:
        run_retry_mode(args, exe, cli_cfg, runtime_dir, use_wine)
        return

    # ----- NORMAL MODE -----
    process_normal_mode(args, exe, cli_cfg, runtime_dir, use_wine, first_row, delimiter)


if __name__ == "__main__":
    main()
#endregion
