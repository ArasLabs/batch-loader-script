#!/usr/bin/env python3
# Minimal Aras BatchLoader driver (CLI-only config; no UI mixing)

import argparse, platform, shutil, subprocess, sys
from pathlib import Path
import xml.etree.ElementTree as ET


def is_windows() -> bool:
    return platform.system().lower().startswith("win")

def require(p: Path, what: str) -> None:
    """Verify that a required file or directory exists, exit with error if not found.

    Args:
        p (Path): The file or directory path to check for existence.
        what (str): Human-readable description of what is being checked (used in error message).

    Returns:
        None: Returns nothing on success, exits program with error code on failure.
    """
    if not p.exists():
        sys.exit(f"ERROR: {what} not found: {p}")


def find_template(
    data_file: Path,
    templates_dir: Path | None = None,
    operation: str = "add",
) -> Path | None:
    """Find the matching template XML file for a given data file.

    Searches for template files depending on the desired operation.
    Naming conventions:
    - add   : Templates/{name}.xml OR next to data: {name}_Template.xml

    Args:
        data_file (Path): The input data file (e.g., tools.txt) where to find a template.
        templates_dir (Path | None, optional): Directory to search for template files first. 
            If None, only searches alongside the data file. Defaults to None.

    Returns:
        Path | None: Path to the matching template file if found, None if no template exists.
    """
    name = data_file.stem
    candidates: list[Path] = []
    if operation == "add":
        if templates_dir is not None:
            candidates.append(templates_dir / f"{name}.xml")
        candidates.append(data_file.with_name(f"{name}_Template.xml"))
    else:
        return None

    # Ensure that the candidate template file exists
    for c in candidates:
        if c.exists():
            return c
    return None


def read_loader_dir_from_config(cfg_path: Path) -> Path | None:
    """Extract the loader_dir path from a BatchLoader config XML file.

    Parses the XML configuration to find the <loader_dir> element. If path is relative,
    it is resolved relative to the configuration file's parent directory.

    Args:
        cfg_path (Path): Path to the BatchLoader configuration XML file to parse.

    Returns:
        Path | None: Absolute path to the loader directory if found and non-empty, 
            None if the element doesn't exist, is empty, or if XML parsing fails.
    """
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
    """Build the command line arguments for BatchLoaderCmd.exe.

    Constructs the full command with all required parameters for the Aras BatchLoader. Resolve turns the path to an absolute path.

    Args:
        exe (Path): Path to the BatchLoaderCmd.exe executable.
        bl_cfg (Path): Path to the BatchLoader configuration XML file containing connection settings.
        data (Path): Path to the input data file (typically tab-delimited .txt file).
        template (Path): Path to the AML template XML file defining the import mapping.
        log (Path): Path where the batch loader should write its execution log.
        use_wine (bool): Whether to prefix the command with 'wine' for non-Windows systems.

    Returns:
        list[str]: Complete command line as a list of strings suitable for subprocess.run().
    """
    # Resolve the paths to absolute paths
    data = data.resolve()
    template = template.resolve()
    log = log.resolve()
    bl_cfg = bl_cfg.resolve()
    cmd = ["wine", str(exe)] if use_wine else [str(exe)]
    return cmd + ["-d", str(data), "-c", str(bl_cfg), "-t", str(template), "-l", str(log)]


