"""Make 3x bigger PNG copies of raw_art with no blurring."""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "raw_art"
ASSETS_DIR = ROOT / "assets"
SCALE = 3


def make_assets(raw_dir=RAW_DIR, assets_dir=ASSETS_DIR, scale=SCALE):
    assets_dir.mkdir(parents=True, exist_ok=True)
    made = []
    for source in sorted(raw_dir.glob("*.png")):
        with Image.open(source) as image:
            width, height = image.size
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
