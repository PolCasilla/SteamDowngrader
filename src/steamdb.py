import base64
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import json
import os
import pathlib
import re
import socket
import struct
import subprocess
import time
import urllib.request
import xml.etree.ElementTree as ET

UA = "builds-list-test/0.1"


def http_get(url: str, timeout: int = 15) -> bytes:
    """Perform a simple HTTP GET with a custom User-Agent."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def parse_patchnotes_rss(xml_bytes: bytes) -> list[dict]:
    """Parse SteamDB PatchnotesRSS feed XML into structured build records."""
    root = ET.fromstring(xml_bytes)
    builds = []
    for item in root.findall("./channel/item"):
        build_id = (item.findtext("guid") or "").replace("build#", "").strip()
        dt = parsedate_to_datetime(item.findtext("pubDate")).astimezone(timezone.utc)
        desc = item.findtext("description") or ""
        title = re.sub(r"\s*\(?SteamDB Build \d+\)?\s*$", "", desc).strip() or "No title"
        builds.append({"build_id": build_id, "dt": dt, "title": title})
    return builds


def parse_steamdb_manifest_date(text: str) -> datetime:
    """Parse date strings from SteamDB manifest table rows into UTC datetime."""
    clean = re.sub(r"\s*UTC.*$", "", text)
    clean = re.sub(r"[^\w\s:]", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return datetime.strptime(clean, "%d %B %Y %H:%M:%S").replace(tzinfo=timezone.utc)


def _read_cache_raw(cache_file: pathlib.Path) -> dict:
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def load_cache(cache_file: pathlib.Path) -> dict:
    """Load cached depot manifests from JSON file into parsed datetimes."""
    raw = _read_cache_raw(cache_file)
    out = {}
    for k, rows in raw.items():
        parsed_rows = []
        for r in rows:
            try:
                parsed_rows.append({
                    "manifest": r["manifest"],
                    "dt": parse_steamdb_manifest_date(r["date"]),
                    "build_id": r.get("build_id"),
                })
            except Exception:
                continue
        out[k] = parsed_rows
    return out


def save_to_cache(cache_file: pathlib.Path, depot_id: str, rows_raw: list) -> None:
    """Append or update a depot's raw manifest rows in the cache JSON file."""
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    data = _read_cache_raw(cache_file)
    data[depot_id] = rows_raw
    cache_file.write_text(json.dumps(data, indent=2), encoding="utf-8")


def fetch_app_info(app_id: int) -> dict:
    """Fetch app metadata and depot list from api.steamcmd.net."""
    url = f"https://api.steamcmd.net/v1/info/{app_id}"
    resp = json.loads(http_get(url, timeout=10))
    app_data = resp.get("data", {}).get(str(app_id), {})
    name = app_data.get("common", {}).get("name", f"App {app_id}")
    depots_obj = app_data.get("depots", {})

    base_depots = []
    for k, v in depots_obj.items():
        if not k.isdigit() or not isinstance(v, dict) or v.get("depotfromapp"):
            continue
        gid = v.get("manifests", {}).get("public", {}).get("gid")
        if not gid:
            continue
        cfg = v.get("config", {})
        if (cfg.get("oslist") and "windows" not in cfg["oslist"]) or (cfg.get("osarch") and cfg["osarch"] != "64"):
            continue
        if cfg.get("language") and cfg["language"] != "english":
            continue
        base_depots.append({"id": k, "manifest": str(gid)})

    pub_branch = depots_obj.get("branches", {}).get("public", {})
    pub_build_id = str(pub_branch.get("buildid", "")) if isinstance(pub_branch, dict) else ""
    pub_dt = (
        datetime.fromtimestamp(int(pub_branch["timeupdated"]), tz=timezone.utc)
        if isinstance(pub_branch, dict) and pub_branch.get("timeupdated")
        else None
    )

    return {
        "name": name,
        "depots_obj": depots_obj,
        "base_depots": base_depots,
        "pub_build_id": pub_build_id,
        "pub_dt": pub_dt,
    }


def resolve_build_depots(build: dict, depots: list, manifests_by_depot: dict) -> list[dict]:
    """Map depots to target manifests for a specific build using build_id or cutoff date."""
    cutoff = build["dt"] + timedelta(minutes=10)
    plan = []
    for d in depots:
        hist = sorted(manifests_by_depot.get(d["id"], []), key=lambda x: x["dt"], reverse=True)
        hit = next((m for m in hist if m.get("build_id") and m.get("build_id") == build["build_id"]), None)
        if not hit:
            hit = next((m for m in hist if m["dt"] <= cutoff), None)
        if not hit and len(hist) == 1:
            hit = hist[0]
        plan.append({
            "id": d["id"],
            "current": d.get("manifest"),
            "target": hit["manifest"] if hit else None,
            "dt": hit["dt"] if hit else None,
        })
    return plan


