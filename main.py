import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

from src.downloader import download_depots
from src.steam_local import (
    copy_tree_with_progress,
    find_steam,
    freeze_app_manifest,
    list_installed_games,
)
from src.steamdb import (
    cdp_fetch_depot_manifests,
    fetch_app_info,
    http_get,
    parse_patchnotes_rss,
    resolve_build_depots,
)

ROOT = pathlib.Path(__file__).resolve().parent
CACHE_FILE = ROOT / ".cache" / "steamdb_cache.json"


def ask(prompt: str) -> str:
    """Prompt the user for input; exit cleanly on 'q', 'quit', or 'exit'."""
    try:
        val = input(prompt).strip()
    except (KeyboardInterrupt, EOFError):
        print("\nExiting.")
        sys.exit(0)
    if val.lower() in ("q", "quit", "exit"):
        print("\nExiting.")
        sys.exit(0)
    return val


def select_game(games: list[dict]) -> dict:
    """Prompt user to choose an installed game or type a Steam App ID."""
    if games:
        print("Installed Steam games:")
        for i, g in enumerate(games):
            print(f"{i:>3}) {g['name']}  [{g['app_id']}]")

    while True:
        raw = ask("\nEnter Steam App ID (e.g. 582160) or game # from list (or 'q' to exit): ")
        if raw.isdigit():
            val = int(raw)
            if games and val < len(games):
                return games[val]
            match = next((g for g in games if g["app_id"] == val), None)
            if match:
                return match
            return {
                "app_id": val,
                "name": f"App {val}",
                "dir": None,
                "acf": None,
                "depots": [],
                "installed": False,
            }
        print("Invalid input. Please enter a valid number or 'q' to exit.")


def select_build(builds: list[dict]) -> dict:
    """Display builds list and prompt user to select one."""
    print(f"\nItems in feed: {len(builds)}\n")
    print(f"{'#':>3}  {'Date':<18}{'Day':<6}{'Time':<8}{'Patch Title':<60}{'BuildID'}")
    for i, b in enumerate(builds):
        dt = b["dt"]
        date_str = f"{dt.day} {dt.strftime('%B %Y')}"
        print(f"{i:>3}) {date_str:<18}{dt.strftime('%a'):<6}{dt.strftime('%H:%M'):<8}{b['title'][:58]:<60}{b['build_id']}")

    while True:
        b_pick = ask(f"\nChoose a build by # (0-{len(builds) - 1}) or BuildID (or 'q' to exit): ")
        if b_pick.isdigit() and int(b_pick) < len(builds):
            return builds[int(b_pick)]
        match = next((b for b in builds if b["build_id"] == b_pick), None)
        if match:
            return match
        print(f"Invalid selection: '{b_pick}'. Please choose from 0 to {len(builds) - 1} or enter a valid BuildID.")


def display_plan_table(chosen: dict, game: dict, plan: list[dict], depots_obj: dict) -> None:
    """Format and print the depot & manifest changes table."""
    print(f"\n{'='*115}")
    print(f" Build {chosen['build_id']} ({chosen['dt'].strftime('%Y-%m-%d %H:%M')} UTC) - Depot & Manifest Changes:")
    print(f"{'='*115}")
    print(f"{'Depot':<9} {'Type':<18} {'Current Manifest':<22}    {'Target Manifest':<22} {'Date (UTC)':<18} {'Change'}")
    print(f"{'-'*115}")

    for p in plan:
        dep_id = p["id"]
        v = depots_obj.get(dep_id, {}) if isinstance(depots_obj, dict) else {}
        dlc = v.get("dlcappid")
        type_str = v.get("name") or (f"DLC {dlc}" if dlc else ("Main Content" if dep_id == game["depots"][0]["id"] else "Depot"))
        if len(type_str) > 17:
            type_str = type_str[:16] + "…"

        curr_str = p["current"] or "(none)"
        target_str = p["target"] or "(none)"
        dt_str = p["dt"].strftime("%Y-%m-%d %H:%M") if p.get("dt") else "current"

        if not p["target"]:
            status = "SKIP"
        elif not game["installed"] or p["target"] != p["current"]:
            status = "CHANGED"
        else:
            status = "UNCHANGED"

        arrow = "->" if status == "CHANGED" else "=="
        print(f"{dep_id:<9} {type_str:<18} {curr_str:<22} {arrow} {target_str:<22} {dt_str:<18} [{status}]")
    print(f"{'='*115}")


