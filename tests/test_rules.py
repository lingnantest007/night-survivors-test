import copy
import math
import random
import unittest
from pathlib import Path

import rules

ROOT = Path(__file__).resolve().parent.parent


def make_world(config=None, seed=1234):
    return rules.World(config or rules.load_config(), rng=random.Random(seed))


def add_bat(world, x, y, hp=None, speed=None):
    stats = world.config["enemies"]["bat"]
    world.enemies.append(
        rules.Enemy(
            kind="bat",
            x=x,
            y=y,
            hp=stats["hp"] if hp is None else hp,
            speed=stats["speed"] if speed is None else speed,
            damage=stats["damage"],
            xp=stats["xp"],
            radius=stats["radius"],
        )
    )
    return world.enemies[-1]


class ConfigTests(unittest.TestCase):
    def test_design_numbers_are_in_data(self):
        config = rules.load_config()
        for key in ("width", "height", "fps"):
            self.assertGreater(config["screen"][key], 0, key)
        self.assertGreater(config["game"]["victory_time"], 0)
        for key in ("speed", "hp", "hit_radius", "magnet_radius", "pointer_stop_distance"):
            self.assertGreater(config["hero"][key], 0, key)

        weapons = config["weapons"]
        self.assertGreater(weapons["max_weapons"], 0)
        for key, data in weapons.items():
            if not isinstance(data, dict):
                continue
            self.assertTrue(data["name"])
            self.assertTrue(data["short"])
            self.assertGreater(data["level1"]["damage"], 0, key)
            self.assertIn("per_level", data)
        spark = weapons["spark_wand"]
        for key in ("speed", "spark_radius", "spark_lifetime"):
            self.assertGreater(spark[key], 0, key)
        blades = weapons["spin_blades"]
        for key in ("orbit_radius", "turn_time", "hit_cooldown", "blade_radius"):
            self.assertGreater(blades[key], 0, key)
        self.assertGreater(blades["level1"]["blades"], 0)
        self.assertGreater(weapons["holy_ring"]["cooldown"], 0)
        self.assertGreater(weapons["holy_ring"]["level1"]["radius"], 0)

        for key, data in config["passives"].items():
            self.assertTrue(data["name"], key)
            self.assertTrue(data["short"], key)
            self.assertGreater(
                data.get("speed_percent", data.get("max_hp", data.get("magnet_radius"))),
                0,
                key,
            )

        for kind, stats in config["enemies"].items():
            self.assertTrue(stats["name"], kind)
            self.assertGreater(stats["hp"], 0, kind)
            self.assertGreater(stats["speed"], 0, kind)
            self.assertGreater(stats["damage"], 0, kind)
            self.assertGreaterEqual(stats["xp"], 0, kind)
            self.assertGreater(stats["radius"], 0, kind)
            self.assertTrue((ROOT / "raw_art" / stats["picture"]).is_file(), kind)
            if "draw_scale" in stats:
                self.assertGreater(stats["draw_scale"], 0, kind)

        self.assertGreater(config["contact"]["hurt_cooldown"], 0)

        spawning = config["spawning"]
        for key in ("interval", "max_per_second", "ring_radius", "max_alive"):
            self.assertGreater(spawning[key], 0, key)
        self.assertGreater(spawning["cull_radius"], spawning["ring_radius"])
        self.assertGreater(spawning["boss_return_radius"], 0)
        waves = spawning["waves"]
        self.assertTrue(waves)
        self.assertEqual([wave["from"] for wave in waves], sorted(wave["from"] for wave in waves))

        progress = config["progress"]
        for key in ("item_max_level", "cards_per_level_up", "xp_first_level", "gem_speed", "heal_amount"):
            self.assertGreater(progress[key], 0, key)
        self.assertGreaterEqual(progress["xp_increase"], 0)

    def test_wave_table_changes_over_time(self):
        world = make_world()
        waves = world.config["spawning"]["waves"]
        for index, wave in enumerate(waves):
            world.time = wave["from"]
            current = world._current_wave()
            self.assertEqual(current["minimum"], wave["minimum"])
            self.assertEqual(current["types"], wave["types"])
            if index + 1 < len(waves):
                world.time = waves[index + 1]["from"] - rules.STEP
                self.assertIs(world._current_wave(), wave)


