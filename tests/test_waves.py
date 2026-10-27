import copy
import math
import random
import unittest

import rules


def make_world(config=None, seed=11):
    return rules.World(config or rules.load_config(), rng=random.Random(seed))


def add_enemy(world, kind, x, y, hp=1000.0, speed=0.0):
    stats = world.config["enemies"][kind]
    enemy = rules.Enemy(
        kind=kind,
        x=x,
        y=y,
        hp=hp,
        speed=speed,
        damage=stats["damage"],
        xp=stats["xp"],
        radius=stats["radius"],
    )
    world.enemies.append(enemy)
    return enemy


def tick_spawn(world):
    world.spawn_timer = 0.0
    world.update()


class WaveTableTests(unittest.TestCase):
    def test_every_row_of_the_wave_table(self):
        expected = [
            (0, ["Bat"], 8),
            (15, ["Bat"], 15),
            (30, ["Bat", "Slime"], 22),
            (45, ["Slime", "Ghost"], 30),
            (60, ["Bat", "Ghost"], 40),
            (75, ["Bat", "Slime", "Ghost"], 50),
            (90, ["Bat", "Slime"], 50),
            (105, ["Bat"], 70),
        ]
        world = make_world()
        for moment, types, minimum in expected:
            world.time = moment
            wave = world._current_wave()
            self.assertEqual(wave["types"], types, moment)
            self.assertEqual(wave["minimum"], minimum, moment)

    def test_spawned_enemies_use_only_that_wave_s_types(self):
        cases = [
            (0, {"bat"}),
            (30, {"bat", "slime"}),
            (45, {"slime", "ghost"}),
            (60, {"bat", "ghost"}),
            (75, {"bat", "slime", "ghost"}),
            (105, {"bat"}),
        ]
        for moment, allowed in cases:
            world = make_world(seed=int(moment) + 1)
            world.time = moment
            wave = world._current_wave()
            while len(world.enemies) < wave["minimum"]:
                world._spawn_wave()
            kinds = {enemy.kind for enemy in world.enemies if enemy.kind != "demon"}
            self.assertTrue(kinds <= allowed, (moment, kinds))
            self.assertEqual(len(world.enemies), wave["minimum"])

    def test_enemy_numbers_come_from_the_data_file(self):
        enemies = rules.load_config()["enemies"]
        self.assertEqual(
            (enemies["slime"]["hp"], enemies["slime"]["speed"], enemies["slime"]["damage"]),
            (30.0, 55.0, 8.0),
        )
        self.assertEqual(enemies["slime"]["xp"], 2)
        self.assertEqual(
            (enemies["ghost"]["hp"], enemies["ghost"]["speed"], enemies["ghost"]["damage"]),
            (15.0, 135.0, 6.0),
        )
        self.assertEqual(enemies["ghost"]["xp"], 2)
        self.assertEqual(
            (enemies["demon"]["hp"], enemies["demon"]["speed"], enemies["demon"]["damage"]),
            (800.0, 85.0, 20.0),
        )
        self.assertEqual(enemies["demon"]["xp"], 0)
        self.assertEqual(enemies["demon"]["draw_scale"], 2.0)


class BossTests(unittest.TestCase):
    def test_boss_appears_once_after_ninety_seconds(self):
        world = make_world()
        world.time = 89.0
        tick_spawn(world)
        self.assertFalse(any(enemy.kind == "demon" for enemy in world.enemies))
        self.assertFalse(world.boss_spawned)

        world.time = 90.0
        tick_spawn(world)
        demons = [enemy for enemy in world.enemies if enemy.kind == "demon"]
        self.assertEqual(len(demons), 1)
        self.assertTrue(world.boss_spawned)
        boss = demons[0]
        self.assertEqual((boss.hp, boss.speed, boss.damage, boss.xp), (800.0, 85.0, 20.0, 0))
        self.assertAlmostEqual(
            math.hypot(boss.x - world.hero.x, boss.y - world.hero.y), 420.0
        )

    def test_boss_does_not_return_after_it_dies(self):
        world = make_world()
        world.time = 90.0
        tick_spawn(world)
        boss = next(enemy for enemy in world.enemies if enemy.kind == "demon")
        world.enemies = [boss]
        boss.hp = 0.0
        world.update()
        self.assertFalse(any(enemy.kind == "demon" for enemy in world.enemies))
        self.assertEqual(world.gems, [])
        world.time = 96.0
        tick_spawn(world)
        self.assertFalse(any(enemy.kind == "demon" for enemy in world.enemies))

    def test_boss_is_never_culled_and_returns_to_the_ring(self):
        world = make_world()
        boss = add_enemy(world, "demon", 800.0, 0.0)
        far_bat = add_enemy(world, "bat", 800.0, 0.0)
        world.update()
        self.assertIn(boss, world.enemies)
        self.assertNotIn(far_bat, world.enemies)
        self.assertAlmostEqual(
            math.hypot(boss.x - world.hero.x, boss.y - world.hero.y), 420.0
        )

    def test_boss_closer_than_six_hundred_stays_put(self):
        world = make_world()
        boss = add_enemy(world, "demon", 500.0, 0.0)
        world.update()
        self.assertAlmostEqual(boss.x, 500.0)
        self.assertAlmostEqual(boss.y, 0.0)

    def test_boss_waits_until_there_is_room(self):
        config = copy.deepcopy(rules.load_config())
        config["spawning"]["max_alive"] = 3
        world = rules.World(config, rng=random.Random(4))
        world.time = 90.0
        add_enemy(world, "bat", 100.0, 0.0)
        add_enemy(world, "bat", -100.0, 0.0)
        add_enemy(world, "bat", 0.0, 100.0)
        world._spawn_wave()
        self.assertFalse(world.boss_spawned)
        self.assertEqual(len(world.enemies), 3)

        world.enemies.pop()
        world._spawn_wave()
        self.assertTrue(world.boss_spawned)
        self.assertEqual(len(world.enemies), 3)
        self.assertEqual(
            len([enemy for enemy in world.enemies if enemy.kind == "demon"]), 1
        )


class VictoryTests(unittest.TestCase):
    def test_victory_when_time_reaches_two_minutes(self):
        world = make_world()
        world.time = 119.99
        world.set_pointer(100.0, 0.0)
        world.update()
        self.assertEqual(world.state, "victory")
        self.assertAlmostEqual(world.time, 120.0)
        self.assertIsNone(world.pointer)
        self.assertEqual(world.cards, [])
        world.update()
        self.assertEqual(world.time, 120.0)
        self.assertEqual(world.state, "victory")

    def test_victory_is_checked_before_contact_damage(self):
        world = make_world()
        add_enemy(world, "bat", 0.0, 0.0)
        world.hero.hp = 1.0
        world.time = 119.99
        world.update()
        self.assertEqual(world.state, "victory")
        self.assertAlmostEqual(world.hero.hp, 1.0)

    def test_victory_time_comes_from_the_data_file(self):
        config = copy.deepcopy(rules.load_config())
        config["game"]["victory_time"] = 2.0
        world = rules.World(config, rng=random.Random(3))
        world.time = 1.99
        world.update()
        self.assertEqual(world.state, "victory")
        self.assertAlmostEqual(world.time, 2.0)

    def test_reset_after_victory_starts_a_new_game(self):
        world = make_world()
        world.time = 120.0
        world.state = "victory"
        world.reset()
        self.assertEqual(world.state, "playing")
        self.assertEqual(world.time, 0.0)
        self.assertFalse(world.boss_spawned)
        self.assertEqual(world.enemies, [])


if __name__ == "__main__":
    unittest.main()
