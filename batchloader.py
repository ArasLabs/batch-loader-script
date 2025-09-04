#!/usr/bin/env python3
# Minimal Aras BatchLoader driver (CLI-only config with no UI mixing)
# Requires the Aras BatchLoader runtime folder; pass with --bl-dir or embed <loader_dir> in CLIBatchLoaderConfig.xml.

import argparse, platform, shutil, subprocess, sys
from pathlib import Path
import xml.etree.ElementTree as ET


def is_windows() -> bool:
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


def make_delete_template(add_template: Path, dest_dir: Path) -> Path:
    """
    Create a 'delete' variant of an existing add-template.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    tree = ET.parse(str(add_template))
    root = tree.getroot()

    # First AML Item node (BatchLoader templates typically have one)
    item_el = root.find(".//Item")
    if item_el is None:
        sys.exit(f"ERROR: Could not find <Item> in template: {add_template}")

    # Flip action to delete
    item_type = (item_el.get("type") or "").strip().lower()
    item_el.set("action", "delete")

    if item_type in {"part bom", "part_bom", "partbom"}: # For Part BOM we use delete by ID
        for child in list(item_el):
            item_el.remove(child)
        if not item_el.get("id"):
            item_el.set("id", "@1")
    elif item_type in {"part"}: # For Part we use where="item_number='@1'"
        for child in list(item_el):
            item_el.remove(child)
        item_el.set("where", "item_number='@1'") # NOTE: '@1' must be the item_number column in Part data file (see README).
    else: # For other types, keep id and item_number if present 
        keep_tags = {"id", "item_number", "keyed_name"} 
        for child in list(item_el):
            if child.tag not in keep_tags:
                item_el.remove(child)

    out_path = dest_dir / add_template.name
    tree.write(out_path, encoding="utf-8", xml_declaration=True) # Write the new delete template to the destination directory
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
    # Determine which config file to use
    if args.bl_config is not None:
        return args.bl_config
    else:
        return Path("./CLIBatchLoaderConfig.xml")


def run_init_config_if_requested(args: argparse.Namespace, cli_cfg: Path) -> bool:
    # Handle config initialization workflow
    if not args.init_config:
        return False

    if not args.init_from_runtime:
        sys.exit("ERROR: --init-config requires --init-from-runtime") 
    if not args.bl_dir:
        sys.exit("ERROR: --init-from-runtime requires --bl-dir to locate the runtime config")

    target = args.bl_config if args.bl_config is not None else Path("./CLIBatchLoaderConfig.xml")

    # If the target is a directory, append the CLIBatchLoaderConfig.xml file
    if target.exists() and target.is_dir():
        target = target / "CLIBatchLoaderConfig.xml"

    # Ensure that the target directory exists
    if not target.parent.exists():
        target.parent.mkdir(parents=True, exist_ok=True)

    # Load runtime config, inject <loader_dir>, pretty-print, and write to target
    runtime_cfg = args.bl_dir / "BatchLoaderConfig.xml"
    require(runtime_cfg, "Runtime BatchLoaderConfig.xml")

    def _indent(elem: ET.Element, level: int = 0, indent_char: str = "\t") -> None:
        """In-place pretty printer: adds newlines and tab indentation."""
        i = "\n" + (indent_char * level)
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = i + indent_char
            for child in elem:
                _indent(child, level + 1, indent_char)
                if not child.tail or not child.tail.strip():
                    child.tail = i + indent_char
            # Ensure the last child's tail brings us back to current level
            if not elem[-1].tail or not elem[-1].tail.strip():
                elem[-1].tail = i
        else:
            if not elem.text:
                elem.text = ""
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail = i

    try:
        tree = ET.parse(str(runtime_cfg))
        root = tree.getroot()

        # Only add <loader_dir> if missing; do not overwrite an existing one.
        if root.find("./loader_dir") is None:

            # Add the loader_dir comment, then the element itself
            root.append(ET.Comment(
                " Runtime folder used by the CLI script (absolute or relative to this file) "
            ))
            ET.SubElement(root, "loader_dir").text = str(args.bl_dir)

        # Pretty print with tabs to match existing style
        _indent(root, level=0, indent_char="\t")

        # Write the file with XML declaration
        tree.write(target, encoding="utf-8", xml_declaration=True)

        # Ensure a trailing newline at EOF for cleanliness
        try:
            with target.open("ab") as f:
                f.seek(0, 2)
                f.write(b"\n")
        except Exception:
            pass
    except Exception as e:
        sys.exit(f"ERROR: failed to initialize CLI config: {e}")

    print(f"Initialized CLI config from runtime: {target.resolve()}")
    return True


def setup_runtime_env(args: argparse.Namespace, cli_cfg: Path) -> tuple[Path, Path, bool]:
    # Validate paths and setup directories
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
    # Header
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
    data_files = sorted(args.data_dir.glob("*.txt"), key=lambda p: p.name.lower())
    if not data_files:
        sys.exit(f"ERROR: No *.txt files found in {args.data_dir}")
    if args.delete:
        # Reverse order: high-prefixed files (BOMs) first, then base parts last
        data_files = list(reversed(data_files))
    return data_files


def process_normal_mode(
    args: argparse.Namespace,
    exe: Path,
    cli_cfg: Path,
    runtime_dir: Path,
    use_wine: bool,
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
                template = make_delete_template(add_tpl, args.delete_templates_dir)
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

    # Header
    print_header(exe, cli_cfg, args)

    # ----- RETRY MODE -----
    if args.retry:
        run_retry_mode(args, exe, cli_cfg, runtime_dir, use_wine)
        return

    # ----- NORMAL MODE -----
    process_normal_mode(args, exe, cli_cfg, runtime_dir, use_wine)


if __name__ == "__main__":
    main()
