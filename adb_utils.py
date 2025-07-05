# adb_utils.py

"""Utility helpers for interacting with the game on macOS."""

import psutil
import pyautogui
from PIL import Image


def ensure_app_running():
    """Ensure the game process is running on macOS."""
    for proc in psutil.process_iter(['name']):
        if proc.info['name'] in ('The Tower', 'TheTower'):
            return
    raise SystemExit("[FATAL] 'The Tower' process not found")


def mac_screencap() -> Image.Image:
    """Capture the current screen and return a PIL Image."""
    return pyautogui.screenshot()


def mac_tap(x: int, y: int):
    """Simulate a tap/click at the given coordinates."""
    pyautogui.click(x, y)


# Backwards compatibility for modules still importing old names
ensure_adb_connected = ensure_app_running
adb_screencap = mac_screencap
