# Modular Steam Downgrader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the monolithic `builds_rss.py` script into a clean, modular Python codebase (`main.py`, `src/`, `tests/`, `.cache/`) with zero external dependencies, robust test coverage, and cleanup of legacy prototypes.

**Architecture:** Split responsibilities into discrete modules: `steam_local.py` for registry/.acf operations and file copying, `steamdb.py` for SteamDB/steamcmd scraping, cache I/O, and manifest resolution, and `downloader.py` for orchestrating `Steam.exe +download_depot` and tailing logs. `main.py` orchestrates user interaction.

**Tech Stack:** Python 3.10+ (Standard Library only: `urllib.request`, `winreg`, `subprocess`, `xml.etree.ElementTree`, `socket`, `json`, `shutil`, `unittest`).

**Spec:** [docs/superpowers/specs/2026-11-03-modular-cleanup-design.md](file:///d:/Paulo/Projects/Steam/docs/superpowers/specs/2026-11-03-modular-cleanup-design.md)

## Global Constraints
- Target platform: Windows (`winreg`, `os.startfile`, `taskkill`, `Steam.exe`).
- Dependencies: Python Standard Library only; no third-party pip packages.
- All tests must use `unittest` and run via `python -m unittest discover tests`.
- Tests must be self-contained and never mutate or depend on the live cache file or real Steam installations.

## Review Focus
- ACF parser handles missing or malformed `InstalledDepots` gracefully without raising unhandled exceptions.
- Manifest resolution logic correctly selects target manifests within cutoff or matches build IDs.
- Cache read/write operations handle corrupted or empty JSON cache files cleanly.
- Copy tree function preserves directory structures and handles empty files properly.
- Downloader log tailing does not loop infinitely or crash when log files are truncated/recreated.

---

### Task 1: Project Setup, `.gitignore`, and Cache Directory Migration

**Files:**
- Create: `.gitignore`
- Create: `src/__init__.py`
- Create: `tests/__init__.py`
- Move/Create: `.cache/steamdb_cache.json`

**Interfaces:**
- Consumes: Existing `steamdb_cache.json` if present.
- Produces: Project root structure with `.cache/` directory and `.gitignore`.

- [ ] **Step 1: Create `.gitignore`**
Define ignore rules for `__pycache__/`, `*.pyc`, `.cache/`, `downloads/`, and `.depotdownloader/`.

- [ ] **Step 2: Create package directories and migrate cache**
Create `src/`, `tests/`, and `.cache/` directories. Move [steamdb_cache.json](file:///d:/Paulo/Projects/Steam/steamdb_cache.json) into `.cache/steamdb_cache.json` (or create an empty JSON object `{}` if absent). Create empty `src/__init__.py` and `tests/__init__.py`.

- [ ] **Step 3: Verify setup**
Run: `Test-Path .gitignore, src, tests, .cache/steamdb_cache.json`
Expected: All return `True`.

---

### Task 2: Local Steam Operations (`src/steam_local.py`) and Tests

**Files:**
- Create: `src/steam_local.py`
- Create: `tests/test_steam_local.py`

**Interfaces:**
- Produces:
  - `find_steam() -> tuple[pathlib.Path | None, list[pathlib.Path]]`
  - `parse_acf_depots(acf_text: str) -> list[dict[str, str]]`
  - `list_installed_games(libs: list[pathlib.Path]) -> list[dict]`
  - `copy_tree_with_progress(src_dir: pathlib.Path, dst_dir: pathlib.Path, label: str = "") -> None`
  - `freeze_app_manifest(acf_path: pathlib.Path) -> None`

- [ ] **Step 1: Write failing tests in `tests/test_steam_local.py`**
Test `parse_acf_depots` with sample ACF text (both valid depots and missing blocks), and test `copy_tree_with_progress` and `freeze_app_manifest` with temporary directories.

- [ ] **Step 2: Run tests to verify failure**
Run: `python -m unittest tests/test_steam_local.py`
Expected: FAIL (ModuleNotFoundError: No module named 'src.steam_local')

- [ ] **Step 3: Implement `src/steam_local.py`**
Extract and clean up local Steam routines from `builds_rss.py`:
  - `find_steam()`: reads `Software\Valve\Steam` registry, parses `libraryfolders.vdf`.
  - `parse_acf_depots(acf_text)`: regex extraction of depot IDs and manifest IDs.
  - `list_installed_games(libs)`: scans library folders for `appmanifest_*.acf` files.
  - `copy_tree_with_progress(src, dst, label)`: binary buffered copy with progress calculation.
  - `freeze_app_manifest(acf_path)`: sets `AutoUpdateBehavior` to `1` and applies read-only file attribute (`stat.S_IREAD`).

- [ ] **Step 4: Run tests to verify pass**
Run: `python -m unittest tests/test_steam_local.py`
Expected: OK

---

### Task 3: SteamDB, API Client, and Manifest Resolution (`src/steamdb.py`) and Tests

**Files:**
- Create: `src/steamdb.py`
- Create: `tests/test_steamdb.py`

**Interfaces:**
- Consumes: `.cache/steamdb_cache.json`
- Produces:
  - `http_get(url: str, timeout: int = 15) -> bytes`
  - `parse_patchnotes_rss(xml_bytes: bytes) -> list[dict]`
  - `parse_steamdb_manifest_date(text: str) -> datetime`
  - `load_cache(cache_file: pathlib.Path) -> dict`
  - `save_to_cache(cache_file: pathlib.Path, depot_id: str, rows_raw: list) -> None`
  - `fetch_app_info(app_id: int) -> dict`
  - `resolve_build_depots(build: dict, depots: list, manifests_by_depot: dict) -> list[dict]`
  - `cdp_fetch_depot_manifests(depot_ids: list, cache_file: pathlib.Path) -> dict`

- [ ] **Step 1: Write failing tests in `tests/test_steamdb.py`**
Test `parse_patchnotes_rss` with sample XML fixture, `parse_steamdb_manifest_date` with date string variations, `resolve_build_depots` with fixture manifests, and `load_cache`/`save_to_cache` with a temporary cache file path.

- [ ] **Step 2: Run tests to verify failure**
Run: `python -m unittest tests/test_steamdb.py`
Expected: FAIL (ModuleNotFoundError: No module named 'src.steamdb')

- [ ] **Step 3: Implement `src/steamdb.py`**
Implement network and SteamDB parsing logic with simplifications:
  - Deduplicate cache JSON reading in `load_cache` and `save_to_cache`.
  - Cache entries store only `manifest` and parsed `dt`.
  - In `cdp_fetch_depot_manifests`: clean up WebSocket framing to simplify payload framing (requests are always small control payloads < 125 bytes).
  - Implement `fetch_app_info(app_id)` to query `api.steamcmd.net/v1/info/{app_id}` and return filtered depots.

- [ ] **Step 4: Run tests to verify pass**
Run: `python -m unittest tests/test_steamdb.py`
Expected: OK

---

### Task 4: Steam Depot Downloader Engine (`src/downloader.py`) and Tests

**Files:**
- Create: `src/downloader.py`
- Create: `tests/test_downloader.py`

**Interfaces:**
- Consumes:
  - `src.steam_local: find_steam`
- Produces:
  - `tail_file(path: pathlib.Path, last_pos: int, line_filter: callable = None) -> tuple[int, list[str]]`
  - `download_depots(steam_path: pathlib.Path, app_id: int, todo_depots: list[dict], max_retries: int = 5) -> pathlib.Path`

- [ ] **Step 1: Write failing tests in `tests/test_downloader.py`**
Test `tail_file` helper with normal appends, truncated files, and non-existent files.

- [ ] **Step 2: Run tests to verify failure**
Run: `python -m unittest tests/test_downloader.py`
Expected: FAIL (ModuleNotFoundError: No module named 'src.downloader')

- [ ] **Step 3: Implement `src/downloader.py`**
Implement the unified `tail_file` helper to deduplicate `console_log.txt` and `content_log.txt` parsing.
Implement `download_depots` executing `Steam.exe +download_depot <app_id> <depot_id> <manifest_id>` with retry logic, progress monitoring, and cleanup of interrupted depot directories.

- [ ] **Step 4: Run tests to verify pass**
Run: `python -m unittest tests/test_downloader.py`
Expected: OK

---

### Task 5: Orchestration CLI (`main.py`) & Launcher Batch Script

**Files:**
- Create: `main.py`
- Modify: `steam-downgrade.bat`

**Interfaces:**
- Consumes:
  - `src.steam_local: find_steam, list_installed_games, copy_tree_with_progress, freeze_app_manifest`
  - `src.steamdb: parse_patchnotes_rss, fetch_app_info, resolve_build_depots, cdp_fetch_depot_manifests, http_get`
  - `src.downloader: download_depots`
- Produces:
  - `main()` interactive CLI loop.

- [ ] **Step 1: Implement `main.py`**
Structure into clean helper functions:
  - `prompt_game_selection(games)`
  - `prompt_build_selection(builds)`
  - `display_plan_table(plan, depots_obj, game)`
  - `main()`: Orchestrates game selection -> RSS build fetch -> depot resolution -> download -> install/freeze.

- [ ] **Step 2: Update `steam-downgrade.bat`**
Update script to run `main.py`:
```bat
@py "%~dp0main.py" %* || @python "%~dp0main.py" %*
@pause
```

- [ ] **Step 3: Run full test suite and verify CLI entry point**
Run: `python -m unittest discover tests` and `python main.py --help` (or verify clean import with `python -c "import main"`).
Expected: All tests pass and import succeeds.

---

### Task 6: Cleanup of Obsolete Prototypes & Verification

**Files:**
- Delete: `build.py`
- Delete: `rss_test.py`
- Delete: `builds_rss.py`
- Delete: `steamdb_cache.json` (since migrated to `.cache/steamdb_cache.json`)
- Delete: `.depotdownloader/`
- Delete: `downloads/`

- [ ] **Step 1: Run comprehensive tests**
Run: `python -m unittest discover tests`
Expected: All unit tests pass cleanly.

- [ ] **Step 2: Delete legacy prototype files and directories**
Remove legacy files: `build.py`, `rss_test.py`, `builds_rss.py`, `steamdb_cache.json`, `.depotdownloader`, and `downloads`.

- [ ] **Step 3: Final verification**
Check root directory listing to verify only clean files remain (`main.py`, `steam-downgrade.bat`, `src/`, `tests/`, `.cache/`, `docs/`, `.gitignore`).
Verify `python -c "import main; print('Ready')"` outputs `Ready`.
