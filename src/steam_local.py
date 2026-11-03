import os
import pathlib
import re
import shutil
import stat
import time
import winreg


def find_steam() -> tuple[pathlib.Path | None, list[pathlib.Path]]:
    """Locate Steam installation path and library folders from Windows registry."""
    steam = None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            steam = pathlib.Path(winreg.QueryValueEx(k, "SteamPath")[0])
    except Exception:
        for p in (r"C:\Program Files\Steam", r"C:\Program Files (x86)\Steam"):
            if os.path.exists(p):
                steam = pathlib.Path(p)
                break
    if not steam:
        return None, []

    try:
        vdf = (steam / "steamapps" / "libraryfolders.vdf").read_text(encoding="utf-8", errors="ignore")
        libs = [pathlib.Path(p.replace(r"\\", "\\")) for p in re.findall(r'"path"\s+"(.+?)"', vdf)]
        return steam, libs if libs else [steam]
    except Exception:
        return steam, [steam]


def parse_acf_depots(acf_text: str) -> list[dict[str, str]]:
    """Return all installed depots from an appmanifest_*.acf file."""
    m = re.search(r'"InstalledDepots"\s*\{', acf_text)
    if not m:
        return []
    start = m.end() - 1
    depth = 0
    end = start
    for i in range(start, len(acf_text)):
        if acf_text[i] == "{":
            depth += 1
        elif acf_text[i] == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    block = acf_text[start:end]
    depots = []
    for d_id, body in re.findall(r'"(\d+)"\s*\{([^}]*)\}', block):
        m_man = re.search(r'"manifest"\s+"(\d+)"', body)
        if m_man:
            depots.append({"id": d_id, "manifest": m_man.group(1)})
    return sorted(depots, key=lambda x: int(x["id"]))


def list_installed_games(libs: list[pathlib.Path]) -> list[dict]:
    """Scan all steam library folders for installed games."""
    games = []
    for lib in libs:
        steamapps = lib / "steamapps"
        if not steamapps.exists():
            continue
        for acf in steamapps.glob("appmanifest_*.acf"):
            try:
                t = acf.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            m_app = re.search(r'"appid"\s+"(\d+)"', t)
            m_name = re.search(r'"name"\s+"(.+?)"', t)
            m_dir = re.search(r'"installdir"\s+"(.+?)"', t)
            depots = parse_acf_depots(t)
            if m_app and int(m_app.group(1)) != 228980 and depots:  # 228980 = Steamworks Common Redist
                games.append({
                    "app_id": int(m_app.group(1)),
                    "name": m_name.group(1) if m_name else m_app.group(1),
                    "dir": lib / "steamapps" / "common" / (m_dir.group(1) if m_dir else ""),
                    "acf": acf,
                    "depots": depots,
                    "installed": True,
                })
    return sorted(games, key=lambda g: g["name"].lower())


def copy_tree_with_progress(src_dir: pathlib.Path, dst_dir: pathlib.Path, label: str = "") -> None:
    """Copy all files from src_dir to dst_dir with a live progress bar."""
    if not src_dir.exists():
        return
    files = [f for f in src_dir.rglob("*") if f.is_file()]
    if not files:
        return
    total_bytes = sum(f.stat().st_size for f in files)
    copied_bytes = 0
    t0 = time.time()
    last_print = 0.0

    print(f"\nCopying {label or src_dir.name} ({len(files)} files, {total_bytes / 1048576:,.1f} MB)...")

    for src in files:
        rel = src.relative_to(src_dir)
        dst = dst_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        size = src.stat().st_size

        if size == 0:
            dst.touch(exist_ok=True)
            continue

        with open(src, "rb") as f_in, open(dst, "wb") as f_out:
            while True:
                buf = f_in.read(8 * 1024 * 1024)
                if not buf:
                    break
                f_out.write(buf)
                copied_bytes += len(buf)
                now = time.time()
                if now - last_print >= 0.2:
                    pct = (copied_bytes / total_bytes * 100) if total_bytes else 100.0
                    mb_cur = copied_bytes / 1048576
                    mb_tot = total_bytes / 1048576
                    elapsed = max(now - t0, 0.001)
                    speed = mb_cur / elapsed
                    bar_len = 25
                    filled = int(bar_len * (pct / 100.0))
                    bar = "=" * filled + "-" * (bar_len - filled)
                    name = rel.name[:25]
                    print(f"\r{' '*80}\r  [{bar}] {pct:5.1f}% ({mb_cur:,.0f}/{mb_tot:,.0f} MB, {speed:,.1f} MB/s) {name:<25}", end="", flush=True)
                    last_print = now
        try:
            shutil.copystat(src, dst)
        except Exception:
            pass

    mb_tot = total_bytes / 1048576
    elapsed = max(time.time() - t0, 0.001)
    speed = mb_tot / elapsed
    bar = "=" * 25
    print(f"\r{' '*80}\r  [{bar}] 100.0% ({mb_tot:,.0f}/{mb_tot:,.0f} MB, {speed:,.1f} MB/s) Done!")


def freeze_app_manifest(acf_path: pathlib.Path) -> None:
    """Set AutoUpdateBehavior to 1 (Only update when launched) and make manifest read-only."""
    if not acf_path.exists():
        return
    os.chmod(acf_path, stat.S_IWRITE)
    txt = acf_path.read_text(encoding="utf-8", errors="ignore")
    if re.search(r'"AutoUpdateBehavior"\s+"\d+"', txt):
        txt = re.sub(r'"AutoUpdateBehavior"\s+"\d+"', '"AutoUpdateBehavior"\t\t"1"', txt)
    else:
        # If missing, insert into AppState
        txt = re.sub(r'("AppState"\s*\{)', r'\1\n\t"AutoUpdateBehavior"\t\t"1"', txt)
    acf_path.write_text(txt, encoding="utf-8")
    os.chmod(acf_path, stat.S_IREAD)
