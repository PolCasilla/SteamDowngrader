# SteamDowngrader

[![GitHub Release](https://img.shields.io/github/v/release/PolCasilla/SteamDowngrader?style=flat-square&color=blue)](https://github.com/PolCasilla/SteamDowngrader/releases)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square&logo=python)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows-0078D6?style=flat-square&logo=windows)](https://microsoft.com)
[![Dependencies](https://img.shields.io/badge/dependencies-zero%20(stdlib%20only)-success?style=flat-square)](https://github.com/PolCasilla/SteamDowngrader)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)

An automated, lightweight CLI tool for Windows to downgrade any Steam game to any historical version or build, and freeze updates to keep your mods and saves intact.

Built entirely with the **Python standard library** — **zero `pip install`** or third-party packages required.

---

## ⚡ Highlights

- **Zero External Dependencies**: Pure Python standard library (`urllib`, `xml`, `winreg`, `socket`, etc.). No virtual environment or extra installs needed.
- **Automatic Library Detection**: Reads your Windows Registry and `libraryfolders.vdf` to discover your Steam install directory and all library drives across disks.
- **Interactive Patch History**: Queries SteamDB's Patchnotes RSS feed to present builds with human-readable update titles, dates (UTC), and Build IDs.
- **Automated Manifest Resolution**: Fetches depot metadata via SteamCMD API and scrapes SteamDB manifest tables using a local Chrome/Edge DevTools Protocol (CDP) WebSocket bridge to smoothly bypass Cloudflare checks.
- **Smart Depot Diffs**: Compares your currently installed manifests against the target build, skipping unchanged depots to save bandwidth and disk space.
- **Native Steam Client Downloads**: Dispatches downloads directly through your logged-in `Steam.exe` client (`+download_depot`), tracking log output and disk write progress in real time.
- **One-Click Apply & Update Freeze**: Closes Steam, transfers downloaded depot files directly into the game directory with a visual progress bar, and marks `appmanifest_<appid>.acf` as read-only (`AutoUpdateBehavior = 1`) to block Steam from silently overwriting your game version.

---

## 📋 Prerequisites

1. **Windows 10 or 11**
2. **Python 3.10+** (Ensure Python is added to your `PATH`)
3. **Steam Client** installed, running, and logged in (must own the target game on your account)
4. **Microsoft Edge or Google Chrome** (pre-installed on Windows; used headlessly via CDP to query SteamDB)

---

## 🚀 Quick Start

### Option A: Download Release (Recommended)

1. Go to the [**Releases**](https://github.com/PolCasilla/SteamDowngrader/releases) page and download `SteamDowngrader.zip`.
2. Extract the archive anywhere on your PC.
3. Double-click `steam-downgrade.bat`.

### Option B: Clone from Source

```powershell
git clone https://github.com/PolCasilla/SteamDowngrader.git
cd SteamDowngrader
python main.py
```

*(Or double-click `steam-downgrade.bat`)*

---

## 🎮 How It Works

```
[1. Select Game] ──> [2. Pick Build] ──> [3. Review Depot Diff] ──> [4. Auto-Download] ──> [5. Apply & Freeze]
```

1. **Select Game**: Choose from a detected list of installed games or enter any arbitrary Steam App ID (e.g. `582160` for *Monster Hunter: World*).
2. **Select Build**: Browse the historical list of game updates complete with release date, time, and patch note title:
   ```text
     #  Date              Day   Time    Patch Title                                                 BuildID
     0) 14 October 2026   Wed   08:00   Major Update 1.5 - Stability & Bugfixes                     12345678
     1) 22 September 2026 Tue   14:30   Hotfix 1.4.2                                                12233445
   ```
3. **Review Changes**: SteamDowngrader compares the target manifests with your local files:
   ```text
   ===================================================================================================================
    Build 12233445 (2026-09-22 14:30 UTC) - Depot & Manifest Changes:
   ===================================================================================================================
   Depot     Type               Current Manifest          Target Manifest        Date (UTC)         Change
   -------------------------------------------------------------------------------------------------------------------
   582161    Main Content       9018237498127391823    -> 8192739182739182731    2026-09-22 14:28   [CHANGED]
   582162    Depot              4728192837192837192    == 4728192837192837192    2026-09-10 11:00   [UNCHANGED]
   ===================================================================================================================
   ```
4. **Auto-Download**: Confirms depot download commands via `Steam.exe +download_depot`. Live progress is streamed directly from Steam's content logs and disk writes.
5. **Apply & Freeze**: Safely shuts down Steam, copies files to the game directory, and protects the `.acf` manifest.

---

## 🔒 How Update Freezing Works

Steam automatically updates games whenever a new build is pushed to the public branch. To keep your downgraded build indefinitely:

1. **AutoUpdateBehavior**: Configured to `1` ("Only update this game when I launch it") inside `steamapps/appmanifest_<appid>.acf`.
2. **Write Lock**: SteamDowngrader applies the Windows `READ-ONLY` file attribute to `appmanifest_<appid>.acf`.
3. Steam cannot modify the manifest file upon launch or download queued updates, preventing silent overwrites.

### To Unfreeze / Update Normally Later:
If you ever want to update the game back to the latest version:
1. Navigate to your Steam library `steamapps/` folder.
2. Right-click `appmanifest_<appid>.acf` -> **Properties**.
3. Uncheck **Read-only** and click **OK**.
4. In Steam, right-click the game -> **Properties** -> **Installed Files** -> **Verify integrity of game files**.

---

## 📁 Project Structure

```text
SteamDowngrader/
├── .cache/                    # Cached SteamDB depot manifests (speeds up repeat runs)
├── src/
│   ├── downloader.py          # Steam client log-tailing and depot download manager
│   ├── steam_local.py         # Registry scanner, library finder, and manifest freeze logic
│   └── steamdb.py             # SteamDB RSS parser, CDP WebSocket scraper, and manifest cache
├── main.py                    # Interactive CLI workflow entrypoint
├── steam-downgrade.bat        # Double-click launcher script for Windows
└── README.md
```

---

## ❓ Troubleshooting & FAQ

<details>
<summary><b>SteamDB opened a browser window asking for Cloudflare verification?</b></summary>
When querying historical manifests for depots not yet cached, SteamDowngrader launches Edge/Chrome via CDP. If Cloudflare prompts a "Verify you are human" checkbox, simply click it in the browser window once. The tool will capture the manifests, save them to <code>.cache/steamdb_cache.json</code>, and automatically close the browser.
</details>

<details>
<summary><b>Does this require me to enter my Steam password?</b></summary>
<b>No.</b> SteamDowngrader never asks for your credentials. It utilizes your locally running Steam client session and the built-in <code>+download_depot</code> command.
</details>

<details>
<summary><b>Can I download games or DLC I do not own?</b></summary>
<b>No.</b> Steam's content servers verify your account's licenses. You must own the game on the currently logged-in Steam account to download its depots.
</details>

<details>
<summary><b>Depot download failed or got stuck?</b></summary>
SteamDowngrader automatically detects client interruptions and retries up to 5 times. Ensure Steam is running and logged in before starting the download.
</details>

---

## ⚖️ Disclaimer

SteamDowngrader is an open-source utility designed for speedrunners, modders, and preservationists who need access to historical game versions. It is **not** a piracy tool and does **not** bypass Steam DRM. All content is downloaded directly from Valve's official content servers through the user's authentic Steam client.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
