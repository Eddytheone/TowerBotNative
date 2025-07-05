#!/usr/bin/env python3
"""
tower_bot_core.py

Tower Bot Core v2.12 – logic, JSON region generation, OCR & ADB helpers
=====================================================================
This module handles:
 • Generating a default regions.json
 • Loading regions
 • Config classes & state
 • ADB connect & screenshot
 • OCR processing
 • Debounce logic
 • TowerBot engine (no GUI)

Performance improvements:
 • Single screenshot per loop
 • NumPy‐based white‐pixel checks
 • Reduced OCR scaling (1.5×) with whitelists
 • Loop throttled to ~10 FPS
 • Profiling debug timings for OCR
Author: ChatGPT (OpenAI)
Date:   09 May 2025
"""
from __future__ import annotations
import json
import shutil
import threading
import time
import psutil
try:
    import pyautogui  # type: ignore
    _HAS_PYAUTOGUI = True
except Exception as e:  # noqa: PIE786 - broad except ok for optional dep
    pyautogui = None
    _PYAUTO_ERROR = e
    _HAS_PYAUTOGUI = False
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Tuple, Dict, Optional

import numpy as np
import pytesseract
from PIL import Image, ImageEnhance

# ← externalized configuration
from config import REGION_FILE, DEFAULT_REGIONS, PERK_PRIORITY_DEFAULT

# ──────────────────────────────────────────────────────────────
# Bot State Machine
# ──────────────────────────────────────────────────────────────
class BotState(Enum):
    IDLE            = 0
    UPGRADING       = 1
    PERK_SELECTING  = 2
    WAITING         = 3

# ──────────────────────────────────────────────────────────────
# Configuration Dataclass
# ──────────────────────────────────────────────────────────────
@dataclass
class BotConfig:
    # Feature toggles
    retry_enabled:   bool = True
    health_enabled:  bool = True
    abs_def_enabled: bool = True
    gems_enabled:    bool = True
    float_enabled:   bool = False
    perk_enabled:    bool = False
    debug_enabled:   bool = False

    # Runtime state
    running:     bool     = False
    state:       BotState = BotState.IDLE
    wave_number: int      = 0

    # Stop thresholds
    health_stop: int = 999999
    abs_def_stop:int = 999999
    perk_stop:   int = 999999

    # Action intervals (seconds)
    retry_interval:   float = 2.0
    defence_interval: float = 1.0
    upgrade_interval: float = 1.0
    gems_interval:    float = 1.0
    wave_interval:    float = 1.0
    float_interval:   float = 2.0
    perk_interval:    float = 2.0

    # OCR / tap regions (loaded from JSON)
    new_perk_region: Tuple[int,int,int,int] = field(default_factory=lambda: DEFAULT_REGIONS['new_perk_region'])
    perk1_region:    Tuple[int,int,int,int] = field(default_factory=lambda: DEFAULT_REGIONS['perk1_region'])
    perk2_region:    Tuple[int,int,int,int] = field(default_factory=lambda: DEFAULT_REGIONS['perk2_region'])
    perk3_region:    Tuple[int,int,int,int] = field(default_factory=lambda: DEFAULT_REGIONS['perk3_region'])
    perk4_region:    Tuple[int,int,int,int] = field(default_factory=lambda: DEFAULT_REGIONS['perk4_region'])
    retry1_region:   Tuple[int,int,int,int] = field(default_factory=lambda: DEFAULT_REGIONS['retry1_region'])
    retry2_region:   Tuple[int,int,int,int] = field(default_factory=lambda: DEFAULT_REGIONS['retry2_region'])
    defence_region:  Tuple[int,int,int,int] = field(default_factory=lambda: DEFAULT_REGIONS['defence_region'])
    health_region:   Tuple[int,int,int,int] = field(default_factory=lambda: DEFAULT_REGIONS['health_region'])
    abs_def_region:  Tuple[int,int,int,int] = field(default_factory=lambda: DEFAULT_REGIONS['abs_def_region'])
    claim_region:    Tuple[int,int,int,int] = field(default_factory=lambda: DEFAULT_REGIONS['claim_region'])
    wave_region:     Tuple[int,int,int,int] = field(default_factory=lambda: DEFAULT_REGIONS['wave_region'])
    float_gem_coord: Tuple[int,int]         = field(default_factory=lambda: DEFAULT_REGIONS['float_gem_coord'])

    # Perk priority list
    perk_priority:   List[str] = field(default_factory=lambda: PERK_PRIORITY_DEFAULT.copy())

    # Internal debounce state
    _cooldown:      Dict[str,float] = field(default_factory=dict, init=False)
    _cooldown_time: Dict[str,float] = field(default_factory=lambda: {
        'retry':2.0,'def':1.0,'upg':1.0,'gems':1.0,'float':2.0,'perk':3.0
    }, init=False)

