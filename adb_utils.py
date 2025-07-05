# adb_utils.py

"""Utility helpers for interacting with the game on macOS."""

import psutil
from PIL import Image

# Optional Quartz import for background clicks on macOS
try:  # Quartz is only available on macOS with PyObjC installed
    import Quartz
    _HAS_QUARTZ = True
except Exception as e:  # noqa: PIE786 - broad except ok for optional dep
    Quartz = None
    _QUARTZ_ERROR = e
    _HAS_QUARTZ = False

try:  # pyautogui needs a display; allow import failure in headless envs
    import pyautogui  # type: ignore
    _HAS_PYAUTOGUI = True
except Exception as e:  # noqa: PIE786 - broad except ok for optional dep
    pyautogui = None
    _PYAUTO_ERROR = e
    _HAS_PYAUTOGUI = False

# Screen scale factor for HiDPI displays (e.g. Retina)
_SCREEN_SCALE: float = 1.0


def _get_app_pid() -> int | None:
    """Return the process ID of the game if running, otherwise ``None``."""
    for proc in psutil.process_iter(['pid', 'name', 'exe', 'cmdline']):
        name = (proc.info.get('name') or '').lower()
        exe = (proc.info.get('exe') or '').lower()
        cmd = ' '.join(proc.info.get('cmdline') or []).lower()
        if 'tower' in name or 'tower' in exe or 'tower' in cmd:
            return proc.info['pid']
    return None


def ensure_app_running() -> bool:
    """Return ``True`` if the game process is running on macOS."""
    return _get_app_pid() is not None


def mac_screencap() -> Image.Image:
    """Capture the current screen and return a PIL Image.

    Falls back to a 1×1 blank image if ``pyautogui`` is unavailable.
    """
    if _HAS_PYAUTOGUI:
        img = pyautogui.screenshot()  # type: ignore[arg-type]
        # Update screen scale on each capture in case of display changes
        try:
            w, h = pyautogui.size()  # type: ignore[attr-defined]
            global _SCREEN_SCALE
            if w and h:
                scale_x = img.width / w
                scale_y = img.height / h
                scale = (scale_x + scale_y) / 2
                if scale > 0:
                    _SCREEN_SCALE = scale
        except Exception:
            pass
        return img
    # Provide a dummy image with a typical screen size to keep cv2 happy
    return Image.new("RGB", (1280, 720))


def mac_tap(x: int, y: int):
    """Simulate a tap/click at ``(x, y)`` without moving the visible cursor."""
    scale = _SCREEN_SCALE or 1.0
    xs, ys = int(x / scale), int(y / scale)
    if _HAS_QUARTZ:
        pid = _get_app_pid()
        if pid is not None:
            for ev in (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp):
                event = Quartz.CGEventCreateMouseEvent(
                    None, ev, (xs, ys), Quartz.kCGMouseButtonLeft
                )
                Quartz.CGEventSetIntegerValueField(
                    event, Quartz.kCGEventTargetUnixProcessID, pid
                )
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
                Quartz.CFRelease(event)
            return
    if _HAS_PYAUTOGUI:
        pyautogui.click(xs, ys)  # type: ignore[arg-type]


# Backwards compatibility for modules still importing old names
ensure_adb_connected = ensure_app_running
adb_screencap = mac_screencap
