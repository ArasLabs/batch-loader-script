from pathlib import Path
import xml.etree.ElementTree as ET

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
    """Normalize <delimiter> text to a single-char delimiter. Supports "\t", tab, comma, pipe."""
    if raw is None:
        return None
    if raw == "\t":
        return "\t"
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
    if len(val) == 1:
        return val
    return "\t"


def read_delimiter_from_config(cfg_path: Path) -> str | None:
    """Read <delimiter> from XML config and normalize to a single character."""
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
    """Read <first_row> as int; return None if missing/invalid."""
    try:
        tree = ET.parse(str(cfg_path))
        root = tree.getroot()
        elem = root.find("./first_row")
        if elem is None:
            return None
        value = (elem.text or "").strip()
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None
    except ET.ParseError:
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
        if header == "id":
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

    # First AML Item node
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
