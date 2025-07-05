# ocr_utils.py

import time
import pytesseract
import numpy as np
from PIL import Image, ImageEnhance
from typing import Tuple, Optional

def ocr_text(
    img: Image.Image,
    region: Tuple[int,int,int,int],
    whitelist: Optional[str] = None
) -> Tuple[str, float]:
    """
    Perform OCR on the given region.
    Returns (recognized_text, elapsed_ms).
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
    start = time.perf_counter()
    try:
        txt = pytesseract.image_to_string(crop, config=config)
    except pytesseract.TesseractNotFoundError:
        # When Tesseract is missing, return empty text to avoid crashes
        return "", 0.0
    elapsed = (time.perf_counter() - start) * 1000
    return txt.replace("\n"," ").lower().strip(), elapsed

def region_has_white(
    img: Image.Image,
    region: Tuple[int,int,int,int]
) -> bool:
    """
    Fast white‐pixel detector via NumPy.
    Returns True if any pixel >250 in the region.
    """
    x,y,w,h = region
    arr = np.array(img.crop((x,y,x+w,y+h)).convert("L"))
    return bool((arr > 250).any())
