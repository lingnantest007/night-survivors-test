"""Run main.py's real event loop with fake mouse and finger events.

Usage: SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python tests/smoke_input.py
"""

import math
import os
import runpy
import sys
import threading
import time
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

import rules  # noqa: E402

ready = threading.Event()
result = {"world": None, "error": None}
played_sounds = []

RealSound = pygame.mixer.Sound


class RecordingSound:
    def __init__(self, path):
        self.name = Path(path).stem
        self.sound = RealSound(path)

    def set_volume(self, value):
        self.sound.set_volume(value)

    def play(self, *args, **kwargs):
        played_sounds.append(self.name)
        return self.sound.play(*args, **kwargs)


pygame.mixer.Sound = RecordingSound


class RecordingWorld(rules.World):
    def __init__(self, config, rng=None):
        self.pointers = []
        self.resets = 0
        super().__init__(config, rng)
        result["world"] = self
        ready.set()

    def set_pointer(self, x, y):
        self.pointers.append((x, y))
        super().set_pointer(x, y)

    def reset(self):
        self.resets += 1
        super().reset()


rules.World = RecordingWorld


def post(kind, **attrs):
    pygame.event.post(pygame.event.Event(kind, attrs))


def _fmt(point):
    return f"({point[0]:.1f}, {point[1]:.1f})"


def drive():
    try:
        if not ready.wait(10.0):
            result["error"] = "main.py did not start"
            return
        world = result["world"]
        time.sleep(0.5)

        mouse_start = world.hero.x
        post(pygame.MOUSEMOTION, pos=(350, 200), rel=(0, 0), buttons=(0, 0, 0))
        time.sleep(0.3)
        result["mouse_pointer"] = world.pointers[-1] if world.pointers else None
        result["mouse_moved"] = math.hypot(world.hero.x - mouse_start, world.hero.y)
        before = (world.hero.x, world.hero.y)
        time.sleep(0.3)
        result["kept_walking"] = math.hypot(
            world.hero.x - before[0], world.hero.y - before[1]
        ) > 1.0
        post(pygame.MOUSEBUTTONDOWN, pos=(350, 200), button=1)
        post(pygame.MOUSEBUTTONUP, pos=(350, 200), button=1)

        finger_start = (world.hero.x, world.hero.y)
        post(pygame.FINGERDOWN, x=0.25, y=0.75, finger_id=1, touch_id=1)
        time.sleep(0.3)
        result["finger_pointer"] = world.pointers[-1] if world.pointers else None
        post(pygame.FINGERMOTION, x=0.30, y=0.70, finger_id=1, touch_id=1)
        time.sleep(0.2)
        result["finger_moved"] = math.hypot(
            world.hero.x - finger_start[0], world.hero.y - finger_start[1]
        )
        post(pygame.FINGERUP, x=0.30, y=0.70, finger_id=1, touch_id=1)
        time.sleep(0.2)
        stop_position = (world.hero.x, world.hero.y)
        time.sleep(0.3)
        result["stopped_after_lift"] = (
            math.hypot(world.hero.x - stop_position[0], world.hero.y - stop_position[1]) < 0.01
        )
        result["pointer_after_lift"] = world.pointer

        post(pygame.KEYDOWN, key=pygame.K_p, mod=0, unicode="p", scancode=0)
        time.sleep(0.2)
        paused_at = world.time
        time.sleep(0.3)
        result["pause_freezes"] = world.paused and world.time == paused_at
        post(pygame.KEYDOWN, key=pygame.K_p, mod=0, unicode="p", scancode=0)
        time.sleep(0.1)
        result["unpaused"] = not world.paused

        world.gems.append(
            rules.Gem(world.hero.x, world.hero.y, world.xp_needed - world.xp)
        )
        time.sleep(0.2)
        result["level_up"] = (
            world.state == "level_up" and world.level == 2 and len(world.cards) == 3
        )
        level_before = world.level
        post(pygame.MOUSEBUTTONDOWN, pos=(195, 245), button=1)
        post(pygame.MOUSEBUTTONUP, pos=(195, 245), button=1)
        time.sleep(0.2)
        result["card_click"] = (
            world.state == "playing"
            and world.level == level_before
            and world.pending_levelups == 0
            and world.cards == []
        )

        world.gems.append(
            rules.Gem(world.hero.x, world.hero.y, world.xp_needed - world.xp)
        )
        time.sleep(0.2)
        second_cards = world.state == "level_up" and len(world.cards) == 3
        level_before = world.level
        post(pygame.FINGERDOWN, x=0.5, y=0.35, finger_id=4, touch_id=4)
        post(pygame.FINGERUP, x=0.5, y=0.35, finger_id=4, touch_id=4)
        time.sleep(0.2)
        result["card_tap"] = (
            second_cards
            and world.state == "playing"
            and world.level == level_before
            and world.pending_levelups == 0
        )

        world.hero.hp = 1.0
        stats = world.config["enemies"]["bat"]
        world.enemies.append(
            rules.Enemy(
                kind="bat",
                x=world.hero.x,
                y=world.hero.y,
                hp=1000.0,
                speed=0.0,
                damage=stats["damage"],
                xp=stats["xp"],
                radius=stats["radius"],
            )
        )
        time.sleep(0.2)
        result["game_over"] = world.state == "game_over"

        resets_before = world.resets
        post(pygame.MOUSEBUTTONDOWN, pos=(195, 350), button=1)
        post(pygame.MOUSEBUTTONUP, pos=(195, 350), button=1)
        time.sleep(0.2)
        result["restart"] = (
            world.resets == resets_before + 1
            and world.state == "playing"
            and world.hero.hp == world.hero.max_hp
            and world.time < 0.5
        )
        result["time_after_restart"] = world.time

        world.hero.hp = 1.0
        world.enemies.append(
            rules.Enemy(
                kind="bat",
                x=world.hero.x,
                y=world.hero.y,
                hp=1000.0,
                speed=0.0,
                damage=stats["damage"],
                xp=stats["xp"],
                radius=stats["radius"],
            )
        )
        time.sleep(0.2)
        result["second_game_over"] = world.state == "game_over"
        resets_before = world.resets
        post(pygame.FINGERDOWN, x=0.5, y=0.5, finger_id=2, touch_id=2)
        post(pygame.FINGERUP, x=0.5, y=0.5, finger_id=2, touch_id=2)
        time.sleep(0.2)
        result["tap_restart"] = (
            world.resets == resets_before + 1
            and world.state == "playing"
            and world.hero.hp == world.hero.max_hp
        )

        enemy_data = world.config["enemies"]
        world.hero.hp = world.hero.max_hp
        for kind, offset_x, offset_y in (
            ("slime", 150.0, 0.0),
            ("ghost", -150.0, 0.0),
            ("demon", 0.0, -160.0),
        ):
            data = enemy_data[kind]
            world.enemies.append(
                rules.Enemy(
                    kind=kind,
                    x=world.hero.x + offset_x,
                    y=world.hero.y + offset_y,
                    hp=data["hp"],
                    speed=0.0,
                    damage=data["damage"],
                    xp=data["xp"],
                    radius=data["radius"],
                )
            )
        time.sleep(0.25)
        result["special_enemies"] = (
            world.state == "playing"
            and {enemy.kind for enemy in world.enemies} >= {"slime", "ghost", "demon"}
        )

        world.hero.hp = world.hero.max_hp
        world.enemies.append(
            rules.Enemy(
                kind="bat",
                x=world.hero.x + 40.0,
                y=world.hero.y,
                hp=1000.0,
                speed=0.0,
                damage=stats["damage"],
                xp=stats["xp"],
                radius=stats["radius"],
            )
        )
        time.sleep(1.2)
        result["hit_sound"] = "hit" in played_sounds

        world.hero.hp = world.hero.max_hp
        world.time = world.config["game"]["victory_time"] - rules.STEP * 0.5
        time.sleep(0.25)
        result["victory"] = (
            world.state == "victory"
            and world.time == world.config["game"]["victory_time"]
            and world.pointer is None
        )
        resets_before = world.resets
        post(pygame.MOUSEBUTTONDOWN, pos=(195, 350), button=1)
        post(pygame.MOUSEBUTTONUP, pos=(195, 350), button=1)
        time.sleep(0.2)
        result["victory_restart"] = (
            world.resets == resets_before + 1
            and world.state == "playing"
            and world.time < 0.5
        )
    except Exception as error:  # noqa: BLE001
        result["error"] = repr(error)
    finally:
        try:
            post(pygame.QUIT)
        except pygame.error:
            pass