class TimeAndMovementTests(unittest.TestCase):
    def test_time_step_is_one_sixtieth(self):
        world = make_world()
        world.update()
        self.assertAlmostEqual(world.time, 1.0 / 60.0)

    def test_hero_walks_toward_pointer_at_speed(self):
        world = make_world()
        world.set_pointer(100.0, 0.0)
        world.update()
        self.assertAlmostEqual(
            world.hero.x, world.config["hero"]["speed"] * rules.STEP
        )
        self.assertAlmostEqual(world.hero.y, 0.0)

    def test_hero_stops_at_the_stop_distance(self):
        world = make_world()
        stop = world.config["hero"]["pointer_stop_distance"]
        step = world.config["hero"]["speed"] * rules.STEP
        target = stop + step * 10
        world.set_pointer(target, 0.0)
        for _ in range(12):
            world.update()
        self.assertAlmostEqual(world.hero.x, target - stop, places=6)
        self.assertAlmostEqual(target - world.hero.x, stop, places=6)
        self.assertAlmostEqual(world.hero.y, 0.0, places=6)

    def test_pointer_inside_stop_distance_does_not_move(self):
        world = make_world()
        world.set_pointer(world.config["hero"]["pointer_stop_distance"], 0.0)
        for _ in range(10):
            world.update()
        self.assertEqual(world.hero.x, 0.0)
        self.assertEqual(world.hero.y, 0.0)

    def test_lifting_pointer_stops_hero(self):
        world = make_world()
        world.set_pointer(100.0, 0.0)
        world.update()
        moved = world.hero.x
        world.clear_pointer()
        for _ in range(10):
            world.update()
        self.assertEqual(world.hero.x, moved)

    def test_pause_freezes_time_and_enemies(self):
        world = make_world()
        world.paused = True
        for _ in range(120):
            world.update()
        self.assertEqual(world.time, 0.0)
        self.assertEqual(world.enemies, [])
        world.paused = False
        world.update()
        self.assertAlmostEqual(world.time, 1.0 / 60.0)