def load_regions(cfg: BotConfig):
    """
    Load region values from regions.json into cfg.
    Generate the file from DEFAULT_REGIONS on first run.
    """
    if not REGION_FILE.exists():
        with open(REGION_FILE, "w") as f:
            json.dump(DEFAULT_REGIONS, f, indent=2)
    data = json.loads(REGION_FILE.read_text())
    for k, v in data.items():
        if hasattr(cfg, k):
            setattr(cfg, k, tuple(v))

# Initialize configuration and load JSON
cfg = BotConfig()
load_regions(cfg)

# ──────────────────────────────────────────────────────────────
# macOS & Tesseract Setup
# ──────────────────────────────────────────────────────────────
TESS_PATH = shutil.which("tesseract") or shutil.which("/opt/homebrew/bin/tesseract")
if TESS_PATH:
    pytesseract.pytesseract.tesseract_cmd = TESS_PATH
else:
    print("[WARN] tesseract not found – OCR functions will return empty strings")

def ensure_app_running():
    """Check if the game process is running on macOS.

    Returns ``True`` when found, ``False`` otherwise. The previous behaviour was
    to terminate the program which made testing difficult.
    """
    for proc in psutil.process_iter(['name', 'exe', 'cmdline']):
        name = (proc.info.get('name') or '').lower()
        exe = (proc.info.get('exe') or '').lower()
        cmd = ' '.join(proc.info.get('cmdline') or []).lower()
        if 'tower' in name or 'tower' in exe or 'tower' in cmd:
            return True
    return False

def mac_screencap() -> Image.Image:
    """Capture the current screen and return a PIL Image.

    Returns a 1×1 blank image if ``pyautogui`` is unavailable.
    """
    if _HAS_PYAUTOGUI:
        return pyautogui.screenshot()  # type: ignore[arg-type]
    # Provide a dummy image with a typical screen size to keep cv2 happy
    return Image.new("RGB", (1280, 720))

def mac_tap(x: int, y: int):
    """Simulate a tap/click at the given coordinates.

    No-op if ``pyautogui`` is unavailable.
    """
    if _HAS_PYAUTOGUI:
        pyautogui.click(x, y)  # type: ignore[arg-type]

# Verify the game is running at startup (optional during tests)
ensure_app_running()

# ──────────────────────────────────────────────────────────────
# Helper Functions
# ──────────────────────────────────────────────────────────────
# Backwards compatibility for legacy imports
adb_screencap = mac_screencap

def ocr_text(img: Image.Image,
             region: Tuple[int,int,int,int],
             whitelist: Optional[str] = None
) -> Tuple[str, float]:
    """
    OCR on a cropped region with preprocessing.
    Returns (text, elapsed_ms).
    """
    x,y,w,h = region
    crop = img.crop((x,y,x+w,y+h)).convert("L")
    crop = crop.resize((int(w*1.5), int(h*1.5)), Image.LANCZOS)
    crop = ImageEnhance.Contrast(crop).enhance(1.5)
    crop = ImageEnhance.Sharpness(crop).enhance(1.2)
    crop = crop.point(lambda p: 255 if p>160 else 0)
    config = "--oem 3 --psm 7"
    if whitelist:
        config += f" -c tessedit_char_whitelist={whitelist}"
    t0 = time.perf_counter()
    txt = pytesseract.image_to_string(crop, config=config)
    elapsed = (time.perf_counter() - t0) * 1000
    return txt.replace("\n"," ").lower().strip(), elapsed

def region_has_white(img: Image.Image, region: Tuple[int,int,int,int]) -> bool:
    """Fast check for any near-white pixel via NumPy array."""
    x,y,w,h = region
    arr = np.array(img.crop((x,y,x+w,y+h)).convert("L"))
    return bool((arr > 250).any())

def can_act(cfg: BotConfig, key: str) -> bool:
    """Debounce helper: allow action once per cooldown interval."""
    now = time.time()
    cd  = cfg._cooldown_time.get(key, getattr(cfg, f"{key}_interval", 0))
    if now >= cfg._cooldown.get(key, 0):
        cfg._cooldown[key] = now + cd
        return True
    return False

