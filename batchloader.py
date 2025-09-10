#!/usr/bin/env python3
# Minimal Aras BatchLoader driver (CLI-only config with no UI mixing)
# Requires the Aras BatchLoader runtime folder; pass with --bl-dir or embed <loader_dir> in CLIBatchLoaderConfig.xml.

import argparse, platform, shutil, subprocess, sys

from pathlib import Path
from xml_helpers import (
    _build_cli_config_from_runtime,
    _write_xml_pretty,
    make_delete_template,
    read_delimiter_from_config,
    read_first_row_from_config,
    read_loader_dir_from_config,
)
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


def _resolve_init_target_path(bl_config_arg: Path | None) -> Path:
    """Resolve the target CLI config path. If an existing directory is passed, append default name. This is the path to the new CLI config file that will be created."""
    target = bl_config_arg if bl_config_arg is not None else Path(f"./{DEFAULT_CLI_CFG_NAME}")
    if target.exists() and target.is_dir():
        target = target / DEFAULT_CLI_CFG_NAME
    return target


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