class SpawnTests(unittest.TestCase):
    def test_spawning_starts_after_one_interval(self):
        world = make_world()
        spawning = world.config["spawning"]
        frames = round(spawning["interval"] / rules.STEP)
        for _ in range(frames - 1):
            world.update()
        self.assertEqual(len(world.enemies), 0)
        world.update()
        per_tick = max(1, round(spawning["max_per_second"] * spawning["interval"]))
        self.assertEqual(len(world.enemies), per_tick)
        allowed = {
            world._enemy_kind(name) for name in world._current_wave()["types"]
        }
        self.assertTrue(all(enemy.kind in allowed for enemy in world.enemies))

    def test_new_enemies_appear_on_the_spawn_ring(self):
        world = make_world()
        spawning = world.config["spawning"]
        frames = round(spawning["interval"] / rules.STEP)
        for _ in range(frames):
            world.update()
        radius = spawning["ring_radius"]
        for enemy in world.enemies:
            distance = math.hypot(enemy.x - world.hero.x, enemy.y - world.hero.y)
            self.assertAlmostEqual(distance, radius, places=6)

    def test_new_enemies_per_tick_come_from_the_data(self):
        world = make_world()
        spawning = world.config["spawning"]
        wave = spawning["waves"][1] if len(spawning["waves"]) > 1 else spawning["waves"][0]
        world.time = wave["from"]
        world.spawn_timer = 0.0
        world.update()
        per_tick = max(1, round(spawning["max_per_second"] * spawning["interval"]))
        self.assertEqual(len(world.enemies), per_tick)
        for _ in range(round(spawning["interval"] / rules.STEP)):
            world.update()
        self.assertLessEqual(len(world.enemies), wave["minimum"])
        self.assertLessEqual(len(world.enemies), per_tick * 2)

    def test_never_more_than_max_alive_enemies(self):
        config = copy.deepcopy(rules.load_config())
        limit = config["spawning"]["max_alive"]
        per_tick = max(
            1,
            round(config["spawning"]["max_per_second"] * config["spawning"]["interval"]),
        )
        config["spawning"]["waves"][0]["minimum"] = limit + per_tick
        world = rules.World(config, rng=random.Random(7))
        for _ in range(limit // per_tick + 2):
            world._spawn_wave()
        self.assertEqual(len(world.enemies), limit)

    def test_bat_moves_toward_hero(self):
        world = make_world()
        stats = world.config["enemies"]["bat"]
        add_bat(world, 100.0, 0.0)
        world.update()
        self.assertAlmostEqual(world.hero.hp, world.hero.max_hp)
        self.assertAlmostEqual(
            world.enemies[0].x, 100.0 - stats["speed"] * rules.STEP
        )

    def test_enemies_beyond_the_cull_radius_are_removed(self):
        world = make_world()
        cull = world.config["spawning"]["cull_radius"]
        add_bat(world, cull + 100.0, 0.0, speed=0.0)
        add_bat(world, cull - 100.0, 0.0, speed=0.0)
        world.update()
        self.assertEqual(len(world.enemies), 1)
        self.assertAlmostEqual(world.enemies[0].x, cull - 100.0)


class DamageTests(unittest.TestCase):
    def test_bat_touching_hero_hurts_once_per_contact_cooldown(self):
        world = make_world()
        stats = world.config["enemies"]["bat"]
        cooldown = world.config["contact"]["hurt_cooldown"]
        world.spawn_timer = 10**9
        add_bat(world, 0.0, 0.0, hp=1000.0)
        world.update()
        first_hp = world.hero.max_hp - stats["damage"]
        self.assertAlmostEqual(world.hero.hp, first_hp)
        self.assertAlmostEqual(world.enemies[0].cooldown, cooldown)
        frames = 0
        limit = round(cooldown / rules.STEP) + 10
        while world.hero.hp == first_hp and frames < limit:
            world.update()
            frames += 1
        self.assertAlmostEqual(world.hero.hp, first_hp - stats["damage"])
        self.assertAlmostEqual(frames * rules.STEP, cooldown, delta=rules.STEP * 2)

    def test_two_bats_each_hurt_the_hero(self):
        world = make_world()
        damage = world.config["enemies"]["bat"]["damage"]
        add_bat(world, 0.0, 0.0, hp=1000.0)
        add_bat(world, 0.0, 0.0, hp=1000.0)
        world.update()
        self.assertAlmostEqual(world.hero.hp, world.hero.max_hp - 2 * damage)

    def test_game_over_and_play_again(self):
        world = make_world()
        damage = world.config["enemies"]["bat"]["damage"]
        add_bat(world, 0.0, 0.0, hp=1000.0)
        world.hero.hp = damage
        world.update()
        self.assertEqual(world.state, "game_over")
        self.assertEqual(world.hero.hp, 0.0)
        frozen = world.time
        world.update()
        self.assertEqual(world.time, frozen)
        world.reset()
        self.assertEqual(world.state, "playing")
        self.assertEqual(world.hero.hp, world.config["hero"]["hp"])
        self.assertEqual(world.time, 0.0)
        self.assertEqual(world.enemies, [])
        self.assertEqual(world.sparks, [])
        self.assertEqual(world.kills, 0)
        self.assertIsNone(world.pointer)


class SparkWandTests(unittest.TestCase):
    def test_spark_hits_nearest_enemy_and_kills_it(self):
        world = make_world()
        world.spawn_timer = 10**9
        add_bat(world, 100.0, 0.0)
        world.update()
        self.assertEqual(len(world.sparks), 1)
        self.assertGreater(world.sparks[0].vx, 0.0)
        limit = round(world.config["game"]["victory_time"] / rules.STEP) - 10
        frames = 0
        while world.enemies and frames < limit:
            world.update()
            frames += 1
        self.assertEqual(world.enemies, [])
        self.assertEqual(world.sparks, [])
        self.assertEqual(world.kills, 1)

    def test_spark_flies_toward_the_nearest_enemy(self):
        world = make_world()
        add_bat(world, 100.0, 0.0, hp=1000.0)
        add_bat(world, 0.0, -300.0, hp=1000.0)
        world.update()
        spark = world.sparks[0]
        self.assertGreater(spark.vx, 0.0)
        self.assertAlmostEqual(spark.vy, 0.0)

    def test_spark_cooldown_comes_from_the_data(self):
        class CountingWorld(rules.World):
            def __init__(self, config, rng=None):
                self.shots = 0
                super().__init__(config, rng)

            def _update_spark(self):
                before = len(self.sparks)
                super()._update_spark()
                self.shots += len(self.sparks) - before

        world = CountingWorld(rules.load_config(), rng=random.Random(3))
        world.spawn_timer = 10**9
        add_bat(world, 300.0, 0.0, hp=1000.0, speed=0.0)
        cooldown = world.config["weapons"]["spark_wand"]["level1"]["cooldown"]
        world.update()
        self.assertEqual(world.shots, 1)
        frames = 0
        limit = round(cooldown / rules.STEP) + 10
        while world.shots == 1 and frames < limit:
            world.update()
            frames += 1
        self.assertEqual(world.shots, 2)
        self.assertAlmostEqual(frames * rules.STEP, cooldown, delta=rules.STEP * 2)

    def test_no_shot_without_enemies(self):
        world = make_world()
        world.spawn_timer = 10**9
        for _ in range(30):
            world.update()
        self.assertEqual(world.sparks, [])


class DataDrivenTests(unittest.TestCase):
    def test_changing_data_changes_the_game(self):
        config = copy.deepcopy(rules.load_config())
        config["hero"]["speed"] = 60.0
        config["weapons"]["spark_wand"]["level1"]["damage"] = 100.0
        world = rules.World(config, rng=random.Random(5))
        world.spawn_timer = 10**9
        world.set_pointer(100.0, 0.0)
        world.update()
        self.assertAlmostEqual(world.hero.x, config["hero"]["speed"] * rules.STEP)
        add_bat(world, 80.0, 0.0, hp=1.0)
        frames = math.ceil(
            80.0 / config["weapons"]["spark_wand"]["speed"] / rules.STEP
        ) + 5
        for _ in range(frames):
            world.update()
        self.assertEqual(world.kills, 1)


if __name__ == "__main__":
    unittest.main()