driver = threading.Thread(target=drive, daemon=True)
driver.start()
runpy.run_path(os.path.join(ROOT, "main.py"), run_name="__main__")
driver.join(timeout=5)

if result.get("error"):
    print("ERROR:", result["error"])
    raise SystemExit(1)

mouse_pointer = result.get("mouse_pointer")
finger_pointer = result.get("finger_pointer")
checks = {
    "mouse event moved the hero": result.get("mouse_moved", 0.0) > 1.0,
    "hero kept walking without new mouse events": result.get("kept_walking") is True,
    "mouse pointer became a world point": mouse_pointer is not None,
    "finger event moved the hero": result.get("finger_moved", 0.0) > 1.0,
    "finger pointer became a world point": finger_pointer is not None,
    "hero stopped after finger lift": result.get("stopped_after_lift") is True,
    "pointer is clear after finger lift": result.get("pointer_after_lift") is None,
    "P paused the game and froze time": result.get("pause_freezes") is True,
    "P unpaused the game": result.get("unpaused") is True,
    "gem opened LEVEL UP with three cards": result.get("level_up") is True,
    "mouse click on a card resumed the game": result.get("card_click") is True,
    "finger tap on a card resumed the game": result.get("card_tap") is True,
    "touching bat caused GAME OVER": result.get("game_over") is True,
    "click on end screen restarted": result.get("restart") is True,
    "tap on end screen restarted": result.get("tap_restart") is True,
    "slime, ghost and boss drew without errors": result.get("special_enemies") is True,
    "hit sound played when a spark hit": result.get("hit_sound") is True,
    "all five sounds played": set(played_sounds) >= {
        "hit",
        "gem",
        "level_up",
        "hurt",
        "end",
    },
    "reaching 2:00 shows VICTORY": result.get("victory") is True,
    "click on VICTORY restarted": result.get("victory_restart") is True,
}

print("mouse pointer -> world point:", _fmt(mouse_pointer) if mouse_pointer else None)
print("finger pointer -> world point:", _fmt(finger_pointer) if finger_pointer else None)
print(f"hero moved by mouse: {result.get('mouse_moved', 0.0):.2f} px")
print(f"hero moved by finger: {result.get('finger_moved', 0.0):.2f} px")
print(f"time after restart: {result.get('time_after_restart', 0.0):.3f} s")
print("sounds played:", ", ".join(sorted(set(played_sounds))))
for name, passed in checks.items():
    print(("PASS" if passed else "FAIL"), "-", name)
print("RESULT:", "ALL PASS" if all(checks.values()) else "SOME CHECKS FAILED")
raise SystemExit(0 if all(checks.values()) else 1)
