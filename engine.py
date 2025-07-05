#!/usr/bin/env python3
"""
engine.py

Tower Bot Engine v2.17 – pauses all other actions while selecting a perk.
Uses OpenCV template‐matching (with auto‐resize) only for:
  • Defence Tab
  • Claim Gems
  • New Perk detection & initial tap

All other interactions use OCR or direct‐tap coordinates.
"""
from __future__ import annotations
import json
import threading
import time
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Tuple, Dict, Optional

import numpy as np
import cv2
from PIL import Image

from config import REGION_FILE, DEFAULT_REGIONS, PERK_PRIORITY_DEFAULT
from adb_utils import ensure_app_running, mac_screencap, mac_tap
from ocr_utils import ocr_text, region_has_white
from debounce import can_act

# ──────────────────────────────────────────────────────────────
class BotState(Enum):
    IDLE           = 0
    UPGRADING      = 1
    PERK_SELECTING = 2
    WAITING        = 3

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

    # Runtime
    running:     bool     = False
    state:       BotState = BotState.IDLE
    wave_number: int      = 0

    # Stop‐after thresholds
    health_stop: int = 999999
    abs_def_stop: int = 999999
    perk_stop:    int = 999999

    # Intervals (seconds)
    retry_interval:   float = 2.0
    defence_interval: float = 1.0
    upgrade_interval: float = 1.0
    gems_interval:    float = 1.0
    wave_interval:    float = 1.0
    float_interval:   float = 2.0
    perk_interval:    float = 2.0

    # OCR / template regions (x, y, w, h)
    new_perk_region:  Tuple[int,int,int,int] = field(default_factory=lambda: tuple(DEFAULT_REGIONS['new_perk_region']))
    perk1_region:     Tuple[int,int,int,int] = field(default_factory=lambda: tuple(DEFAULT_REGIONS['perk1_region']))
    perk2_region:     Tuple[int,int,int,int] = field(default_factory=lambda: tuple(DEFAULT_REGIONS['perk2_region']))
    perk3_region:     Tuple[int,int,int,int] = field(default_factory=lambda: tuple(DEFAULT_REGIONS['perk3_region']))
    perk4_region:     Tuple[int,int,int,int] = field(default_factory=lambda: tuple(DEFAULT_REGIONS['perk4_region']))
    retry1_region:    Tuple[int,int,int,int] = field(default_factory=lambda: tuple(DEFAULT_REGIONS['retry1_region']))
    retry2_region:    Tuple[int,int,int,int] = field(default_factory=lambda: tuple(DEFAULT_REGIONS['retry2_region']))
    defence_region:   Tuple[int,int,int,int] = field(default_factory=lambda: tuple(DEFAULT_REGIONS['defence_region']))
    health_region:    Tuple[int,int,int,int] = field(default_factory=lambda: tuple(DEFAULT_REGIONS['health_region']))
    abs_def_region:   Tuple[int,int,int,int] = field(default_factory=lambda: tuple(DEFAULT_REGIONS['abs_def_region']))
    claim_region:     Tuple[int,int,int,int] = field(default_factory=lambda: tuple(DEFAULT_REGIONS['claim_region']))
    wave_region:      Tuple[int,int,int,int] = field(default_factory=lambda: tuple(DEFAULT_REGIONS['wave_region']))

    # Direct‐tap coordinates (x, y)
    float_gem_coord:   Tuple[int,int] = field(default_factory=lambda: tuple(DEFAULT_REGIONS['float_gem_coord']))
    def_tab_tap_coord: Tuple[int,int] = field(default_factory=lambda: tuple(DEFAULT_REGIONS['def_tab_tap_coord']))

    # Perk priority list
    perk_priority: List[str] = field(default_factory=lambda: PERK_PRIORITY_DEFAULT.copy())

    # Internal cooldowns
    _cooldown:      Dict[str,float] = field(default_factory=dict, init=False)
    _cooldown_time: Dict[str,float] = field(default_factory=lambda: {
        'retry':2.0, 'def':1.0, 'upg':1.0, 'gems':1.0, 'float':2.0, 'perk':3.0
    }, init=False)

# ──────────────────────────────────────────────────────────────
def load_regions(cfg: BotConfig):
    """Create regions.json if missing, then load all values into cfg."""
    if not REGION_FILE.exists():
        with open(REGION_FILE, "w") as f:
            json.dump(DEFAULT_REGIONS, f, indent=2)
    data = json.loads(REGION_FILE.read_text())
    for key, val in data.items():
        if hasattr(cfg, key):
            setattr(cfg, key, tuple(val))