def cdp_fetch_depot_manifests(depot_ids: list, cache_file: pathlib.Path) -> dict:
    """Use local Chrome/Edge via Chrome DevTools Protocol to fetch SteamDB depot manifest histories."""
    cached = load_cache(cache_file)
    out = {d: cached.get(d, []) for d in depot_ids}
    to_fetch = [d for d in depot_ids if not out[d]]
    if not to_fetch:
        return out

    browsers = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    ]
    exe = next((b for b in browsers if os.path.exists(b)), None)
    if not exe:
        return out

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    prof = os.path.join(os.environ.get("LOCALAPPDATA", "."), "steam-downgrader-cdp")
    proc = subprocess.Popen([
        exe, f"--user-data-dir={prof}", f"--remote-debugging-port={port}",
        "--no-first-run", "--no-default-browser-check", "--window-size=900,680", "about:blank",
    ])
    try:
        tabs = None
        for _ in range(40):
            time.sleep(0.3)
            try:
                tabs = json.loads(http_get(f"http://127.0.0.1:{port}/json", timeout=1))
                if tabs and any(t.get("type") == "page" for t in tabs):
                    break
            except Exception:
                pass
        if not tabs:
            return out

        ws_url = next(t["webSocketDebuggerUrl"] for t in tabs if t.get("type") == "page")
        path = "/" + ws_url.split("/", 3)[3]
        sock = socket.create_connection(("127.0.0.1", port), timeout=15)
        key = base64.b64encode(os.urandom(16)).decode()
        sock.sendall(
            f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
            f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n".encode()
        )
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += sock.recv(4096)

        msg_id = 0

        def recv_exact(n: int) -> bytes:
            data = bytearray()
            while len(data) < n:
                chunk = sock.recv(n - len(data))
                if not chunk:
                    raise EOFError("WebSocket closed")
                data.extend(chunk)
            return bytes(data)

        def cdp_call(method: str, params: dict):
            nonlocal msg_id
            msg_id += 1
            payload = json.dumps({"id": msg_id, "method": method, "params": params}).encode()
            mask = os.urandom(4)
            n = len(payload)
            if n < 126:
                header = bytearray([0x81, 0x80 | n])
            else:
                header = bytearray([0x81, 0x80 | 126]) + struct.pack("!H", n)
            masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            sock.sendall(header + mask + masked)

            while True:
                b0, b1 = recv_exact(2)
                length = b1 & 0x7F
                if length == 126:
                    length = struct.unpack("!H", recv_exact(2))[0]
                elif length == 127:
                    length = struct.unpack("!Q", recv_exact(8))[0]
                data = recv_exact(length)
                if (b0 & 0x0F) == 1:
                    msg = json.loads(data.decode("utf-8", errors="ignore"))
                    if msg.get("id") == msg_id:
                        return msg

        for d in to_fetch:
            print(f"  Reading SteamDB manifests for depot {d}...")
            cdp_call("Page.navigate", {"url": f"https://steamdb.info/depot/{d}/manifests/"})
            js = f"""(() => {{
              if (!location.pathname.includes('/depot/{d}/')) return '';
              const rows = [...document.querySelectorAll('#manifests tr, table tr')]
                .map(tr => [...tr.querySelectorAll('td')].map(td => td.innerText.trim()));
              const valid = rows.filter(r => r.some(c => /^\\d{{15,20}}$/.test(c)));
              return valid.length ? JSON.stringify(valid) : '';
            }})()"""
            for i in range(90):
                time.sleep(0.6)
                res = cdp_call("Runtime.evaluate", {"expression": js, "returnByValue": True})
                val = res.get("result", {}).get("result", {}).get("value")
                if val:
                    raw_cache = []
                    for row in json.loads(val):
                        mid = next((c for c in row if re.match(r"^\d{15,20}$", c)), None)
                        if mid:
                            out[d].append({
                                "manifest": mid,
                                "dt": parse_steamdb_manifest_date(row[0]),
                                "build_id": None,
                            })
                            raw_cache.append({"date": row[0], "manifest": mid})
                    if raw_cache:
                        save_to_cache(cache_file, d, raw_cache)
                    break
                if i == 10:
                    print("  (If the browser shows a Cloudflare check, click it once in the browser window...)")
        sock.close()
    finally:
        subprocess.call(["taskkill", "/F", "/T", "/PID", str(proc.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out
