"""Make 3x bigger PNG copies of raw_art with no blurring.

The gem is recoloured: one bright picture per XP value in data/game.json.
"""

import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "raw_art"
ASSETS_DIR = ROOT / "assets"
CONFIG_PATH = ROOT / "data" / "game.json"
SCALE = 3
GEM_COLOURS = (
    (90, 235, 255),
    (255, 95, 220),
    (255, 225, 80),
    (105, 255, 140),
    (255, 150, 70),
    (175, 135, 255),
)


def gem_xp_values(config_path=CONFIG_PATH):
    with open(config_path, encoding="utf-8") as file:
        config = json.load(file)
    return sorted(
        {
            int(stats["xp"])
            for stats in config["enemies"].values()
            if stats.get("xp", 0) > 0
        }
    )


def _is_edge(pixels, width, height, x, y):
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx, ny = x + dx, y + dy
        if nx < 0 or ny < 0 or nx >= width or ny >= height:
            return True
        if not pixels[nx, ny][3]:
            return True
    return False


def recolour_gem(image, colour):
    source = image.convert("RGBA")
    pixels = source.load()
    shades = []
    for y in range(source.height):
        for x in range(source.width):
            red, green, blue, alpha = pixels[x, y]
            if alpha:
                shades.append(red * 0.299 + green * 0.587 + blue * 0.114)
    low, high = min(shades), max(shades)
    span = high - low or 1.0
    edge = tuple(round(channel * 0.55) for channel in colour)
    highlight = tuple(round(channel + (255 - channel) * 0.75) for channel in colour)
    tinted = Image.new("RGBA", source.size, (0, 0, 0, 0))
    target = tinted.load()
    for y in range(source.height):
        for x in range(source.width):
            red, green, blue, alpha = pixels[x, y]
            if not alpha:
                continue
            shade = (red * 0.299 + green * 0.587 + blue * 0.114 - low) / span
            shade = min(1.0, max(0.0, shade))
            if _is_edge(pixels, source.width, source.height, x, y):
                rgb = edge
            else:
                rgb = [
                    colour[channel] + (highlight[channel] - colour[channel]) * shade
                    for channel in range(3)
                ]
            target[x, y] = (
                round(rgb[0]),
                round(rgb[1]),
                round(rgb[2]),
                alpha,
            )
    return tinted


def make_assets(raw_dir=RAW_DIR, assets_dir=ASSETS_DIR, scale=SCALE):
    assets_dir.mkdir(parents=True, exist_ok=True)
    made = []
    xp_values = gem_xp_values()
    for source in sorted(raw_dir.glob("*.png")):
        with Image.open(source) as image:
            width, height = image.size
            if source.stem == "gem":
                stale = assets_dir / "gem.png"
                if stale.exists():
                    stale.unlink()
                for xp in xp_values:
                    colour = GEM_COLOURS[(xp - 1) % len(GEM_COLOURS)]
                    tinted = recolour_gem(image, colour)
                    big = tinted.resize(
                        (width * scale, height * scale), Image.Resampling.NEAREST
                    )
                    name = f"gem_{xp}.png"
                    big.save(assets_dir / name, format="PNG")
                    made.append((name, (width, height), big.size))
                continue
            big = image.convert("RGBA").resize(
                (width * scale, height * scale), Image.Resampling.NEAREST
            )
            target = assets_dir / source.name
            big.save(target, format="PNG")
        made.append((source.name, (width, height), big.size))
    return made


if __name__ == "__main__":
    for name, old_size, new_size in make_assets():
        print(f"{name}: {old_size[0]}x{old_size[1]} -> {new_size[0]}x{new_size[1]}")
