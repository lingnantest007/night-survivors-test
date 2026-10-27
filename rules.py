"""Night Survivors game rules. This module never imports pygame."""

import json
import math
import random
from dataclasses import dataclass
from pathlib import Path

STEP = 1.0 / 60.0
CONFIG_PATH = Path(__file__).resolve().parent / "data" / "game.json"


def load_config(path=None):
    with open(path or CONFIG_PATH, encoding="utf-8") as file:
        return json.load(file)


@dataclass
class Hero:
    x: float
    y: float
    hp: float
    max_hp: float
    speed: float
    hit_radius: float
    magnet_radius: float


@dataclass
class Enemy:
    kind: str
    x: float
    y: float
    hp: float
    speed: float
    damage: float
    xp: int
    radius: float
    cooldown: float = 0.0


@dataclass
class Spark:
    x: float
    y: float
    vx: float
    vy: float
    damage: float
    life: float


@dataclass
class Gem:
    x: float
    y: float
    xp: int


@dataclass
class Card:
    kind: str
    key: str
    name: str
    level: int | None
    text: str


class World:
    def __init__(self, config, rng=None):
        self.config = config
        self.rng = rng or random.Random()
        self.reset()

    def reset(self):
        hero_data = self.config["hero"]
        progress = self.config["progress"]
        self.time = 0.0
        self.state = "playing"
        self.paused = False
        self.kills = 0
        self.pointer = None
        self.hero = Hero(
            x=0.0,
            y=0.0,
            hp=hero_data["hp"],
            max_hp=hero_data["hp"],
            speed=hero_data["speed"],
            hit_radius=hero_data["hit_radius"],
            magnet_radius=hero_data["magnet_radius"],
        )
        self.enemies = []
        self.sparks = []
        self.gems = []
        self.boss_spawned = False
        self.boss_kind = self._boss_kind()
        self.spawn_timer = self.config["spawning"]["interval"]
        self.fire_timer = 0.0
        self.weapon_levels = {"spark_wand": 1}
        self.passive_levels = {}
        self.blade_timers = []
        self.ring_timer = 0.0
        self.level = 1
        self.xp = 0
        self.xp_needed = progress["xp_first_level"]
        self.pending_levelups = 0
        self.cards = []
        self.events = []

    def set_pointer(self, x, y):
        self.pointer = (x, y)

    def clear_pointer(self):
        self.pointer = None

    def update(self):
        if self.state != "playing" or self.paused:
            return
        self.time += STEP
        victory_time = self.config["game"]["victory_time"]
        if self.time >= victory_time:
            self.time = victory_time
            self.state = "victory"
            self.pointer = None
            self.cards = []
            self.events.append(("end",))
            return
        self._move_hero()
        self._update_weapons()
        self._update_sparks()
        self._remove_dead()
        self._update_gems()
        self._update_enemies()
        self._return_boss()
        self._cull_enemies()
        self._spawn()
        if self.hero.hp <= 0:
            self.hero.hp = 0.0
            self.state = "game_over"
            self.pointer = None
            self.cards = []
            self.events.append(("end",))
        elif self.pending_levelups > 0:
            self._open_level_up()

    def _move_hero(self):
        if self.pointer is None:
            return
        target_x, target_y = self.pointer
        dx = target_x - self.hero.x
        dy = target_y - self.hero.y
        distance = math.hypot(dx, dy)
        if distance <= self.config["hero"]["pointer_stop_distance"]:
            return
        step = min(self.hero.speed * STEP, distance)
        self.hero.x += dx / distance * step
        self.hero.y += dy / distance * step

    def _update_weapons(self):
        if "spark_wand" in self.weapon_levels:
            self._update_spark()
        if "spin_blades" in self.weapon_levels:
            self._update_blades()
        if "holy_ring" in self.weapon_levels:
            self._update_ring()

    def _spark_stats(self, level):
        weapon = self.config["weapons"]["spark_wand"]
        extra = weapon["per_level"]
        damage = weapon["level1"]["damage"] + extra["damage"] * (level - 1)
        cooldown = weapon["level1"]["cooldown"] - extra["cooldown"] * (level - 1)
        sparks = weapon["level1"]["sparks"] + sum(
            1 for extra_level in extra["extra_spark_at"] if level >= extra_level
        )
        return damage, cooldown, sparks

    def _update_spark(self):
        weapon = self.config["weapons"]["spark_wand"]
        level = self.weapon_levels["spark_wand"]
        damage, cooldown, count = self._spark_stats(level)
        self.fire_timer -= STEP
        if self.fire_timer > 0 or not self.enemies:
            return
        target = min(
            self.enemies,
            key=lambda enemy: (enemy.x - self.hero.x) ** 2 + (enemy.y - self.hero.y) ** 2,
        )
        dx = target.x - self.hero.x
        dy = target.y - self.hero.y
        distance = math.hypot(dx, dy)
        if distance == 0:
            dx, dy, distance = 1.0, 0.0, 1.0
        speed = weapon["speed"]
        for _ in range(count):
            self.sparks.append(
                Spark(
                    x=self.hero.x,
                    y=self.hero.y,
                    vx=dx / distance * speed,
                    vy=dy / distance * speed,
                    damage=damage,
                    life=weapon["spark_lifetime"],
                )
            )
        self.fire_timer = cooldown

    def _damage_enemy(self, enemy, amount):
        enemy.hp -= amount
        self.events.append(("damage", enemy.x, enemy.y, amount))

    def _update_sparks(self):
        weapon = self.config["weapons"]["spark_wand"]
        reach = weapon["spark_radius"]
        alive = []
        for spark in self.sparks:
            spark.life -= STEP
            if spark.life <= 0:
                continue
            spark.x += spark.vx * STEP
            spark.y += spark.vy * STEP
            target = None
            for enemy in self.enemies:
                if enemy.hp <= 0:
                    continue
                if math.hypot(enemy.x - spark.x, enemy.y - spark.y) <= enemy.radius + reach:
                    target = enemy
                    break
            if target is None:
                alive.append(spark)
            else:
                self._damage_enemy(target, spark.damage)
        self.sparks = alive

    def _blade_count(self, level):
        weapon = self.config["weapons"]["spin_blades"]
        return weapon["level1"]["blades"] + sum(
            1 for extra_level in weapon["per_level"]["extra_blade_at"] if level >= extra_level
        )

    def blade_positions(self):
        if "spin_blades" not in self.weapon_levels:
            return []
        weapon = self.config["weapons"]["spin_blades"]
        level = self.weapon_levels["spin_blades"]
        count = self._blade_count(level)
        positions = []
        for index in range(count):
            angle = (
                math.tau * self.time / weapon["turn_time"]
                + math.tau * index / count
            )
            positions.append(
                (
                    self.hero.x + math.cos(angle) * weapon["orbit_radius"],
                    self.hero.y + math.sin(angle) * weapon["orbit_radius"],
                )
            )
        return positions

    def _update_blades(self):
        weapon = self.config["weapons"]["spin_blades"]
        level = self.weapon_levels["spin_blades"]
        damage = weapon["level1"]["damage"] + weapon["per_level"]["damage"] * (level - 1)
        count = self._blade_count(level)
        while len(self.blade_timers) < count:
            self.blade_timers.append(0.0)
        for index in range(count):
            self.blade_timers[index] = max(0.0, self.blade_timers[index] - STEP)
        reach = weapon["blade_radius"]
        for index, (x, y) in enumerate(self.blade_positions()):
            if self.blade_timers[index] > 0:
                continue
            hit = False
            for enemy in self.enemies:
                if enemy.hp <= 0:
                    continue
                if math.hypot(enemy.x - x, enemy.y - y) <= enemy.radius + reach:
                    self._damage_enemy(enemy, damage)
                    hit = True
            if hit:
                self.blade_timers[index] = weapon["hit_cooldown"]

    def ring_radius(self):
        if "holy_ring" not in self.weapon_levels:
            return None
        weapon = self.config["weapons"]["holy_ring"]
        level = self.weapon_levels["holy_ring"]
        return weapon["level1"]["radius"] + weapon["per_level"]["radius"] * (level - 1)

    def _update_ring(self):
        weapon = self.config["weapons"]["holy_ring"]
        level = self.weapon_levels["holy_ring"]
        damage = weapon["level1"]["damage"] + weapon["per_level"]["damage"] * (level - 1)
        radius = self.ring_radius()
        self.ring_timer = max(0.0, self.ring_timer - STEP)
        if self.ring_timer > 0:
            return
        self.ring_timer = weapon["cooldown"]
        for enemy in self.enemies:
            if enemy.hp <= 0:
                continue
            if math.hypot(enemy.x - self.hero.x, enemy.y - self.hero.y) <= radius:
                self._damage_enemy(enemy, damage)

    def _remove_dead(self):
        alive = []
        for enemy in self.enemies:
            if enemy.hp <= 0:
                self.kills += 1
                self.events.append(("death", enemy.x, enemy.y, enemy.radius))
                if enemy.xp > 0:
                    self.gems.append(Gem(enemy.x, enemy.y, enemy.xp))
            else:
                alive.append(enemy)
        self.enemies = alive

    def _update_gems(self):
        speed = self.config["progress"]["gem_speed"]
        remaining = []
        for gem in self.gems:
            dx = self.hero.x - gem.x
            dy = self.hero.y - gem.y
            distance = math.hypot(dx, dy)
            if distance <= self.hero.magnet_radius:
                step = min(speed * STEP, distance)
                if distance > 0:
                    gem.x += dx / distance * step
                    gem.y += dy / distance * step
                distance = math.hypot(self.hero.x - gem.x, self.hero.y - gem.y)
            if distance <= self.hero.hit_radius:
                self._gain_xp(gem.xp)
                self.events.append(("gem",))
            else:
                remaining.append(gem)
        self.gems = remaining

    def _gain_xp(self, amount):
        self.xp += amount
        increase = self.config["progress"]["xp_increase"]
        while self.xp >= self.xp_needed:
            self.xp -= self.xp_needed
            self.level += 1
            self.xp_needed += increase
            self.pending_levelups += 1

    def _open_level_up(self):
        if self.pending_levelups <= 0 or self.state != "playing":
            return
        self.state = "level_up"
        self.pointer = None
        self.cards = self._offer_cards()
        self.events.append(("level_up",))

    def _weapon_card(self, key, new_level):
        data = self.config["weapons"][key]
        if key == "spark_wand":
            if new_level == 1:
                text = (
                    f"{data['level1']['damage']:g} dmg, every "
                    f"{data['level1']['cooldown']:.2f} s, "
                    f"{data['level1']['sparks']} spark"
                )
            else:
                text = (
                    f"+{data['per_level']['damage']:g} dmg, "
                    f"{data['per_level']['cooldown']:g} s faster"
                )
                if new_level in data["per_level"]["extra_spark_at"]:
                    text += ", +1 spark"
        elif key == "spin_blades":
            if new_level == 1:
                text = (
                    f"{data['level1']['blades']} blades, {data['level1']['damage']:g} dmg, "
                    f"{data['orbit_radius']:g} px circle"
                )
            else:
                text = f"+{data['per_level']['damage']:g} dmg"
                if new_level in data["per_level"]["extra_blade_at"]:
                    text += ", +1 blade"
        else:
            if new_level == 1:
                text = (
                    f"{data['level1']['damage']:g} dmg, {data['level1']['radius']:g} px, "
                    f"every {data['cooldown']:g} s"
                )
            else:
                text = f"+{data['per_level']['damage']:g} dmg, +{data['per_level']['radius']:g} px"
        return Card("weapon", key, data["name"], new_level, text)

    def _passive_card(self, key, new_level):
        data = self.config["passives"][key]
        if key == "swift_boots":
            text = f"+{data['speed_percent']:g}% walking speed"
        elif key == "big_heart":
            text = f"+{data['max_hp']:g} max HP and heal {data['heal']:g}"
        else:
            text = f"+{data['magnet_radius']:g} px gem magnet"
        return Card("passive", key, data["name"], new_level, text)

    def _heal_card(self):
        amount = self.config["progress"]["heal_amount"]
        return Card("heal", "heal", f"Heal {amount:g} HP", None, "Restore your health")

    def _offer_cards(self):
        progress = self.config["progress"]
        max_level = progress["item_max_level"]
        count = progress["cards_per_level_up"]
        weapons = {
            key: data
            for key, data in self.config["weapons"].items()
            if isinstance(data, dict)
        }
        options = []
        if len(self.weapon_levels) < self.config["weapons"]["max_weapons"]:
            for key in weapons:
                if key not in self.weapon_levels:
                    options.append(self._weapon_card(key, 1))
        for key, level in self.weapon_levels.items():
            if level < max_level:
                options.append(self._weapon_card(key, level + 1))
        for key, level in self.passive_levels.items():
            if level < max_level:
                options.append(self._passive_card(key, level + 1))
        for key in self.config["passives"]:
            if key not in self.passive_levels and 0 < max_level:
                options.append(self._passive_card(key, 1))
        if len(options) >= count:
            return self.rng.sample(options, count)
        cards = list(options)
        while len(cards) < count:
            cards.append(self._heal_card())
        self.rng.shuffle(cards)
        return cards

    def choose_card(self, index):
        if self.state != "level_up" or not 0 <= index < len(self.cards):
            return False
        card = self.cards[index]
        self._apply_card(card)
        self.pending_levelups = max(0, self.pending_levelups - 1)
        if self.pending_levelups > 0:
            self.cards = self._offer_cards()
        else:
            self.cards = []
            self.state = "playing"
            self.pointer = None
        return True

    def _apply_card(self, card):
        progress = self.config["progress"]
        if card.kind == "heal":
            self.hero.hp = min(self.hero.max_hp, self.hero.hp + progress["heal_amount"])
            return
        if card.kind == "weapon":
            self.weapon_levels[card.key] = card.level
            if card.key == "holy_ring":
                self.ring_timer = 0.0
            return
        data = self.config["passives"][card.key]
        self.passive_levels[card.key] = card.level
        if card.key == "swift_boots":
            self.hero.speed = self.config["hero"]["speed"] * (
                1 + data["speed_percent"] / 100 * card.level
            )
        elif card.key == "big_heart":
            self.hero.max_hp = self.config["hero"]["hp"] + data["max_hp"] * card.level
            self.hero.hp = min(self.hero.max_hp, self.hero.hp + data["heal"])
        elif card.key == "magnet":
            self.hero.magnet_radius = (
                self.config["hero"]["magnet_radius"] + data["magnet_radius"] * card.level
            )

    def loadout_entries(self):
        entries = []
        for key, level in self.weapon_levels.items():
            entries.append((self.config["weapons"][key]["short"], level))
        for key, level in self.passive_levels.items():
            entries.append((self.config["passives"][key]["short"], level))
        return entries

    def _update_enemies(self):
        contact_cooldown = self.config["contact"]["hurt_cooldown"]
        for enemy in self.enemies:
            dx = self.hero.x - enemy.x
            dy = self.hero.y - enemy.y
            distance = math.hypot(dx, dy)
            if distance > 0:
                enemy.x += dx / distance * enemy.speed * STEP
                enemy.y += dy / distance * enemy.speed * STEP
            if enemy.cooldown > 0:
                enemy.cooldown = max(0.0, enemy.cooldown - STEP)
            distance = math.hypot(self.hero.x - enemy.x, self.hero.y - enemy.y)
            if distance <= self.hero.hit_radius + enemy.radius and enemy.cooldown <= 0:
                self.hero.hp -= enemy.damage
                enemy.cooldown = contact_cooldown
                self.events.append(("hurt",))

    def _cull_enemies(self):
        limit = self.config["spawning"]["cull_radius"]
        self.enemies = [
            enemy
            for enemy in self.enemies
            if enemy.kind == self.boss_kind
            or math.hypot(enemy.x - self.hero.x, enemy.y - self.hero.y) <= limit
        ]

    def _return_boss(self):
        if self.boss_kind is None:
            return
        spawning = self.config["spawning"]
        for enemy in self.enemies:
            if enemy.kind != self.boss_kind:
                continue
            distance = math.hypot(enemy.x - self.hero.x, enemy.y - self.hero.y)
            if distance > spawning["boss_return_radius"]:
                angle = self.rng.uniform(0.0, math.tau)
                enemy.x = self.hero.x + math.cos(angle) * spawning["ring_radius"]
                enemy.y = self.hero.y + math.sin(angle) * spawning["ring_radius"]

    def _current_wave(self):
        wave = self.config["spawning"]["waves"][0]
        for candidate in self.config["spawning"]["waves"]:
            if self.time + 1e-9 >= candidate["from"]:
                wave = candidate
        return wave

    def _enemy_kind(self, name):
        for key, data in self.config["enemies"].items():
            if isinstance(data, dict) and data.get("name") == name:
                return key
        return name.lower()

    def _boss_kind(self):
        for wave in self.config["spawning"]["waves"]:
            if "boss" in wave:
                return self._enemy_kind(wave["boss"])
        return None

    def _make_enemy(self, kind, x, y):
        stats = self.config["enemies"][kind]
        return Enemy(
            kind=kind,
            x=x,
            y=y,
            hp=stats["hp"],
            speed=stats["speed"],
            damage=stats["damage"],
            xp=stats["xp"],
            radius=stats["radius"],
        )

    def _spawn(self):
        self.spawn_timer -= STEP
        if self.spawn_timer > 1e-9:
            return
        self.spawn_timer += self.config["spawning"]["interval"]
        self._spawn_wave()

    def _maybe_spawn_boss(self):
        if self.boss_spawned or self.boss_kind is None:
            return
        spawning = self.config["spawning"]
        boss_wave = next(
            (wave for wave in spawning["waves"] if "boss" in wave), None
        )
        if boss_wave is None or self.time + 1e-9 < boss_wave["from"]:
            return
        if len(self.enemies) >= spawning["max_alive"]:
            return
        angle = self.rng.uniform(0.0, math.tau)
        self.enemies.append(
            self._make_enemy(
                self.boss_kind,
                self.hero.x + math.cos(angle) * spawning["ring_radius"],
                self.hero.y + math.sin(angle) * spawning["ring_radius"],
            )
        )
        self.boss_spawned = True

    def _spawn_wave(self):
        spawning = self.config["spawning"]
        self._maybe_spawn_boss()
        wave = self._current_wave()
        per_tick = max(1, round(spawning["max_per_second"] * spawning["interval"]))
        room = min(
            wave["minimum"] - len(self.enemies),
            per_tick,
            spawning["max_alive"] - len(self.enemies),
        )
        if room <= 0:
            return
        for _ in range(int(room)):
            kind = self._enemy_kind(self.rng.choice(wave["types"]))
            angle = self.rng.uniform(0.0, math.tau)
            self.enemies.append(
                self._make_enemy(
                    kind,
                    self.hero.x + math.cos(angle) * spawning["ring_radius"],
                    self.hero.y + math.sin(angle) * spawning["ring_radius"],
                )
            )
