# Evolution DataEditor

<img width="1403" height="747" alt="Editor1" src="https://github.com/user-attachments/assets/cc7e5d40-b2c3-48e6-96c0-8725e27321ea" />
<img width="1883" height="891" alt="Editor2" src="https://github.com/user-attachments/assets/e79e1cf5-9c75-4c94-8159-7d5e8c028ca8" />
<img width="1665" height="761" alt="Editor3" src="https://github.com/user-attachments/assets/145a8a57-7aca-446e-9999-450eab4f1578" />

All-in-one tool to **analyze Yu-Gi-Oh! scripts** and **edit/inspect cards** from `.cdb` (SQLite) databases and local resources (scripts `c*.lua`, `strings.conf`, images).

Includes:
- An **Analyzer module** to detect inconsistencies between CDB ↔ scripts ↔ strings.
- A **DataEditorX-style visual editor** (locally served web UI) with advanced filters, preview, and decoding.

## Key Features

### Editor (UI)
- **Card list** with pagination, total counter, and fast selection.
- **Search by ID / name / description**:
  - Case-insensitive.
  - Accent-insensitive.
  - Highlights matches in the list and in fields (ID/Name); the full description is shown in the analysis panel.
- **Read-only by default**:
  - All fields are disabled to prevent accidental edits.
  - Editing is enabled only after pressing **Modify**.
- **Composable filters (Advanced Filters)** using the same editor controls:
  - Rule (Format), Attribute, Level/Rank/Link, Race, Archetypes.
  - **Type** and **Category/Genre** bitmask checkboxes.
  - **Pre-Released** filter (IDs longer than 8 digits).
  - Filters can be combined.
- **Multi-archetype (Setcode)**:
  - Up to **4 archetypes** per card (16-bit blocks).
  - Unknown sets are shown as `Unknown Set (0xXXXX)`.
- **Link Markers**
  - 3×3 grid to view/edit markers (Link monsters).
  - On typical `.cdb`, markers are interpreted from `def` as a bitmask (DataEditorX approach).
- **Category/Genre (Effect Categories)**:
  - Shows flags like `Special Summon`, `Recovery`, etc. from `datas.category`.
  - Clear visualization even when controls are disabled.
- **Responsive/adaptive layout**:
  - Spacing/size adjustments for different resolutions.
  - Scroll applied to whole sections when needed (no content clipping).

### Script Analysis (Analyzer module)
- Loads local resources (configurable):
  - `.cdb` folder
  - scripts folder (`c*.lua`)
  - `strings.conf`
  - images folder (optional)
- Detects and reports common issues:
  - `strX` references used in scripts without corresponding text.
  - CDB texts not used by the script (orphans).
  - Missing scripts.
  - Excluded cards (based on internal rules).
- Exports results to `resultados.json` for the UI.

## Project Structure

- `srt_advanced.py` — local server + API + main logic.
- `index.html` — editor/analyzer UI.
- `config_app.json` — local paths (CDB, scripts, strings, pics).
- `config/cardinfo_english.txt` — constants (rule/attribute/level/type/category/flags/setname).
- `card_decoder.py` — decoding (type, setname, rule, etc).
- `editor_constants.py`, `card_info_parser.py` — parser/cache for `cardinfo_english.txt`.

Optional utilities (if present in your checkout):
- `export_editor_cards.py`, `inspect_*.py`, `resolve_unknown_sets.py`, `stats_editor_cards.py`
- `tests/`

## Requirements

- Windows (recommended for the current workflow; may work on other OS with Python).
- Python 3.x (when running from source).
- Local access to:
  - `.cdb` (SQLite) with `datas` and `texts` tables
  - `c*.lua` scripts
  - `strings.conf`

## Dependencies

This project mainly uses the Python standard library.

Optional dependency:
- `requests` (used by `srt_advanced.py` for GitHub download mode). Install it if you plan to use that feature.

Install (recommended in a virtual environment):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install requests
```

## Setup & Run

### Option A: run from Python

1) (Optional but recommended) Activate your virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

2) Start the app:

```powershell
python .\srt_advanced.py
```

Then open the browser when the app prompts you (or visit the `localhost` URL it prints).

### Option B: run the EXE (if present)

Run `dist/AnalizadorScriptsYuGiOh.exe` (if it exists).

## Configuration (`config_app.json`)

Example:

```json
{
  "pics_dir": "D:/Game/MDPro3/Picture/Art",
  "cdb_dir": "C:/path/to/cdb",
  "script_dir": "C:/path/to/scripts",
  "strings_conf": "D:/path/to/strings.conf"
}
```

The app lets you configure these paths from the UI and persists them in this file.

## DataEditorX Reference

This project is **based on** and takes reference from the original **DataEditorX** editor:

- `https://github.com/Lyris12/DataEditorX`

In particular, it borrows ideas for:
- The overall editor layout.
- Interpreting **Link Markers** as a bitmask (commonly stored in `def` for Link monsters).
- Interpreting **Category/Genre** as a bitmask (commonly stored in `datas.category` for standard `.cdb`).

On standard `.cdb`, “Flags (category)” in the Omega/DataEditorX sense usually does not exist as a separate field.

## Repo Cleanup

See `CLEANUP.md` and the `cleanup_unused.ps1` script.

## License

Add your license here (MIT, GPL, etc.) as appropriate for your repo.
