# adb_utils.py

"""Utility helpers for interacting with the game on macOS."""

import psutil
from PIL import Image

try:  # pyautogui needs a display; allow import failure in headless envs
    import pyautogui  # type: ignore
    _HAS_PYAUTOGUI = True
except Exception as e:  # noqa: PIE786 - broad except ok for optional dep
    pyautogui = None
    _PYAUTO_ERROR = e
    _HAS_PYAUTOGUI = False


def ensure_app_running():
    """Ensure the game process is running on macOS.

    In testing environments the process may not exist. Instead of raising a
    fatal error, simply return False when the process is missing so callers can
    decide how to proceed.
    """
    for proc in psutil.process_iter(['name']):
        if proc.info['name'] in ('The Tower', 'TheTower'):
            return True
    return False


def mac_screencap() -> Image.Image:
    """Capture the current screen and return a PIL Image.

    Falls back to a 1×1 blank image if ``pyautogui`` is unavailable.
    """
    if _HAS_PYAUTOGUI:
        return pyautogui.screenshot()  # type: ignore[arg-type]
    # Provide a dummy image with a typical screen size to keep cv2 happy
    return Image.new("RGB", (1280, 720))


def mac_tap(x: int, y: int):
    """Simulate a tap/click at the given coordinates.

    On headless systems this is a no-op.
    """
    if _HAS_PYAUTOGUI:
        pyautogui.click(x, y)  # type: ignore[arg-type]


# Backwards compatibility for modules still importing old names
ensure_adb_connected = ensure_app_running
adb_screencap = mac_screencap
