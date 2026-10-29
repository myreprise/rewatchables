"""Open the Rewatchables site in its own window, starting its dev server first if it isn't up.

    pythonw scripts/launch_app.pyw          # what the Start Menu "Rewatchables Explorer" entry runs
    pythonw scripts/launch_app.pyw --stop   # what "Stop Rewatchables Explorer" runs

A .pyw runs under pythonw.exe, so no console window appears. The server is the
Observable Framework dev server for site/ (observable preview on 127.0.0.1:8577),
run straight from site/node_modules rather than through npm, so the process that
holds the port is the one --stop ends. It is started hidden and keeps running
after the window closes, so the next open is instant and pages always show the
current site/src; --stop ends it. Port 8577, not Framework's default 3000 or the
3200/3201 of .claude/launch.json, so it never collides with a dev preview.

The server gets a console of its own, hidden, rather than none: the data loader
(src/data/site.db.py) runs under python.exe, and a console program started by a
process with no console opens a window of its own.

"Is it ours" is decided by the listening process's command line, which has to
run Framework from this repo's site/. Anything else on the port is reported and
left alone. Server output goes to server.log under %LOCALAPPDATA%\\rewatchables,
outside OneDrive. Errors are shown in a message box: with no console, a printed
error would vanish. The Start Menu entries are made by install_shortcut.ps1,
next to this file.
"""

import argparse
import ctypes
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SITE = ROOT / "site"
FRAMEWORK = SITE / "node_modules" / "@observablehq" / "framework" / "dist" / "bin" / "observable.js"
PORT = 8577
URL = f"http://127.0.0.1:{PORT}"
TITLE = "Rewatchables Explorer"
MARKER = "Rewatchables Explorer"   # observablehq.config.js's title, in every page's <title>
LOG = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "rewatchables" / "server.log"
SERVE_TIMEOUT_S = 60

NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW
NEW_GROUP = 0x00000200  # CREATE_NEW_PROCESS_GROUP


def message(text: str, error: bool = False) -> None:
    ctypes.windll.user32.MessageBoxW(None, text, TITLE, 0x10 if error else 0x40)


def shown(path: Path) -> Path:
    """Where a file under %LOCALAPPDATA% really is. The Microsoft Store Python redirects
    AppData writes into its package folder, so the plain path doesn't exist in Explorer."""
    exe = Path(sys.executable)
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    if "WindowsApps" in exe.parts and local in path.parents:
        real = local / "Packages" / exe.parent.name / "LocalCache" / "Local" / path.relative_to(local)
        if real.exists():
            return real
    return path


def site_up(timeout: float = 2.0) -> bool:
    """True when :8577 answers with a page of this site, not merely when something is listening."""
    try:
        with urllib.request.urlopen(f"{URL}/", timeout=timeout) as r:
            return MARKER in r.read(4096).decode("utf-8", "replace")
    except Exception:
        return False


def listener_pid() -> int | None:
    """The process listening on 127.0.0.1:PORT, from netstat (no psutil needed)."""
    out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True,
                         creationflags=NO_WINDOW).stdout
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 5 and parts[1] in (f"127.0.0.1:{PORT}", f"0.0.0.0:{PORT}") \
                and parts[3] == "LISTENING":
            return int(parts[4])
    return None


def command_line(pid: int) -> str:
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CommandLine"],
        capture_output=True, text=True, creationflags=NO_WINDOW).stdout
    return out.strip()


def is_ours(pid: int) -> bool:
    return str(FRAMEWORK).lower() in command_line(pid).lower()


def node() -> str | None:
    if found := shutil.which("node"):
        return found
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if base and (p := Path(base) / "nodejs" / "node.exe").exists():
            return str(p)
    return None


def start_server(exe: str) -> subprocess.Popen:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    log = open(LOG, "a", encoding="utf-8")
    log.write(f"\n--- started {time.strftime('%Y-%m-%d %H:%M:%S')} by launch_app.pyw ---\n")
    log.flush()
    # The absolute observable.js path is what is_ours() looks for. An explicit
    # --port makes Framework fail if the port is taken instead of trying the next.
    args = [exe, str(FRAMEWORK), "preview", "--host", "127.0.0.1", "--port", str(PORT), "--no-open"]
    return subprocess.Popen(args, cwd=SITE, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                            env={**os.environ, "PYTHONUTF8": "1"},
                            creationflags=NEW_GROUP | NO_WINDOW, close_fds=True)


def wait_until_up(server: subprocess.Popen, timeout: float) -> bool:
    """Poll until the site answers; give up early if the server process has exited."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if site_up():
            return True
        if server.poll() is not None:
            return False
        time.sleep(0.5)
    return False


def log_tail(lines: int = 4) -> str:
    try:
        return "\n".join(shown(LOG).read_text(encoding="utf-8", errors="replace").strip().splitlines()[-lines:])
    except OSError:
        return ""


def edge() -> str | None:
    import winreg
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            key = winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe")
            path = winreg.QueryValue(key, None)
            if path and Path(path).exists():
                return path
        except OSError:
            pass
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
        if base and (p := Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe").exists():
            return str(p)
    return shutil.which("msedge")


def open_window() -> None:
    """Edge in app mode: its own window and taskbar button, no tabs or address bar.
    Falls back to a tab in the default browser."""
    if exe := edge():
        subprocess.Popen([exe, f"--app={URL}/"], creationflags=NO_WINDOW)
    else:
        webbrowser.open(f"{URL}/")


def kill(pid: int) -> None:
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, creationflags=NO_WINDOW)
    for _ in range(20):
        if listener_pid() is None:
            return
        time.sleep(0.25)


def launch() -> None:
    pid = listener_pid()
    if pid is not None:
        if not is_ours(pid):
            message(f"Port {PORT} is held by process {pid}, which isn't the Rewatchables site.\n\n"
                    f"Close it (or run Stop Rewatchables Explorer if it's the old Streamlit app) "
                    f"and try again.", error=True)
            return
        open_window()
        return

    if not FRAMEWORK.exists():
        message(f"Observable Framework isn't installed in {SITE}.\n\n"
                f"Run  npm --prefix site install  from the repo and try again.", error=True)
        return
    if not (exe := node()):
        message("Node.js wasn't found. Install Node 20 or later and try again.", error=True)
        return

    server = start_server(exe)
    if not wait_until_up(server, SERVE_TIMEOUT_S):
        why = (f"stopped with exit code {server.returncode}" if server.poll() is not None
               else f"didn't answer within {SERVE_TIMEOUT_S} seconds")
        message(f"The Rewatchables site's dev server {why}.\n\n{log_tail()}\n\nFull log: {shown(LOG)}",
                error=True)
        return
    open_window()


def stop() -> None:
    pid = listener_pid()
    if pid is None:
        message(f"The Rewatchables site isn't running (nothing on port {PORT}).")
        return
    if not is_ours(pid):
        message(f"Port {PORT} is held by process {pid}, which isn't the Rewatchables site. "
                f"Left it alone.", error=True)
        return
    kill(pid)
    message(f"Stopped the Rewatchables site's dev server (process {pid}).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stop", action="store_true", help=f"stop the server on :{PORT} instead of opening")
    args = ap.parse_args()
    try:
        stop() if args.stop else launch()
    except Exception as exc:  # no console: surface anything unexpected
        message(f"{type(exc).__name__}: {exc}", error=True)
