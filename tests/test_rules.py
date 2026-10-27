import copy
import math
import random
import unittest

import rules


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
        self.assertEqual(config["screen"]["width"], 390)
        self.assertEqual(config["screen"]["height"], 700)
        self.assertEqual(config["hero"]["speed"], 120.0)
        self.assertEqual(config["hero"]["hp"], 100.0)
        self.assertEqual(config["hero"]["hit_radius"], 12.0)
        self.assertEqual(config["hero"]["magnet_radius"], 60.0)
        self.assertEqual(config["hero"]["pointer_stop_distance"], 12.0)
        self.assertEqual(config["weapons"]["spark_wand"]["speed"], 400.0)
        self.assertEqual(config["weapons"]["spark_wand"]["level1"]["damage"], 10.0)
        self.assertEqual(config["weapons"]["spark_wand"]["level1"]["cooldown"], 0.8)
        self.assertEqual(config["enemies"]["bat"]["hp"], 8.0)
        self.assertEqual(config["enemies"]["bat"]["speed"], 100.0)
        self.assertEqual(config["contact"]["hurt_cooldown"], 0.5)
        self.assertEqual(config["spawning"]["ring_radius"], 420.0)
        self.assertEqual(config["spawning"]["cull_radius"], 700.0)
        self.assertEqual(config["spawning"]["max_alive"], 120)
        self.assertEqual(config["game"]["victory_time"], 120.0)

    def test_wave_table_changes_over_time(self):
        world = make_world()
        expected = [
            (0, 8),
            (15, 15),
            (30, 22),
            (45, 30),
            (60, 40),
            (75, 50),
            (90, 50),
            (105, 70),
        ]
        for moment, minimum in expected:
            world.time = moment
            self.assertEqual(world._current_wave()["minimum"], minimum)


class TimeAndMovementTests(unittest.TestCase):
    def test_time_step_is_one_sixtieth(self):
        world = make_world()
        world.update()
        self.assertAlmostEqual(world.time, 1.0 / 60.0)

    def test_hero_walks_toward_pointer_at_speed(self):
        world = make_world()
        world.set_pointer(100.0, 0.0)
        world.update()
        self.assertAlmostEqual(world.hero.x, 2.0)
        self.assertAlmostEqual(world.hero.y, 0.0)

    def test_hero_stops_twelve_pixels_away(self):
        world = make_world()
        world.set_pointer(30.0, 0.0)
        for _ in range(40):
            world.update()
        self.assertAlmostEqual(world.hero.x, 18.0, places=6)
        self.assertAlmostEqual(world.hero.y, 0.0, places=6)

    def test_pointer_inside_stop_distance_does_not_move(self):
        world = make_world()
        world.set_pointer(12.0, 0.0)
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
    def test_spawning_starts_after_one_second_with_eight_bats(self):
        world = make_world()
        for _ in range(59):
            world.update()
        self.assertEqual(len(world.enemies), 0)
        world.update()
        self.assertEqual(len(world.enemies), 8)
        self.assertTrue(all(enemy.kind == "bat" for enemy in world.enemies))

    def test_new_bats_appear_on_the_420_pixel_ring(self):
        world = make_world()
        for _ in range(60):
            world.update()
        for enemy in world.enemies:
            distance = math.hypot(enemy.x - world.hero.x, enemy.y - world.hero.y)
            self.assertAlmostEqual(distance, 420.0, places=6)

    def test_at_most_eight_new_enemies_per_second(self):
        world = make_world()
        world.time = 15.0
        world.spawn_timer = 0.0
        world.update()
        self.assertEqual(len(world.enemies), 8)
        for _ in range(60):
            world.update()
        self.assertEqual(len(world.enemies), 15)

    def test_never_more_than_120_enemies(self):
        config = copy.deepcopy(rules.load_config())
        config["spawning"]["waves"][0]["minimum"] = 500
        world = rules.World(config, rng=random.Random(7))
        for _ in range(20):
            world._spawn_wave()
        self.assertEqual(len(world.enemies), 120)

    def test_bat_moves_toward_hero(self):
        world = make_world()
        add_bat(world, 100.0, 0.0)
        world.update()
        self.assertAlmostEqual(world.hero.hp, 100.0)
        self.assertAlmostEqual(world.enemies[0].x, 100.0 - 100.0 / 60.0)

    def test_enemies_farther_than_700_are_removed(self):
        world = make_world()
        add_bat(world, 800.0, 0.0, speed=0.0)
        add_bat(world, 600.0, 0.0, speed=0.0)
        world.update()
        self.assertEqual(len(world.enemies), 1)
        self.assertAlmostEqual(world.enemies[0].x, 600.0)