# ──────────────────────────────────────────────────────────────
# TowerBot Engine
# ──────────────────────────────────────────────────────────────
class TowerBot:
    def __init__(self, cfg: BotConfig):
        self.cfg = cfg
        self._stop = threading.Event()
        self._thr: Optional[threading.Thread] = None
        now = time.perf_counter()
        self._next = {k: now for k in ['retry','def','upg','gems','wave','float','perk']}

    def _dbg(self, *msgs):
        if self.cfg.debug_enabled:
            print('[DEBUG]', *msgs)

    def start(self):
        if self._thr and self._thr.is_alive():
            return
        self._stop.clear()
        self._thr = threading.Thread(target=self._loop, daemon=True)
        self._thr.start()

    def stop(self):
        if self._thr and self._thr.is_alive():
            self._stop.set()
            self._thr.join()

    def _handle_perk_selection(self, img: Image.Image):
        # 1) Tap the NEW PERK button
        x,y,w,h = self.cfg.new_perk_region
        mac_tap(x+w//2, y+h//2)
        time.sleep(0.5)
        img2 = mac_screencap()
        # 2) Choose first matching perk by priority
        for key in self.cfg.perk_priority:
            for reg in (self.cfg.perk1_region, self.cfg.perk2_region, self.cfg.perk3_region, self.cfg.perk4_region):
                if key in ocr_text(img2, reg)[0]:
                    x2,y2,w2,h2 = reg
                    mac_tap(x2+w2//2, y2+h2//2)
                    return
        # Fallback: tap first option
        x2,y2,w2,h2 = self.cfg.perk1_region
        mac_tap(x2+w2//2, y2+h2//2)

    def _loop(self):
        while not self._stop.is_set():
            now = time.perf_counter()
            if not ensure_app_running():
                self._dbg("Warning: 'The Tower' process not found")
            img = mac_screencap()

            # Suspend other actions if selecting perks
            if self.cfg.state == BotState.PERK_SELECTING:
                self._handle_perk_selection(img)
                self.cfg.state = BotState.IDLE
                self._next['perk'] = now + self.cfg.perk_interval
                time.sleep(0.1)
                continue

            # 1) Wave OCR
            if now >= self._next['wave']:
                self._next['wave'] = now + self.cfg.wave_interval
                text, dt = ocr_text(img, self.cfg.wave_region, whitelist="0123456789")
                m = re.search(r"\b(\d+)\b", text)
                if m:
                    self.cfg.wave_number = int(m.group(1))
                    self._dbg(f"Wave {self.cfg.wave_number} ({dt:.1f} ms)")

            # 2) Retry
            if self.cfg.retry_enabled and now >= self._next['retry']:
                self._next['retry'] = now + self.cfg.retry_interval
                for reg in (self.cfg.retry1_region, self.cfg.retry2_region):
                    text, dt = ocr_text(img, reg, whitelist="retry ")
                    if "retry" in text and can_act(self.cfg, 'retry'):
                        self._dbg(f"Retry detected ({dt:.1f} ms)")
                        mac_tap(530, 2420)
                        img = mac_screencap()
                        break

            # 3) Defence tab
            active = False
            if now >= self._next['def']:
                self._next['def'] = now + self.cfg.defence_interval
                text, dt = ocr_text(img, self.cfg.defence_region)
                active = "defense upgrades" in text
                self._dbg(f"Defence Active? {active} ({dt:.1f} ms)")
                if not active and can_act(self.cfg, 'def'):
                    mac_tap(530, 2420)
                    img = mac_screencap()

            # 4) Purchases via white-pixel detection
            if active and now >= self._next['upg']:
                self._next['upg'] = now + self.cfg.upgrade_interval
                if (self.cfg.health_enabled and self.cfg.wave_number < self.cfg.health_stop
                        and can_act(self.cfg, 'health')
                        and region_has_white(img, self.cfg.health_region)):
                    self._dbg("Health Up available")
                    x,y,w,h = self.cfg.health_region
                    mac_tap(x+w//2, y+h//2)
                if (self.cfg.abs_def_enabled and self.cfg.wave_number < self.cfg.abs_def_stop
                        and can_act(self.cfg, 'abs_def')
                        and region_has_white(img, self.cfg.abs_def_region)):
                    self._dbg("AbsDef Up available")
                    x,y,w,h = self.cfg.abs_def_region
                    mac_tap(x+w//2, y+h//2)

            # 5) Free gems claim
            if self.cfg.gems_enabled and now >= self._next['gems'] and can_act(self.cfg, 'gems'):
                self._next['gems'] = now + self.cfg.gems_interval
                text, dt = ocr_text(img, self.cfg.claim_region)
                self._dbg(f"Claim OCR raw: '{text}' ({dt:.1f} ms)")
                if "claim" in text:
                    self._dbg("Claim detected—tapping!")
                    x,y,w,h = self.cfg.claim_region
                    mac_tap(x+w//2, y+h//2)

            # 6) Floating gem
            if self.cfg.float_enabled and now >= self._next['float'] and can_act(self.cfg, 'float'):
                self._next['float'] = now + self.cfg.float_interval
                x,y = self.cfg.float_gem_coord
                self._dbg("Float Gem tap")
                mac_tap(x, y)

            # 7) Detect NEW PERK trigger
            if self.cfg.perk_enabled and now >= self._next['perk']:
                text, dt = ocr_text(img, self.cfg.new_perk_region)
                if "new perk" in text:
                    self._dbg(f"NEW PERK! ({dt:.1f} ms)")
                    self.cfg.state = BotState.PERK_SELECTING

            time.sleep(0.1)
