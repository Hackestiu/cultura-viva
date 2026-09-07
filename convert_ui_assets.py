from pathlib import Path
from PIL import Image

ROOT = Path(__file__).parent
SOURCE_DIR = ROOT / "python" / "assets"
DESTINATION = ROOT / "sketch" / "src" / "display" / "ui_assets.h"
TARGET_WIDTH = 160
TARGET_HEIGHT = 128

ASSETS = (
    ("UI_START_BITMAP", "start.png"),
    ("UI_OPTIONS_BITMAP", "skip_tutorial.png"),
    ("UI_TUTORIAL1_BITMAP", "tutorial_1.png"),
    ("UI_TUTORIAL2_BITMAP", "tutorial_2.png"),
    ("UI_TUTORIAL3_BITMAP", "tutorial_3.png"),
    ("UI_PERSONALITY_BITMAP", "choose_personality.png"),
)


def to_rgb565(red, green, blue):
    return ((red & 0xF8) << 8) | ((green & 0xFC) << 3) | (blue >> 3)


def bitmap_lines(image):
    pixels = list(image.getdata())
    lines = []
    for row in range(TARGET_HEIGHT):
        values = [
            f"0x{to_rgb565(*pixels[row * TARGET_WIDTH + column]):04X}"
            for column in range(TARGET_WIDTH)
        ]
        lines.append("  " + ", ".join(values))
    return ",\n".join(lines)


header = [
    "#pragma once",
    "#include <stdint.h>",
    "",
    f"static const uint16_t UI_BITMAP_W = {TARGET_WIDTH};",
    f"static const uint16_t UI_BITMAP_H = {TARGET_HEIGHT};",
    "",
]

for symbol, filename in ASSETS:
    source = SOURCE_DIR / filename
    image = Image.open(source).convert("RGB").resize(
        (TARGET_WIDTH, TARGET_HEIGHT), Image.Resampling.LANCZOS
    )
    header.extend(
        [
            f"static const uint16_t {symbol}[{TARGET_WIDTH * TARGET_HEIGHT}] PROGMEM = {{",
            bitmap_lines(image),
            "};",
            "",
        ]
    )

DESTINATION.write_text("\n".join(header), encoding="ascii")
print(f"Generated {DESTINATION} ({DESTINATION.stat().st_size // 1024} KiB)")
