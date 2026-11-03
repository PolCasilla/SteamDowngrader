import os
import pathlib
import shutil
import subprocess
import sys
import time
from typing import Callable, Optional


def tail_file(
    path: pathlib.Path,
    last_pos: int,
    line_filter: Optional[Callable[[str], bool]] = None,
) -> tuple[int, list[str]]:
    """Tail a file from last_pos, handling truncation and line filtering."""
    if not path.exists():
        return 0, []
    try:
        cur_size = path.stat().st_size
        if cur_size < last_pos:
            last_pos = 0

        lines = []
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            f.seek(last_pos)
            for line in f:
                stripped = line.strip()
                if line_filter is None or line_filter(stripped):
                    lines.append(stripped)
            new_pos = f.tell()
        return new_pos, lines
    except OSError:
        return last_pos, []


def clean_content_app_dirs(steam: pathlib.Path, libs: list[pathlib.Path], app_id: int) -> None:
    """Remove any previously downloaded content folders for this App ID across all library folders."""
    all_bases = {steam}
    if libs:
        all_bases.update(libs)
    for base in all_bases:
        old_dir = base / "steamapps" / "content" / f"app_{app_id}"
        if old_dir.exists():
            print(f"\nRemoving existing downloaded files for App {app_id}: {old_dir} ...")
            shutil.rmtree(old_dir, ignore_errors=True)


def download_depots(
    steam: pathlib.Path,
    libs: list[pathlib.Path],
    app_id: int,
    todo_depots: list[dict],
    max_retries: int = 5,
    prompt_retry: Optional[Callable[[str], str]] = None,
) -> pathlib.Path:
    """Download specified depots using Steam.exe client console commands."""
    steam_exe = steam / "Steam.exe"
    console_log = steam / "logs" / "console_log.txt"
    content_log = steam / "logs" / "content_log.txt"
    content_app_dir = steam / "steamapps" / "content" / f"app_{app_id}"

    clean_content_app_dirs(steam, libs, app_id)

    print(f"\nAuto-downloading {len(todo_depots)} depot(s) via Steam client:")
    for idx, p in enumerate(todo_depots, 1):
        depot_id = p["id"]
        manifest_id = p["target"]
        attempt = 0
        done = False

        while not done:
            attempt += 1
            c_pos = console_log.stat().st_size if console_log.exists() else 0
            r_pos = content_log.stat().st_size if content_log.exists() else 0

            retry_tag = f" (retry {attempt - 1}/{max_retries})" if attempt > 1 else ""
            print(f"\n[{idx}/{len(todo_depots)}]{retry_tag} Running: Steam.exe +download_depot {app_id} {depot_id} {manifest_id}")
            subprocess.Popen([str(steam_exe), "+download_depot", str(app_id), str(depot_id), str(manifest_id)])

            failed_line = None
            t0 = time.time()
            while not done and not failed_line:
                time.sleep(2)

                r_pos, content_lines = tail_file(
                    content_log,
                    r_pos,
                    lambda l: "Current download rate:" in l or f"depot {depot_id}" in l or "update started" in l,
                )
                for line in content_lines:
                    print(f"\r{' '*80}\r  {line}")

                c_pos, console_lines = tail_file(
                    console_log,
                    c_pos,
                    lambda l: f"depot {depot_id}" in l or f"depot_{depot_id}" in l or "Depot download" in l,
                )
                for line in console_lines:
                    print(f"\r{' '*80}\r  {line}")
                    if "Depot download complete" in line and f"depot_{depot_id}" in line:
                        done = True
                    elif "Depot download failed" in line:
                        failed_line = line

                if not done and not failed_line:
                    depot_dir = content_app_dir / f"depot_{depot_id}"
                    mb = sum(f.stat().st_size for f in depot_dir.rglob("*") if f.is_file()) / 1048576 if depot_dir.exists() else 0.0
                    elapsed = int(time.time() - t0)
                    print(f"\r  [in progress] {mb:,.1f} MB written to disk | elapsed {elapsed // 60:02d}:{elapsed % 60:02d} ...", end="", flush=True)

            print()

            if failed_line:
                depot_dir = content_app_dir / f"depot_{depot_id}"
                if depot_dir.exists():
                    print(f"  Removing partial files in {depot_dir} ...")
                    shutil.rmtree(depot_dir, ignore_errors=True)
                if attempt <= max_retries:
                    print(f"  Download interrupted ({failed_line}). Retrying in 5s...")
                    time.sleep(5)
                else:
                    ans = "y"
                    if prompt_retry:
                        ans = prompt_retry(f"\nFailed after {max_retries} retries. Try {max_retries} more times? (y/n, Enter=y, or 'q' to exit): ").lower()
                    if ans != "n":
                        attempt = 1
                    else:
                        sys.exit(f"Stopped after failure: {failed_line}")

    return content_app_dir
