import math
import tempfile
import unittest
from pathlib import Path

from PIL import Image

import make_assets


def average_colour(image):
    image = image.convert("RGBA")
    pixels = image.load()
    total = [0, 0, 0]
    count = 0
    for y in range(image.height):
        for x in range(image.width):
            red, green, blue, alpha = pixels[x, y]
            if alpha:
                total[0] += red
                total[1] += green
                total[2] += blue
                count += 1
    return tuple(channel / count for channel in total)


class MakeAssetsTests(unittest.TestCase):
    def test_every_picture_becomes_three_times_bigger(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)
            made = make_assets.make_assets(assets_dir=target, scale=3)
            names = {name for name, _old, _new in made}
            sources = sorted(make_assets.RAW_DIR.glob("*.png"))
            for source in sources:
                if source.stem == "gem":
                    continue
                with Image.open(source) as small, Image.open(target / source.name) as big:
                    self.assertEqual(big.size, (small.width * 3, small.height * 3))
                self.assertIn(source.name, names)
            self.assertNotIn("gem.png", names)

    def test_one_bright_gem_picture_per_xp_value(self):
        xp_values = make_assets.gem_xp_values()
        self.assertTrue(xp_values)
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)
            make_assets.make_assets(assets_dir=target, scale=3)
            with Image.open(make_assets.RAW_DIR / "gem.png") as small:
                expected_size = (small.width * 3, small.height * 3)
            for xp in xp_values:
                path = target / f"gem_{xp}.png"
                self.assertTrue(path.is_file(), path)
                with Image.open(path) as image:
                    self.assertEqual(image.size, expected_size)
                    rgba = image.convert("RGBA")
                    pixels = rgba.load()
                    alphas = [
                        pixels[x, y][3]
                        for y in range(rgba.height)
                        for x in range(rgba.width)
                    ]
                    self.assertIn(0, alphas)

    def test_gem_colours_are_bright_and_different(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)
            make_assets.make_assets(assets_dir=target, scale=3)
            colours = []
            for xp in make_assets.gem_xp_values():
                with Image.open(target / f"gem_{xp}.png") as image:
                    colour = average_colour(image)
                brightness = 0.299 * colour[0] + 0.587 * colour[1] + 0.114 * colour[2]
                self.assertGreater(brightness, 130, (xp, colour))
                colours.append(colour)
            for index, first in enumerate(colours):
                for second in colours[index + 1 :]:
                    distance = math.dist(first, second)
                    self.assertGreater(distance, 100, (first, second))

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

    def test_raw_art_is_not_changed(self):
        before = {
            path.name: path.read_bytes()
            for path in sorted(make_assets.RAW_DIR.glob("*.png"))
        }
        with tempfile.TemporaryDirectory() as folder:
            make_assets.make_assets(assets_dir=Path(folder), scale=3)
        after = {
            path.name: path.read_bytes()
            for path in sorted(make_assets.RAW_DIR.glob("*.png"))
        }
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