class DamageTests(unittest.TestCase):
    def test_bat_touching_hero_hurts_once_every_half_second(self):
        world = make_world()
        add_bat(world, 0.0, 0.0, hp=1000.0)
        world.update()
        self.assertAlmostEqual(world.hero.hp, 95.0)
        self.assertAlmostEqual(world.enemies[0].cooldown, 0.5)
        frames = 0
        while world.hero.hp == 95.0 and frames < 60:
            world.update()
            frames += 1
        self.assertAlmostEqual(world.hero.hp, 90.0)
        self.assertTrue(28 <= frames <= 32, frames)

    def test_two_bats_each_hurt_the_hero(self):
        world = make_world()
        add_bat(world, 0.0, 0.0, hp=1000.0)
        add_bat(world, 0.0, 0.0, hp=1000.0)
        world.update()
        self.assertAlmostEqual(world.hero.hp, 90.0)

    def test_game_over_and_play_again(self):
        world = make_world()
        add_bat(world, 0.0, 0.0, hp=1000.0)
        world.hero.hp = 5.0
        world.update()
        self.assertEqual(world.state, "game_over")
        self.assertEqual(world.hero.hp, 0.0)
        frozen = world.time
        world.update()
        self.assertEqual(world.time, frozen)
        world.reset()
        self.assertEqual(world.state, "playing")
        self.assertEqual(world.hero.hp, world.hero.max_hp)
        self.assertEqual(world.time, 0.0)
        self.assertEqual(world.enemies, [])
        self.assertEqual(world.sparks, [])
        self.assertEqual(world.kills, 0)
        self.assertIsNone(world.pointer)


class SparkWandTests(unittest.TestCase):
    def test_spark_hits_nearest_enemy_and_kills_a_bat(self):
        world = make_world()
        add_bat(world, 100.0, 0.0)
        world.update()
        self.assertEqual(len(world.sparks), 1)
        self.assertGreater(world.sparks[0].vx, 0.0)
        for _ in range(40):
            world.update()
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

    def test_spark_cooldown_is_point_eight_seconds(self):
        class CountingWorld(rules.World):
            def __init__(self, config, rng=None):
                self.shots = 0
                super().__init__(config, rng)

            def _update_spark(self):
                before = len(self.sparks)
                super()._update_spark()
                self.shots += len(self.sparks) - before

        world = CountingWorld(rules.load_config(), rng=random.Random(3))
        add_bat(world, 300.0, 0.0, hp=1000.0, speed=0.0)
        world.update()
        self.assertEqual(world.shots, 1)
        for _ in range(49):
            world.update()
        self.assertEqual(world.shots, 2)

    def test_no_shot_without_enemies(self):
        world = make_world()
        for _ in range(30):
            world.update()
        self.assertEqual(world.sparks, [])


class DataDrivenTests(unittest.TestCase):
    def test_changing_data_changes_the_game(self):
        config = copy.deepcopy(rules.load_config())
        config["hero"]["speed"] = 60.0
        config["weapons"]["spark_wand"]["level1"]["damage"] = 100.0
        world = rules.World(config, rng=random.Random(5))
        world.set_pointer(100.0, 0.0)
        world.update()
        self.assertAlmostEqual(world.hero.x, 1.0)
        add_bat(world, 80.0, 0.0)
        for _ in range(40):
            world.update()
        self.assertEqual(world.kills, 1)


if __name__ == "__main__":
    unittest.main()
