"""Start Kodi and fit it to the current display mode. Run by the Unified Remote "Kodi" remote.

    launch      start Kodi if needed, fit it to the mode, bring it to the front
    fullscreen  toggle fullscreen
    home        go to Kodi's home screen
    quit        close Kodi

Each command has a matching commands/<name>.pyw for the remote to start with pythonw, or run
`python kodi_control.py <command>`.

Couch: fullscreen on the TV.
Desk:  a window at 65% of the main (Dell) monitor; the remote's Fullscreen button makes it fullscreen.

The mode comes from DisplayModes' current-mode.txt, the same file puckstream reads. Kodi is
controlled over its local JSON-RPC port (9090, on by default as "Allow remote control from
applications on this system"). The only Kodi setting it touches is Display mode (fullscreen or
windowed).
"""
import ctypes
import ctypes.wintypes as wt
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

KODI_EXE = r"C:\Program Files\Kodi\kodi.exe"
MODE_FILE = Path(r"C:\Users\harri\DisplayModes\logs\current-mode.txt")
HERE = Path(__file__).resolve().parent
LOG = HERE / "logs" / "kodi_remote.log"
APPLIED = HERE / "logs" / "applied-mode.txt"  # mode last applied to the running Kodi
DESK_FRACTION = 0.65

user32 = ctypes.windll.user32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # real pixels, not scaled ones
except Exception:
    pass


def log(msg):
    LOG.parent.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")


def current_mode():
    try:
        m = MODE_FILE.read_text().strip().title()
        return m if m in ("Couch", "Desk") else "Desk"
    except OSError:
        return "Desk"


def rpc(method, params=None, timeout=2.0):
    msg = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    with socket.create_connection(("127.0.0.1", 9090), timeout) as s:
        s.sendall(json.dumps(msg).encode())
        buf = b""
        while True:
            buf += s.recv(65536)
            try:
                return json.loads(buf).get("result")
            except ValueError:
                continue


def kodi_window():
    """Kodi's top-level window handle, or 0."""
    found = []
    pid = wt.DWORD()

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in kodi_pids():
                found.append(hwnd)
                return False
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else 0


_pids = None


def kodi_pids():
    global _pids
    if _pids is None:
        out = subprocess.run(["tasklist", "/fi", "imagename eq kodi.exe", "/fo", "csv", "/nh"],
                             capture_output=True, text=True, creationflags=0x08000000).stdout
        _pids = {int(line.split('","')[1]) for line in out.splitlines() if line.startswith('"kodi')}
    return _pids


def wait_for_rpc(seconds):
    end = time.time() + seconds
    while time.time() < end:
        try:
            rpc("JSONRPC.Ping", timeout=1)
            return True
        except OSError:
            time.sleep(0.5)
    return False


def bring_to_front(hwnd):
    if not hwnd:
        return
    # Windows only lets the foreground app hand focus over; a tap of Alt lifts that lock.
    user32.keybd_event(0x12, 0, 0, 0)
    user32.keybd_event(0x12, 0, 2, 0)
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)


def place_desk_window(hwnd):
    """Centre a 65% window on the primary monitor."""
    w, h = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    ww, wh = int(w * DESK_FRACTION), int(h * DESK_FRACTION)
    user32.SetWindowPos(hwnd, 0, (w - ww) // 2, (h - wh) // 2, ww, wh, 0x0040)  # SWP_SHOWWINDOW


def set_fullscreen(fullscreen):
    # Kodi's own Display > Display mode setting: DESKTOP is fullscreen, WINDOW is windowed.
    rpc("Settings.SetSettingValue", {"setting": "videoscreen.screenmode",
                                     "value": "DESKTOP" if fullscreen else "WINDOW"})
    if not fullscreen:
        time.sleep(1.5)
        hwnd = kodi_window()
        if hwnd:
            place_desk_window(hwnd)


def is_fullscreen():
    return rpc("Settings.GetSettingValue", {"setting": "videoscreen.screenmode"})["value"] != "WINDOW"


def apply_mode(mode):
    fullscreen = mode == "Couch"
    set_fullscreen(fullscreen)
    APPLIED.write_text(mode)
    log(f"applied {mode}: fullscreen={fullscreen}")


def launch():
    mode = current_mode()
    started = False
    if not kodi_pids():
        subprocess.Popen([KODI_EXE], cwd=str(Path(KODI_EXE).parent))
        started = True
        log(f"started Kodi ({mode})")
    if not wait_for_rpc(40 if started else 5):
        log("Kodi did not answer on port 9090")
        return
    applied = APPLIED.read_text().strip() if APPLIED.exists() else ""
    # Fit Kodi to the mode when it has just started or the mode changed since; otherwise leave
    # alone a window the user has made fullscreen (or not) on purpose.
    if started or applied != mode:
        apply_mode(mode)
    globals()["_pids"] = None
    bring_to_front(kodi_window())


def toggle_fullscreen():
    set_fullscreen(not is_fullscreen())


def main(cmd=None):
    cmd = cmd or (sys.argv[1] if len(sys.argv) > 1 else "launch")
    LOG.parent.mkdir(exist_ok=True)
    try:
        if cmd == "launch":
            launch()
        elif cmd == "fullscreen":
            toggle_fullscreen()
        elif cmd == "home":
            rpc("Input.Home")
        elif cmd == "quit":
            # Leave Kodi's saved display mode at its default (fullscreen) for launches that don't
            # come through this remote. Kodi saves settings on exit.
            rpc("Settings.SetSettingValue", {"setting": "videoscreen.screenmode", "value": "DESKTOP"})
            rpc("Application.Quit")
            APPLIED.unlink(missing_ok=True)
            log("quit Kodi")
    except Exception as e:  # pythonw has no console; keep a trace of what went wrong
        log(f"{cmd} failed: {e!r}")


if __name__ == "__main__":
    main()
