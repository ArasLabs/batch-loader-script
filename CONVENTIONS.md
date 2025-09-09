# Data & Template Conventions

This document covers recommended file organization, load ordering, and data/template formats used by the CLI wrapper.

## Ordering of Loads

- Files are processed in case-insensitive, lexicographic order.
  Example: `001-User.txt` → `005-Variable.txt` → `018-Document.txt` → `096-Customer.txt`.
- Put base “main items” first (e.g., `User`, `Document`, `Part`, `Customer`).
- Put relationship rows after both sides exist (e.g., `Part Document` relations).
  - Example names: `200-PartDocumentRelationship.txt`, `200-PartDocumentRelationship_Template.xml`.

This helps avoid foreign-key or key-lookup failures during relationship inserts.

## Data and Template File Organization

By default, place data files (`*.txt`) and their corresponding templates (`*_Template.xml`) together in the `data/` directory. This is the standard and simplest setup.

If you prefer a separate templates directory, run with `--templates-dir`. The script still expects data files in your `--data-dir` (default `./data`).

### How Templates Are Found

For each data file `<data-dir>/NNN-Name.txt` (where `NNN-Name` is the stem), the script searches for the template as follows:

1) If `--templates-dir` is specified: looks for `<templates-dir>/NNN-Name.xml`
2) Otherwise (or if not found): looks for `<data-dir>/NNN-Name_Template.xml` (next to the data file)

If no template is found, the file is skipped and a `[SKIP]` message is printed.

Retry mapping: For a `.failed` file named `001-Parts_TopAndAssemblies.failed`, the script looks for the template `001-Parts_TopAndAssemblies.xml` (in `--templates-dir`) or `001-Parts_TopAndAssemblies_Template.xml` (next to the data).

## CSV/TSV Format Expectations

### Delimiter and header detection

- The CLI reads `<delimiter>` from `CLIBatchLoaderConfig.xml` and uses it to split header rows when detecting the ID column for delete mode.
- Supported values include a literal tab, `\t`, `tab`, `,`/`comma`, `|`/`pipe`, or any single character.
- Ensure your data files use the same delimiter configured in the CLI config.

### Data File Requirements

- Files must match the `<delimiter>`, `<encoding>`, and `<first_row>` settings in `CLIBatchLoaderConfig.xml`.
- With headers (`<first_row> > 1`):
  - Include an ID column for delete mode:
    - Accepted header names (case-insensitive): `id`, `rel_id`, `relationship_id`.
    - The column may appear in any position — the CLI locates it by name and maps the correct column index for the generated delete template.
  - For add mode, templates only bind the columns they reference; additional columns (such as `id` for deletes) can remain unused by the add template.
- Without headers (`<first_row> <= 1`):
  - **Column 1 is treated as the ID for delete mode.**
  - This means headerless delete files **must** put the GUID in column 1.


- Item datasets (e.g., Part, Document, User):
  - Provide the Item’s GUID in the `id` column for delete mode (recommended header name: `id`).
  - When using the same file for add and delete, consider appending the ID column at the end so template indices used for add remain stable.
- Relationship datasets (e.g., Part BOM, custom relationships):
  - Provide the relationship row GUID in the ID column for delete mode.
  - Recommended header name: `rel_id` (alternatively `relationship_id` or `id`).
- Values in ID columns must be valid Innovator IDs for the target environment.
- Template placeholders `@1`, `@2`, … map to column positions used for add mode; positions are unaffected by columns that templates do not reference.


Example: using headers with an ID column at the end for an item dataset

```
item_number  name  description  major_rev  classification  unit  make_buy  cost  cost_basis  id
```

Template placeholders `@1`, `@2`, … map to the column index in your file. Add templates are unaffected by extra columns like `id` if they are not referenced.

Example (`001-User_Template.xml`):

```xml
<Item type="User" action="merge" id="@1">
  <last_name>@2</last_name>
  <first_name>@3</first_name>
  <!-- ... -->
  </Item>
```


## Mandatory ID Column for Deletes

- Items: include an `id` column with the Item’s GUID. With headers, the column can be anywhere; without headers, place the GUID in column 1.
- Relationships: include a relationship row GUID column named `id`, `rel_id`, or `relationship_id` (case-insensitive). With headers, the column can be anywhere; without headers, place the GUID in column 1.
- The CLI reads `<first_row>` and `<delimiter>` from `CLIBatchLoaderConfig.xml` to find the ID column when generating delete templates.


## Template & Data Structure

- Main items (e.g., Part, Document, User): map `@1`, `@2`, … to columns in your data files. Template design determines which columns are referenced for adds. For delete mode, include an ID column (Item GUID) somewhere in the file when using headers; if files are headerless, place the ID at column 1.
- Relationships (e.g., Part BOM): include an ID column for each relationship row. Column names `id`, `rel_id`, or `relationship_id` are accepted (case-insensitive). With headers, the column can appear anywhere; without headers, place the ID at column 1.

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
