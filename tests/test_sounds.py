import array
import tempfile
import unittest
import wave
from pathlib import Path

import make_sounds

EXPECTED = ["hit", "gem", "level_up", "hurt", "end"]


class MakeSoundsTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.target = Path(self.folder.name)
        self.made = make_sounds.make_sounds(self.target)

    def test_makes_the_five_sounds(self):
        self.assertEqual([name for name, _, _ in self.made], EXPECTED)
        for name in EXPECTED:
            self.assertTrue((self.target / f"{name}.wav").is_file(), name)

    def test_files_are_short_mono_16_bit_22_khz(self):
        for name in EXPECTED:
            path = self.target / f"{name}.wav"
            with wave.open(str(path), "rb") as wav_file:
                self.assertEqual(wav_file.getnchannels(), 1, name)
                self.assertEqual(wav_file.getsampwidth(), 2, name)
                self.assertEqual(wav_file.getframerate(), make_sounds.RATE, name)
                duration = wav_file.getnframes() / wav_file.getframerate()
            self.assertGreater(duration, 0.05, name)
            self.assertLess(duration, 1.5, name)

    def test_every_sound_has_audible_samples(self):
        for name in EXPECTED:
            path = self.target / f"{name}.wav"
            with wave.open(str(path), "rb") as wav_file:
                samples = array.array("h")
                samples.frombytes(wav_file.readframes(wav_file.getnframes()))
            self.assertTrue(samples, name)
            peak = max(abs(value) for value in samples)
            self.assertGreater(peak, 3000, name)
            self.assertLess(peak, 32767, name)
            self.assertGreater(len(set(samples)), 100, name)


if __name__ == "__main__":
    unittest.main()
