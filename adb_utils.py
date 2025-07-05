# adb_utils.py

import subprocess
from pathlib import Path
from PIL import Image
from io import BytesIO

ADB_PATH = "/opt/homebrew/bin/adb"

def ensure_adb_connected():
    """Ensure BlueStacks is reachable via ADB."""
    try:
        subprocess.run(
            [ADB_PATH, "connect", "127.0.0.1:5555"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        devs = subprocess.check_output([ADB_PATH, "devices"]).decode()
        if "127.0.0.1:5555" not in devs or "device" not in devs:
            raise RuntimeError("ADB device not ready")
    except Exception as e:
        raise SystemExit(f"[FATAL] ADB connection failed: {e}")

def adb_screencap() -> Image.Image:
    """Capture the screen via adb and return as a PIL Image."""
    try:
        proc = subprocess.run(
            [ADB_PATH, '-s', '127.0.0.1:5555', 'exec-out', 'screencap', '-p'],
            check=True, stdout=subprocess.PIPE
        )
        return Image.open(BytesIO(proc.stdout))
    except:
        raw = subprocess.check_output(
            [ADB_PATH, '-s', '127.0.0.1:5555', 'shell', 'screencap', '-p']
        )
        raw = raw.replace(b"\r\r\n", b"\n").replace(b"\r\n", b"\n")
        return Image.open(BytesIO(raw))