def main() -> None:
    """Main entry point for the BatchLoader CLI wrapper.

    Handles two primary workflows:
    1. Config initialization: Copies runtime config to create a local CLI config
    2. Batch loading: Processes all .txt files in data directory using their templates

    The function manages the entire batch loading lifecycle including:
    - Parsing command line arguments
    - Validating required files and directories
    - Setting up Wine for non-Windows systems if needed
    - Processing each data file with its template
    - Handling retry logic for failed items
    - Cleaning up temporary files

    Returns:
        None: Exits with status code 0 on success, non-zero on error.
    """
    ap = argparse.ArgumentParser(description="Minimal BatchLoader runner (separate CLI config).")
    ap.add_argument(
        "--dl-dir",
        dest="dl_dir",
        type=Path,
        required=False,
        help=(
            "Folder that contains BatchLoaderCmd.exe and its DLLs (runtime)."
        ),
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
    ap.add_argument("--templates-dir", type=Path, default=None)
    ap.add_argument(
        "--operation",
        "--op",
        choices=["add"],
        default="add",
        help="Operation mode: add",
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
        "--init-config",
        action="store_true",
        help=(
            "Copy runtime BatchLoaderConfig.xml to local CLI config. "
            "Requires --init-from-runtime and --dl-dir."
        ),
    )
    ap.add_argument(
        "--init-from-runtime",
        action="store_true",
        help="Required with --init-config. Copies runtime's BatchLoaderConfig.xml.",
    )
    args = ap.parse_args()

    # Determine which config file to use
    if args.bl_config is not None:
        cli_cfg = args.bl_config
    else:
        cli_cfg = Path("./CLIBatchLoaderConfig.xml")

    # Handle config initialization workflow
    if args.init_config:
        if not args.init_from_runtime:
            sys.exit("ERROR: --init-config requires --init-from-runtime") 
        if not args.dl_dir:
            sys.exit("ERROR: --init-from-runtime requires --dl-dir to locate the runtime config")
        
        target = args.bl_config if args.bl_config is not None else Path("./CLIBatchLoaderConfig.xml")

        # If the target is a directory, append the CLIBatchLoaderConfig.xml file
        if target.exists() and target.is_dir():
            target = target / "CLIBatchLoaderConfig.xml"

        # Ensure that the target directory exists
        if not target.parent.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
        
        # Copy runtime config and inject loader_dir path    
        runtime_cfg = args.dl_dir / "BatchLoaderConfig.xml"
        require(runtime_cfg, "Runtime BatchLoaderConfig.xml")
        try:
            xml_bytes = runtime_cfg.read_bytes()
            target.write_bytes(xml_bytes)
            # Add loader_dir to config so we don't need --dl-dir every time
            try:
                tree = ET.parse(str(target)) 
                root = tree.getroot()
                if root.find("./loader_dir") is None: # Add loader_dir to config so we don't need --dl-dir every time
                    ET.SubElement(root, "loader_dir").text = str(args.dl_dir)
                    tree.write(target, encoding="utf-8", xml_declaration=True)
            except ET.ParseError:
                pass
        except Exception as e:
            sys.exit(f"ERROR: failed to copy runtime config: {e}")
        print(f"Initialized CLI config from runtime: {target.resolve()}") 
        return

    # Validate paths and setup directories
    require(cli_cfg, "CLI config XML (e.g., CLIBatchLoaderConfig.xml)")
    
    runtime_dir = args.dl_dir or read_loader_dir_from_config(cli_cfg)
    if not runtime_dir:
        sys.exit("ERROR: No runtime provided. Set --dl-dir or <loader_dir> in your CLI config")
    exe = runtime_dir / "BatchLoaderCmd.exe" # set the exe path to the BatchLoaderCmd.exe in the runtime folder
    require(exe, "BatchLoaderCmd.exe") # Check if the exe exists
    
    if not args.data_dir.exists(): # Check if the data directory exists
        sys.exit(f"ERROR: data dir not found: {args.data_dir}")
    args.logs_dir.mkdir(parents=True, exist_ok=True)

    # Check if we need Wine for non-Windows systems
    use_wine = False
    if not is_windows():
        if shutil.which("wine"):
            use_wine = True
        else:
            sys.exit("ERROR: Windows EXE detected and no 'wine' found. Run on Windows/WSL or install wine.")

    # Header
    print(f"Runtime : {exe.parent}")
    print(f"Config  : {cli_cfg.resolve()}")
    print(f"Data    : {args.data_dir.resolve()}")
    print(f"Templates: {(str(args.templates_dir.resolve()) if args.templates_dir else '(next to data)')}")
    print(f"Operation: {args.operation}")
    print(f"Logs    : {args.logs_dir.resolve()}")
    print(f"Mode    : {'RETRY' if args.retry else 'NORMAL'}\n")

    # ----- RETRY MODE -----
    if args.retry:
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
            name = data.stem  # '001-User.failed' -> '001-User'
            # Try templates_dir/<name>.xml, else fallback to data/<name>_Template.xml
            template = find_template(data, args.templates_dir, args.operation)
            if not template:
                candidate = args.data_dir / f"{name}_Template.xml"
                if candidate.exists():
                    template = candidate
            if not template:
                print(f"[SKIP] {name}: missing template (Templates/{name}.xml or {name}_Template.xml)")
                continue

            log = retry_logs_dir / f"{name}.retry.log"
            print(f"[RETRY] {name}")

            rc = subprocess.run(
                build_cmd(exe, cli_cfg, data, template, log, use_wine),
                cwd=str(runtime_dir),
            ).returncode
            if rc != 0:
                print(f"  -> non-zero exit ({rc}); check {log}")
        print("\nDone.")
        return

    # ----- NORMAL MODE -----
    data_files = sorted(args.data_dir.glob("*.txt"), key=lambda p: p.name.lower())
    if not data_files:
        sys.exit(f"ERROR: No *.txt files found in {args.data_dir}")

    # Process each data file
    for data in data_files:
        name = data.stem
        
        template = find_template(data, args.templates_dir, args.operation)
        if not template:
            if args.operation == "add":
                missing_hint = f"Templates/{name}.xml or {name}_Template.xml"
            print(f"[SKIP] {name}: missing template ({missing_hint})")
            continue

        log = args.logs_dir / f"{name}.log"
        print(f"[LOAD] {name}")

        # Execute the BatchLoaderCmd.exe
        rc = subprocess.run(
            build_cmd(exe, cli_cfg, data, template, log, use_wine),
            cwd=str(runtime_dir),  # Run from runtime dir so DLLs are found
        ).returncode

        # If the BatchLoaderCmd.exe returned a non-zero exit code, print an error message
        if rc != 0:
            print(f"  -> non-zero exit ({rc}); check {log}")

    print("\nDone.")


if __name__ == "__main__":
    main()
