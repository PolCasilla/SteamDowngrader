# Steam Downgrader Modular Cleanup — Design Spec

## Intent & Why
Reorganize the working Steam Downgrader prototype (`builds_rss.py` and surrounding scratch files) into a clean, maintainable modular workspace (`src/`, `tests/`, `.cache/`) for ongoing development, while trimming duplicated and dead code inside the implementation.

## Goals, Non-Goals, and Anti-Goals
- **Goals:**
  - Split [builds_rss.py](file:///d:/Paulo/Projects/Steam/builds_rss.py) into focused modules under `src/` (`steam_local.py`, `steamdb.py`, `downloader.py`) with `main.py` as the CLI entry point.
  - Move runtime cache data ([steamdb_cache.json](file:///d:/Paulo/Projects/Steam/steamdb_cache.json)) into `.cache/steamdb_cache.json` so runtime state does not pollute the root directory.
  - Extract self-tests into `tests/test_downgrade.py` and remove the brittle assertion against the live disk cache.
  - Deduplicate log-tailing and cache I/O, and remove dead code (unreachable outbound WebSocket 16/64-bit length branches in `cdp_call`, unused `"build_id": None` fields on cached manifests).
  - Remove obsolete prototype artifacts (`build.py`, `rss_test.py`, `.depotdownloader/`, `downloads/`).
  - Add `.gitignore` for Python bytecode, `.cache/`, and temporary download directories.
- **Non-Goals:**
  - Changing the user-facing CLI behavior, prompts, or Steam downgrade workflow.
  - Adding third-party dependencies (remains 100% Python standard library).
- **Anti-Goals:**
  - Over-engineering with unnecessary classes, abstract interfaces, or deep package hierarchies (per Ponytail rules).

## Constraints
- Windows-only target (`winreg`, `os.startfile`, `taskkill`, `Steam.exe`).
- Zero external Python dependencies (stdlib only).
- [steam-downgrade.bat](file:///d:/Paulo/Projects/Steam/steam-downgrade.bat) must continue to launch the tool seamlessly.

## Approaches Considered
1. **Single-Script Repo:** Keep one `steam_downgrade.py` script in root, move cache to `.cache/` and tests to `test_downgrade.py`. Minimal file count, but keeps ~500 lines of mixed concerns (SteamDB scraping, CDP WebSocket client, `.acf` parsing, log tailing) in one file.
2. **Modular Layout (`src/` + `tests/`) — Selected:** Split by responsibility into `main.py`, `src/steam_local.py`, `src/steamdb.py`, `src/downloader.py`, and `tests/test_downgrade.py`, with runtime state in `.cache/`. Chosen to give clean file management and separation of concerns for ongoing development.
3. **Archive Prototypes:** Same as above, but keep `build.py` and `rss_test.py` in an `archive/` folder. Rejected in favor of a clean repository.

## Decided Layout & Responsibilities

```text
Steam/
├── steam-downgrade.bat          # Runs main.py
├── main.py                      # Interactive CLI prompts & step orchestration
├── .gitignore                   # Ignores __pycache__/, .cache/, downloads/, .depotdownloader/
├── .cache/
│   └── steamdb_cache.json       # Cached depot manifest histories
├── src/
│   ├── steam_local.py           # find_steam, parse_acf_depots, list_installed_games, copy_tree_with_progress, freeze_acf
│   ├── steamdb.py               # http_get, parse_patchnotes_rss, fetch_app_depots, cdp_fetch_depot_manifests, resolve_build_depots, cache I/O
│   └── downloader.py            # download_depots (Steam.exe +download_depot loop + unified log tailer)
└── tests/
    └── test_downgrade.py        # Self-contained unit tests (no dependency on live .cache/steamdb_cache.json)
```

### Files to Delete (After Migration & Verification)
- [build.py](file:///d:/Paulo/Projects/Steam/build.py) — superseded `steam.client` prototype
- [rss_test.py](file:///d:/Paulo/Projects/Steam/rss_test.py) — superseded `requests` prototype
- [builds_rss.py](file:///d:/Paulo/Projects/Steam/builds_rss.py) — replaced by `main.py` + `src/*`
- `.depotdownloader/` — unused 78 MB `DepotDownloader.exe` binary
- `downloads/` — leftover test download folder (`582160_build_8082448`)

## What's Left to the Builder
- Exact function signatures between `main.py` and `src/*` modules.
- Internal helper naming for the unified log-tailer (`tail_log`) and JSON cache loader/saver.
