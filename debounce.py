# debounce.py

import time
from typing import Dict

def can_act(cfg, key: str) -> bool:
    """
    Allow an action only once per cooldown interval.
    Expects cfg._cooldown_time and cfg._cooldown dicts.
    """
    now = time.time()
    interval = cfg._cooldown_time.get(key, getattr(cfg, f"{key}_interval", 0))
    if now >= cfg._cooldown.get(key, 0):
        cfg._cooldown[key] = now + interval
        return True
    return False