# ──────────────────────────────────────────────────────────────
TEMPLATE_DIR = Path(__file__).parent / "templates"
TEMPLATES: Dict[str, np.ndarray] = {}
for name in ("defence_region","claim_region","new_perk_region"):
    p = TEMPLATE_DIR / f"{name}.png"
    if p.exists():
        TEMPLATES[name] = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)

def cv_match(sub: np.ndarray, tpl: np.ndarray) -> float:
    """Resize tpl to sub’s size if needed, then return max NCC score."""
    h_sub, w_sub = sub.shape[:2]
    h_tpl, w_tpl = tpl.shape[:2]
    if (h_sub, w_sub) != (h_tpl, w_tpl):
        tpl = cv2.resize(tpl, (w_sub, h_sub), interpolation=cv2.INTER_AREA)
    res = cv2.matchTemplate(sub, tpl, cv2.TM_CCOEFF_NORMED)
    return float(res.max())

# ──────────────────────────────────────────────────────────────
class TowerBot:
    def __init__(self, cfg: BotConfig):
        self.cfg    = cfg
        self._stop  = threading.Event()
        self._thr: Optional[threading.Thread] = None
        now = time.perf_counter()
        self._next = {k: now for k in ['retry','def','upg','gems','wave','float','perk']}

    def _dbg(self, *msgs):
        if self.cfg.debug_enabled:
            print("[DEBUG]", *msgs)

    def start(self):
        if self._thr and self._thr.is_alive(): return
        self._stop.clear()
        self._thr = threading.Thread(target=self._loop, daemon=True)
        self._thr.start()

    def stop(self):
        if self._thr and self._thr.is_alive():
            self._stop.set()
            self._thr.join()

    def _handle_perk_selection(self, img: Image.Image, gray: np.ndarray):
        """
        OCR each of perk1_region, perk2_region, perk3_region, perk4_region,
        match against perk_priority, tap the highest-priority perk,
        then clear state to IDLE.
        """
        text_regions = []
        for idx, reg in enumerate((self.cfg.perk1_region,
                                   self.cfg.perk2_region,
                                   self.cfg.perk3_region,
                                   self.cfg.perk4_region), start=1):
            txt, dt = ocr_text(img, reg)
            low = txt.lower()
            self._dbg(f"PERK OCR R{idx}: '{low.strip()}' ({dt:.1f}ms)")
            text_regions.append((idx, low, reg))

        chosen = None
        for priority in self.cfg.perk_priority:
            for idx, low, reg in text_regions:
                if priority in low:
                    chosen = (priority, idx, reg)
                    break
            if chosen:
                break

        if chosen:
            priority, idx, (x,y,w,h) = chosen
            cx, cy = x + w//2, y + h//2
            self._dbg(f"Selected perk '{priority}' in region {idx} → tapping", (cx, cy))
            mac_tap(cx, cy)
        else:
            self._dbg("No matching perk found")

        # Done selecting → return to main loop
        self.cfg.state = BotState.IDLE

    def _loop(self):
        load_regions(self.cfg)
        ensure_app_running()

        while not self._stop.is_set():
            now  = time.perf_counter()
            img  = mac_screencap()
            gray = cv2.cvtColor(np.array(img), cv2.COLOR_BGR2GRAY)

            # If in PERK_SELECTING state, only run perk handler
            if self.cfg.state == BotState.PERK_SELECTING:
                self._dbg("PERK_SELECTING → running handler")
                self._handle_perk_selection(img, gray)
                time.sleep(0.1)
                continue

            # 1) Wave OCR
            if now >= self._next['wave']:
                self._next['wave'] = now + self.cfg.wave_interval
                txt, dt = ocr_text(img, self.cfg.wave_region, whitelist="0123456789")
                m = re.search(r"\b(\d+)\b", txt)
                if m:
                    self.cfg.wave_number = int(m.group(1))
                    self._dbg(f"Wave {self.cfg.wave_number} ({dt:.1f} ms)")

            # 2) Retry OCR
            if ( self.cfg.retry_enabled
              and now >= self._next['retry']
              and can_act(self.cfg,'retry') ):
                self._next['retry'] = now + self.cfg.retry_interval
                for region in (self.cfg.retry1_region, self.cfg.retry2_region):
                    txt, _ = ocr_text(img, region)
                    if "retry" in txt.lower():
                        x,y,w,h = region
                        cx,cy = x+w//2, y+h//2
                        self._dbg("Retry → tapping", (cx,cy))
                        mac_tap(cx, cy)
                        break

            # 3) Defence Tab (CV + OCR fallback)
            if now >= self._next['def']:
                self._next['def'] = now + self.cfg.defence_interval
                tpl = TEMPLATES.get("defence_region")
                active = False
                if tpl is not None:
                    x,y,w,h = self.cfg.defence_region
                    sub = gray[y:y+h, x:x+w]
                    score = cv_match(sub, tpl)
                    active = (score >= 0.7)
                    self._dbg(f"DefTab CV score: {score:.2f}")
                else:
                    txt, _ = ocr_text(img, self.cfg.defence_region)
                    low = txt.lower()
                    active = (("defense" in low or "defence" in low) and "upgrade" in low)
                    self._dbg(f"DefTab OCR: '{txt.strip()}'")

                if not active and can_act(self.cfg,'def'):
                    xt,yt = self.cfg.def_tab_tap_coord
                    self._dbg("DefTab inactive → tapping", (xt,yt))
                    mac_tap(xt, yt)
                else:
                    self._dbg("DefTab active, skipping tap")

            # 4) Health & AbsDef upgrades (white-pixel OCR)
            if now >= self._next['upg'] and can_act(self.cfg,'upg'):
                self._next['upg'] = now + self.cfg.upgrade_interval

                if ( self.cfg.health_enabled
                  and self.cfg.wave_number < self.cfg.health_stop
                  and region_has_white(img, self.cfg.health_region) ):
                    x,y,w,h = self.cfg.health_region
                    cx,cy = x+w//2, y+h//2
                    self._dbg("Health → tapping", (cx,cy))
                    mac_tap(cx, cy)

                if ( self.cfg.abs_def_enabled
                  and self.cfg.wave_number < self.cfg.abs_def_stop
                  and region_has_white(img, self.cfg.abs_def_region) ):
                    x,y,w,h = self.cfg.abs_def_region
                    cx,cy = x+w//2, y+h//2
                    self._dbg("AbsDef → tapping", (cx,cy))
                    mac_tap(cx, cy)

            # 5) Float Gem tap
            if ( self.cfg.float_enabled
              and now >= self._next['float']
              and can_act(self.cfg,'float') ):
                self._next['float'] = now + self.cfg.float_interval
                x,y = self.cfg.float_gem_coord
                self._dbg("FloatGem → tapping", (x,y))
                mac_tap(x, y)

            # 6) Claim Gems (CV + OCR fallback)
            if ( self.cfg.gems_enabled
              and now >= self._next['gems']
              and can_act(self.cfg,'gems') ):
                self._next['gems'] = now + self.cfg.gems_interval
                tpl = TEMPLATES.get("claim_region")
                x,y,w,h = self.cfg.claim_region
                sub = gray[y:y+h, x:x+w]

                if tpl is not None:
                    score = cv_match(sub, tpl)
                    self._dbg(f"Claim CV score: {score:.2f}")
                    if score >= 0.7:
                        cx,cy = x+w//2, y+h//2
                        self._dbg("Claim → tapping", (cx,cy))
                        mac_tap(cx, cy)
                else:
                    txt,_ = ocr_text(img, self.cfg.claim_region)
                    if "claim" in txt.lower():
                        cx,cy = x+w//2, y+h//2
                        self._dbg("Claim OCR → tapping", (cx,cy))
                        mac_tap(cx, cy)

            # 7) New Perk detection (CV + OCR fallback)
            if ( self.cfg.perk_enabled
              and now >= self._next['perk']
              and can_act(self.cfg,'perk') ):
                self._next['perk'] = now + self.cfg.perk_interval
                tpl = TEMPLATES.get("new_perk_region")
                x,y,w,h = self.cfg.new_perk_region
                sub = gray[y:y+h, x:x+w]
                triggered = False

                if tpl is not None:
                    score = cv_match(sub, tpl)
                    triggered = (score >= 0.7)
                    self._dbg(f"NewPerk CV score: {score:.2f}")
                else:
                    txt,_ = ocr_text(img, self.cfg.new_perk_region)
                    triggered = ("new perk" in txt.lower())
                    self._dbg(f"NewPerk OCR: '{txt.strip()}'")

                if triggered:
                    cx,cy = x+w//2, y+h//2
                    self._dbg("NEW PERK → tapping centre to open menu", (cx,cy))
                    mac_tap(cx, cy)
                    self._dbg("Switching to PERK_SELECTING state")
                    self.cfg.state = BotState.PERK_SELECTING

            # sleep a short while to limit CPU usage
            time.sleep(0.1)
