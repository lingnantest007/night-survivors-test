import tempfile
import unittest
from pathlib import Path

from PIL import Image

import make_assets


class MakeAssetsTests(unittest.TestCase):
    def test_every_png_becomes_three_times_bigger(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)
            made = make_assets.make_assets(assets_dir=target, scale=3)
            sources = sorted(make_assets.RAW_DIR.glob("*.png"))
            self.assertEqual(len(made), len(sources))
            for source in sources:
                with Image.open(source) as small, Image.open(target / source.name) as big:
                    self.assertEqual(big.size, (small.width * 3, small.height * 3))

    def test_nearest_neighbour_keeps_crisp_three_by_three_blocks(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)
            make_assets.make_assets(assets_dir=target, scale=3)
            with Image.open(make_assets.RAW_DIR / "hero.png") as image:
                small = image.convert("RGBA")
            with Image.open(target / "hero.png") as image:
                big = image.convert("RGBA")
            for y in range(small.height):
                for x in range(small.width):
                    colour = small.getpixel((x, y))
                    for dy in range(3):
                        for dx in range(3):
                            self.assertEqual(big.getpixel((x * 3 + dx, y * 3 + dy)), colour)

    def test_transparent_pixels_stay_transparent(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)
            make_assets.make_assets(assets_dir=target, scale=3)
            with Image.open(target / "bat.png") as image:
                self.assertEqual(image.convert("RGBA").getpixel((0, 0))[3], 0)


if __name__ == "__main__":
    unittest.main()