def main():
    steam, libs = find_steam()
    games = list_installed_games(libs)
    game = select_game(games)
    app_id = game["app_id"]

    # Fetch Builds list via SteamDB PatchnotesRSS
    url = f"https://steamdb.info/api/PatchnotesRSS/?appid={app_id}"
    try:
        builds = parse_patchnotes_rss(http_get(url))
    except Exception as e:
        sys.exit(f"Failed to fetch PatchnotesRSS for App {app_id}: {e}")

    chosen = select_build(builds)

    # Fetch app info & depot structures
    manifests_by_depot = {}
    depots_obj = {}
    try:
        app_info = fetch_app_info(app_id)
        game["name"] = app_info["name"]
        depots_obj = app_info["depots_obj"]

        if game["depots"]:
            # Filter out shared redists/launchers
            game["depots"] = [
                d for d in game["depots"]
                if not isinstance(depots_obj.get(d["id"]), dict)
                or not depots_obj[d["id"]].get("depotfromapp")
            ]
        else:
            game["depots"] = app_info["base_depots"]

        for d in game["depots"]:
            manifests_by_depot[d["id"]] = []

        if app_info["pub_dt"] and app_info["pub_build_id"]:
            for d in game["depots"]:
                gid = depots_obj.get(d["id"], {}).get("manifests", {}).get("public", {}).get("gid")
                if gid:
                    manifests_by_depot[d["id"]].append({
                        "manifest": str(gid),
                        "dt": app_info["pub_dt"],
                        "build_id": app_info["pub_build_id"],
                    })
    except Exception:
        pass

    if not game["depots"]:
        sys.exit(f"Could not determine depots for App {app_id}.")

    pub_build_id = next(
        (m["build_id"] for ms in manifests_by_depot.values() for m in ms if m.get("build_id")),
        None,
    )
    if chosen["build_id"] != pub_build_id:
        depot_ids = [d["id"] for d in game["depots"]]
        fetched = cdp_fetch_depot_manifests(depot_ids, CACHE_FILE)
        for d_id, rows in fetched.items():
            manifests_by_depot.setdefault(d_id, []).extend(rows)

    plan = resolve_build_depots(chosen, game["depots"], manifests_by_depot)
    for p in plan:
        if not p["target"]:
            os.startfile(f"https://steamdb.info/depot/{p['id']}/manifests/")
            m = re.search(r"\d{15,20}", ask(f"Paste manifest ID for depot {p['id']} (Enter = skip, or 'q' to exit): "))
            p["target"] = m.group(0) if m else None

    display_plan_table(chosen, game, plan, depots_obj)

    todo = [p for p in plan if p["target"] and (not game["installed"] or p["target"] != p["current"])]
    unchanged = [p for p in plan if p["target"] and game["installed"] and p["target"] == p["current"]]

    if todo:
        print(f"\n{len(todo)} depot(s) need updating for Build {chosen['build_id']}:")
        for idx, p in enumerate(todo, 1):
            print(f"  {idx}) Steam.exe +download_depot {app_id} {p['id']} {p['target']}")
    if unchanged:
        print(f"{len(unchanged)} depot(s) already match this build and will not be re-downloaded.")

    override = ask("\nPress Enter to start downloading, 'edit' to override, or 'q' to exit: ").lower()
    if override == "edit":
        for p in plan:
            val = ask(f"  Manifest for depot {p['id']} [{p['target']}] (Enter to keep, or 'q' to exit): ")
            if val.isdigit():
                p["target"] = val
        todo = [p for p in plan if p["target"] and (not game["installed"] or p["target"] != p["current"])]

    if not todo:
        print("Nothing to download (all depots already match that build).")
        return

    if not steam:
        steam = pathlib.Path(r"C:\Program Files\Steam")

    content_app_dir = download_depots(steam, libs, app_id, todo, prompt_retry=ask)

    if not game["installed"]:
        print(f"\nDone! Downloaded depots are in:\n  {content_app_dir}")
        os.startfile(str(content_app_dir))
        return

    if ask(f"\nApply all {len(todo)} depot(s) over installed game ({game['dir']}) and freeze updates? (y/n, or 'q' to exit): ").lower() != "y":
        os.startfile(str(content_app_dir))
        return

    # Close Steam, copy each downloaded depot over the install directory, and freeze appmanifest
    subprocess.call([str(steam / "steam.exe"), "-shutdown"])
    time.sleep(3)
    for idx, p in enumerate(todo, 1):
        depot_src = content_app_dir / f"depot_{p['id']}"
        copy_tree_with_progress(depot_src, game["dir"], label=f"depot {p['id']} [{idx}/{len(todo)}]")

    freeze_app_manifest(game["acf"])
    shutil.rmtree(content_app_dir, ignore_errors=True)
    print(f"\nDone! {game['name']} is now on Build {chosen['build_id']} and frozen.")


if __name__ == "__main__":
    main()
