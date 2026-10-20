"""Playwright browser path + process hygiene for Apply.

Cursor/sandbox shells often set PLAYWRIGHT_BROWSERS_PATH to a cache that is
missing the Chromium build Playwright expects. We point at a real install and
kill leftover Apply Chromium processes so each Apply starts a fresh browser.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .config import DATA_DIR

APPLY_USER_DATA = DATA_DIR / "browser"


def _chrome_exe_under(root: Path) -> Path | None:
    if not root.is_dir():
        return None
    # Prefer newest chromium-* folder that contains chrome.exe
    candidates: list[Path] = []
    try:
        for d in root.glob("chromium-*"):
            for name in ("chrome-win64/chrome.exe", "chrome-win/chrome.exe"):
                exe = d / name.replace("/", os.sep)
                if exe.is_file():
                    candidates.append(exe)
    except OSError:
        return None
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0]


def ensure_playwright_browsers_path() -> str | None:
    """Fix PLAYWRIGHT_BROWSERS_PATH; return the path used (or None = Playwright default)."""
    local = Path(os.environ.get("LOCALAPPDATA") or "") / "ms-playwright"
    home = Path.home() / "AppData" / "Local" / "ms-playwright"
    preferred_roots = [local, home]

    current = (os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or "").strip()
    current_path = Path(current) if current else None
    current_ok = bool(current_path and _chrome_exe_under(current_path))
    sandboxish = "cursor-sandbox-cache" in current.lower() or "sandbox-cache" in current.lower()

    if current_ok and not sandboxish:
        return current

    for root in preferred_roots:
        if _chrome_exe_under(root):
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(root)
            print(f"[browser] PLAYWRIGHT_BROWSERS_PATH -> {root}")
            return str(root)

    # Drop broken sandbox override so Playwright uses its default lookup.
    if current and (sandboxish or not current_ok):
        os.environ.pop("PLAYWRIGHT_BROWSERS_PATH", None)
        print(f"[browser] cleared broken PLAYWRIGHT_BROWSERS_PATH ({current})")
    return os.environ.get("PLAYWRIGHT_BROWSERS_PATH")


def install_chromium_if_needed() -> None:
    """Best-effort `playwright install chromium` when no chrome.exe is found."""
    ensure_playwright_browsers_path()
    root = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or (Path(os.environ.get("LOCALAPPDATA") or "") / "ms-playwright"))
    if _chrome_exe_under(root) or _chrome_exe_under(Path(os.environ.get("LOCALAPPDATA") or "") / "ms-playwright"):
        return
    print("[browser] Chromium missing — running playwright install chromium…")
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=False,
            timeout=600,
        )
    except Exception as e:
        print(f"[browser] playwright install failed: {e}")
    ensure_playwright_browsers_path()


def clear_profile_locks(user_data: Path | None = None) -> None:
    """Public alias — clear Chromium singleton locks for the Apply profile."""
    _clear_profile_locks(user_data or APPLY_USER_DATA)


def _clear_profile_locks(user_data: Path) -> None:
    for name in (
        "SingletonLock",
        "SingletonCookie",
        "SingletonSocket",
        "lockfile",
        "RunningChromeVersion",
    ):
        try:
            (user_data / name).unlink(missing_ok=True)
        except OSError:
            pass


def kill_stale_apply_browsers() -> None:
    """Kill Chromium still holding the Apply user-data dir so the next launch is clean."""
    marker = str(APPLY_USER_DATA.resolve())
    killed = 0
    if sys.platform == "win32":
        try:
            # Emit PIDs whose command line references our Apply profile dir.
            ps = r"""
$ErrorActionPreference='SilentlyContinue'
Get-CimInstance Win32_Process |
  Where-Object { $_.Name -match '^(chrome|chromium)\.exe$' -and $_.CommandLine } |
  ForEach-Object {
    $cl = $_.CommandLine.ToLower()
    if ($cl -match 'applyforme[\\/]+data[\\/]+browser') { $_.ProcessId }
  }
"""
            ps_exe = os.path.join(
                os.environ.get("SystemRoot", r"C:\Windows"),
                "System32",
                "WindowsPowerShell",
                "v1.0",
                "powershell.exe",
            )
            if not os.path.isfile(ps_exe):
                ps_exe = "powershell.exe"
            out = subprocess.run(
                [ps_exe, "-NoProfile", "-Command", ps],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            for line in (out.stdout or "").splitlines():
                line = line.strip()
                if line.isdigit():
                    try:
                        subprocess.run(
                            ["taskkill", "/F", "/PID", line, "/T"],
                            check=False,
                            capture_output=True,
                            timeout=10,
                        )
                        killed += 1
                    except Exception:
                        pass
        except Exception as e:
            print(f"[browser] stale kill skipped: {e}")
    else:
        try:
            r = subprocess.run(["pkill", "-f", marker], check=False, timeout=10)
            if r.returncode == 0:
                killed = 1
        except Exception:
            pass

    _clear_profile_locks(APPLY_USER_DATA)
    print(f"[browser] restart Apply browser (killed={killed}, locks cleared)")


def prepare_local_browser(*, kill_stale: bool = False) -> Path:
    """Call before a local Playwright Apply launch.

    ``kill_stale`` is opt-in.  The old code killed every Apply Chromium on
    every launch, which made two independent applications (or a dashboard
    submit racing a prepare) kill each other's browser.  A stale process is now
    only cleared after a launch failure, while holding the browser lock.
    """
    ensure_playwright_browsers_path()
    install_chromium_if_needed()
    APPLY_USER_DATA.mkdir(parents=True, exist_ok=True)
    if kill_stale:
        kill_stale_apply_browsers()
    return APPLY_USER_DATA


BROWSER_LOCK = DATA_DIR / "apply-browser.lock"


def acquire_browser_lock(*, timeout_sec: float = 60.0, stale_sec: float = 900.0) -> Path | None:
    """Cross-process lock so only one Apply controls the shared Chromium profile."""
    import time as _time

    deadline = _time.time() + max(1.0, timeout_sec)
    while _time.time() < deadline:
        try:
            fd = os.open(str(BROWSER_LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(f"{os.getpid()}\n{_time.time()}\n")
            return BROWSER_LOCK
        except FileExistsError:
            try:
                age = _time.time() - BROWSER_LOCK.stat().st_mtime
                raw = BROWSER_LOCK.read_text(encoding="utf-8", errors="replace").splitlines()
                pid = int(raw[0]) if raw and raw[0].strip().isdigit() else 0
                alive = False
                if pid:
                    try:
                        os.kill(pid, 0)  # type: ignore[arg-type]
                        alive = True
                    except Exception:
                        alive = False
                if age > stale_sec or not alive:
                    BROWSER_LOCK.unlink(missing_ok=True)
                    continue
            except Exception:
                pass
            _time.sleep(0.5)
    return None


def release_browser_lock(lock: Path | None) -> None:
    if lock is None:
        return
    try:
        lock.unlink(missing_ok=True)
    except OSError:
        pass

