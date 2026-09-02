"""
Converts python/inicial/160-100.jpg to sketch/logo_bitmap.h
as a raw RGB565 uint16_t array for use with tft.drawRGBBitmap().

Usage:
    py -3.12 convert_logo.py
"""

import struct
from pathlib import Path
from PIL import Image

SRC = Path(__file__).parent / "python" / "inicial" / "160-100.jpg"
DST = Path(__file__).parent / "sketch" / "logo_bitmap.h"

img = Image.open(SRC).convert("RGB")
w, h = img.size
print(f"Source image: {w}x{h} px -> {w*h*2} bytes RGB565")

pixels = list(img.getdata())

def to_rgb565(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)

lines = [
    "#pragma once",
    "#include <stdint.h>",
    f"",
    f"static const uint16_t LOGO_W = {w};",
    f"static const uint16_t LOGO_H = {h};",
    f"",
    f"// RGB565 bitmap for the intro logo ({w}x{h} px, {w*h} pixels, {w*h*2} bytes)",
    f"static const uint16_t LOGO_BITMAP[{w*h}] PROGMEM = {{",
]

row_strings = []
for row in range(h):
    row_vals = []
    for col in range(w):
        r, g, b = pixels[row * w + col]
        row_vals.append(f"0x{to_rgb565(r, g, b):04X}")
    row_strings.append("  " + ", ".join(row_vals))

lines.append(",\n".join(row_strings))
lines.append("};")

content = "\n".join(lines)
DST.write_text(content, encoding="utf-8")
print(f"Written: {DST}  ({DST.stat().st_size // 1024} KB)")
