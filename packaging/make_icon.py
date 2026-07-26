from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw


SIZES = {
    "icon_16x16.png": 16,
    "icon_16x16@2x.png": 32,
    "icon_32x32.png": 32,
    "icon_32x32@2x.png": 64,
    "icon_128x128.png": 128,
    "icon_128x128@2x.png": 256,
    "icon_256x256.png": 256,
    "icon_256x256@2x.png": 512,
    "icon_512x512.png": 512,
    "icon_512x512@2x.png": 1024,
}


def create_master_icon() -> Image.Image:
    size = 1024
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle(
        (72, 72, 952, 952),
        radius=220,
        fill=(19, 93, 69, 255),
    )
    draw.rounded_rectangle(
        (112, 112, 912, 912),
        radius=185,
        outline=(255, 255, 255, 28),
        width=6,
    )

    bar_color = (200, 234, 114, 255)
    bar_width = 118
    baseline = 754
    bars = [
        (246, baseline - 265, baseline),
        (453, baseline - 490, baseline),
        (660, baseline - 370, baseline),
    ]
    for x, top, bottom in bars:
        draw.rounded_rectangle(
            (x, top, x + bar_width, bottom),
            radius=58,
            fill=bar_color,
        )

    draw.ellipse((722, 196, 836, 310), fill=(255, 255, 255, 238))
    draw.line(
        [(752, 252), (782, 282), (825, 222)],
        fill=(19, 93, 69, 255),
        width=20,
        joint="curve",
    )
    return image


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: make_icon.py OUTPUT.icns")

    output = Path(sys.argv[1]).resolve()
    iconset = output.with_suffix(".iconset")
    iconset.mkdir(parents=True, exist_ok=True)

    master = create_master_icon()
    for name, size in SIZES.items():
        resized = master.resize((size, size), Image.Resampling.LANCZOS)
        resized.save(iconset / name, format="PNG")

    subprocess.run(
        ["/usr/bin/iconutil", "-c", "icns", str(iconset), "-o", str(output)],
        check=True,
    )


if __name__ == "__main__":
    main()
