#!/usr/bin/env python3
from pathlib import Path
from typing import List, Dict

# Path to your regions.json file
REGION_FILE = Path(__file__).parent / "regions.json"

# Default regions & coordinates (4-tuples for OCR regions; 2-tuples for tap points)
DEFAULT_REGIONS: Dict[str, List[int]] = {
    "new_perk_region":    [483,   194, 505,  73],
    "perk1_region":       [159,   553,1124,243],
    "perk2_region":       [159,   818,1124,213],
    "perk3_region":       [159,  1072,1124,224],
    "perk4_region":       [159,  1336,1124,224],
    "retry1_region":      [250,  1850, 280, 80],
    "retry2_region":      [256,  1920, 284, 80],
    "defence_region":     [10,   1490, 820, 90],
    "health_region":      [400,  1785, 270, 45],
    "abs_def_region":     [1088, 2065, 276, 38],
    "claim_region":       [86,   1023, 216, 68],
    "wave_region":        [743,  1315, 377, 65],
    "float_gem_coord":    [960,   748],      # tap point for floating gem
    "def_tab_tap_coord":  [530,  2420],      # tap point to open Defence Upgrades
}

# Your default perk‐priority list (words only; no numeric values)
PERK_PRIORITY_DEFAULT: List[str] = [
    "increase max game speed",
    "perk wave requirement",
    "all coins bonuses",
    "cash bonus",
    "golden tower bonus",
    "black hole duration",
    "free upgrade chance",
    "defense percent",
    "max health",
    "unlock a random ultimate weapon",
    "enemies have",
    "damage",
    "defense absolute",
    "land mine damage",
    "orbs",
    "bounce shot",
    "chain lightning damage",
    "boss health but boss speed",
    "swamp radius",
    "extra set of inner mines",
    "death wave",
    "spotlight damage bonus",
    "chrono field duration",
    "more smart missiles",
    "interest",
    "health regen",
    "tower damage but bosses",
    "enemies damage tower damage",
    "enemies speed but enemies damage",
    "ranged enemies attack distance",
    "cash per wave",
    "lifesteal but knockback",
    "coins per wave tower health",
    "tower health regen but tower",
    "coins but tower max",
]
