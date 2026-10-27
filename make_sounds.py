"""Make the game's short sounds with the Python standard library only."""

import math
import wave
from array import array
from pathlib import Path

RATE = 22050
SOUNDS_DIR = Path(__file__).resolve().parent / "sounds"


def _note(frequency, duration, volume, end_frequency=None, shape="sine"):
    count = max(1, int(RATE * duration))
    samples = array("h")
    phase = 0.0
    end = frequency if end_frequency is None else end_frequency
    for index in range(count):
        progress = index / (count - 1) if count > 1 else 1.0
        current = frequency + (end - frequency) * progress
        phase += math.tau * current / RATE
        wave_value = math.sin(phase)
        if shape == "square":
            wave_value = 1.0 if wave_value >= 0.0 else -1.0
        elif shape == "triangle":
            wave_value = 2.0 / math.pi * math.asin(wave_value)
        attack = min(1.0, progress / 0.08)
        release = min(1.0, (1.0 - progress) / 0.15)
        envelope = attack * release * (1.0 - 0.55 * progress)
        value = wave_value * envelope * volume
        samples.append(int(max(-1.0, min(1.0, value)) * 32767))
    return samples


def _chord(frequencies, duration, volume):
    count = max(1, int(RATE * duration))
    samples = array("h")
    phases = [0.0] * len(frequencies)
    for index in range(count):
        progress = index / (count - 1) if count > 1 else 1.0
        total = 0.0
        for position, frequency in enumerate(frequencies):
            phases[position] += math.tau * frequency / RATE
            total += math.sin(phases[position])
        attack = min(1.0, progress / 0.06)
        release = min(1.0, (1.0 - progress) / 0.2)
        envelope = attack * release * (1.0 - 0.6 * progress)
        value = total / len(frequencies) * envelope * volume
        samples.append(int(max(-1.0, min(1.0, value)) * 32767))
    return samples


def _join(*tracks):
    joined = array("h")
    for track in tracks:
        joined.extend(track)
    return joined


def _build():
    return {
        "hit": _note(880.0, 0.07, 0.30, end_frequency=320.0, shape="square"),
        "gem": _join(
            _note(880.0, 0.07, 0.24, shape="triangle"),
            _note(1318.5, 0.12, 0.24, shape="triangle"),
        ),
        "level_up": _join(
            _note(523.25, 0.10, 0.26),
            _note(659.25, 0.10, 0.26),
            _note(783.99, 0.10, 0.26),
            _note(1046.5, 0.24, 0.26),
        ),
        "hurt": _note(220.0, 0.20, 0.35, end_frequency=90.0, shape="square"),
        "end": _chord([392.0, 261.63, 523.25], 0.85, 0.26),
    }


def make_sounds(sounds_dir):
    target = Path(sounds_dir)
    target.mkdir(parents=True, exist_ok=True)
    results = []
    for name, samples in _build().items():
        path = target / f"{name}.wav"
        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(RATE)
            wav_file.writeframes(samples.tobytes())
        results.append((name, len(samples) / RATE, path))
    return results


if __name__ == "__main__":
    for name, duration, path in make_sounds(SOUNDS_DIR):
        print(f"{path.name}: {duration:.2f} s")
    print("Sounds saved in", SOUNDS_DIR)
