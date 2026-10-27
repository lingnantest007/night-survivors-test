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


def boss_wave(world):
    return next(
        wave for wave in world.config["spawning"]["waves"] if "boss" in wave
    )


class WaveTableTests(unittest.TestCase):
    def test_every_row_of_the_wave_table(self):
        world = make_world()
        waves = world.config["spawning"]["waves"]
        for wave in waves:
            world.time = wave["from"]
            current = world._current_wave()
            self.assertEqual(current["types"], wave["types"])
            self.assertEqual(current["minimum"], wave["minimum"])

    def test_spawned_enemies_use_only_that_wave_s_types(self):
        config = rules.load_config()
        waves = config["spawning"]["waves"]
        max_alive = config["spawning"]["max_alive"]
        for index, wave in enumerate(waves):
            world = make_world(seed=index + 1)
            world.time = wave["from"]
            allowed = {world._enemy_kind(name) for name in wave["types"]}
            limit = min(wave["minimum"], max_alive)
            for _ in range(limit + 1):
                if len(world.enemies) >= limit:
                    break
                world._spawn_wave()
            self.assertEqual(len(world.enemies), limit, wave["from"])
            kinds = {
                enemy.kind
                for enemy in world.enemies
                if enemy.kind != world.boss_kind
            }
            self.assertTrue(kinds <= allowed, (wave["from"], kinds, allowed))

    def test_enemy_numbers_come_from_the_data_file(self):
        config = copy.deepcopy(rules.load_config())
        for index, stats in enumerate(config["enemies"].values(), start=1):
            stats["hp"] = 10.0 * index
            stats["speed"] = 20.0 * index
            stats["damage"] = 30.0 * index
            stats["xp"] = index
            stats["radius"] = 40.0 * index
        world = rules.World(config, rng=random.Random(1))
        for kind, stats in config["enemies"].items():
            enemy = world._make_enemy(kind, 5.0, 6.0)
            self.assertEqual((enemy.x, enemy.y), (5.0, 6.0))
            self.assertEqual(enemy.hp, stats["hp"])
            self.assertEqual(enemy.speed, stats["speed"])
            self.assertEqual(enemy.damage, stats["damage"])
            self.assertEqual(enemy.xp, stats["xp"])
            self.assertEqual(enemy.radius, stats["radius"])


class BossTests(unittest.TestCase):
    def test_boss_appears_once_at_its_wave_time(self):
        world = make_world()
        wave = boss_wave(world)
        boss_kind = world.boss_kind
        self.assertIsNotNone(boss_kind)
        stats = world.config["enemies"][boss_kind]
        spawn_radius = world.config["spawning"]["ring_radius"]

        world.time = wave["from"] - 1.0
        tick_spawn(world)
        self.assertFalse(any(enemy.kind == boss_kind for enemy in world.enemies))
        self.assertFalse(world.boss_spawned)

        world.time = wave["from"]
        tick_spawn(world)
        bosses = [enemy for enemy in world.enemies if enemy.kind == boss_kind]
        self.assertEqual(len(bosses), 1)
        self.assertTrue(world.boss_spawned)
        boss = bosses[0]
        self.assertEqual(
            (boss.hp, boss.speed, boss.damage, boss.xp),
            (stats["hp"], stats["speed"], stats["damage"], stats["xp"]),
        )
        self.assertAlmostEqual(
            math.hypot(boss.x - world.hero.x, boss.y - world.hero.y),
            spawn_radius,
        )

    def test_boss_does_not_return_after_it_dies(self):
        world = make_world()
        wave = boss_wave(world)
        boss_kind = world.boss_kind
        stats = world.config["enemies"][boss_kind]
        world.time = wave["from"]
        tick_spawn(world)
        boss = next(enemy for enemy in world.enemies if enemy.kind == boss_kind)
        world.enemies = [boss]
        boss.hp = 0.0
        world.update()
        self.assertFalse(any(enemy.kind == boss_kind for enemy in world.enemies))
        self.assertEqual(len(world.gems), 1 if stats["xp"] > 0 else 0)
        world.time = wave["from"] + 2 * world.config["spawning"]["interval"]
        tick_spawn(world)
        self.assertFalse(any(enemy.kind == boss_kind for enemy in world.enemies))

    def test_boss_is_never_culled_and_returns_to_the_ring(self):
        world = make_world()
        spawning = world.config["spawning"]
        boss_kind = world.boss_kind
        far = spawning["cull_radius"] + 100.0
        boss = add_enemy(world, boss_kind, far, 0.0)
        far_bat = add_enemy(world, "bat", far, 0.0)
        world.update()
        self.assertIn(boss, world.enemies)
        self.assertNotIn(far_bat, world.enemies)
        self.assertAlmostEqual(
            math.hypot(boss.x - world.hero.x, boss.y - world.hero.y),
            spawning["ring_radius"],
        )

    def test_boss_closer_than_the_return_radius_stays_put(self):
        world = make_world()
        close = world.config["spawning"]["boss_return_radius"] - 100.0
        boss = add_enemy(world, world.boss_kind, close, 0.0)
        world.update()
        self.assertAlmostEqual(boss.x, close)
        self.assertAlmostEqual(boss.y, 0.0)

    def test_boss_waits_until_there_is_room(self):
        config = copy.deepcopy(rules.load_config())
        config["spawning"]["max_alive"] = 3
        world = rules.World(config, rng=random.Random(4))
        wave = boss_wave(world)
        limit = world.config["spawning"]["max_alive"]
        world.time = wave["from"]
        for index in range(limit):
            add_enemy(world, "bat", 100.0 * index, 0.0)
        world._spawn_wave()
        self.assertFalse(world.boss_spawned)
        self.assertEqual(len(world.enemies), limit)

        world.enemies.pop()
        world._spawn_wave()
        self.assertTrue(world.boss_spawned)
        self.assertEqual(len(world.enemies), limit)
        self.assertEqual(
            len([enemy for enemy in world.enemies if enemy.kind == world.boss_kind]),
            1,
        )


class VictoryTests(unittest.TestCase):
    def test_victory_when_time_reaches_the_configured_limit(self):
        world = make_world()
        victory_time = world.config["game"]["victory_time"]
        world.time = victory_time - rules.STEP * 0.5
        world.set_pointer(100.0, 0.0)
        world.update()
        self.assertEqual(world.state, "victory")
        self.assertAlmostEqual(world.time, victory_time)
        self.assertIsNone(world.pointer)
        self.assertEqual(world.cards, [])
        world.update()
        self.assertEqual(world.time, victory_time)
        self.assertEqual(world.state, "victory")

    def test_victory_is_checked_before_contact_damage(self):
        world = make_world()
        add_enemy(world, "bat", 0.0, 0.0)
        world.hero.hp = 1.0
        world.time = world.config["game"]["victory_time"] - rules.STEP * 0.5
        world.update()
        self.assertEqual(world.state, "victory")
        self.assertAlmostEqual(world.hero.hp, 1.0)

    def test_victory_time_comes_from_the_data_file(self):
        config = copy.deepcopy(rules.load_config())
        config["game"]["victory_time"] = 2.0
        world = rules.World(config, rng=random.Random(3))
        world.time = config["game"]["victory_time"] - rules.STEP * 0.5
        world.update()
        self.assertEqual(world.state, "victory")
        self.assertAlmostEqual(world.time, config["game"]["victory_time"])

    def test_reset_after_victory_starts_a_new_game(self):
        world = make_world()
        world.time = world.config["game"]["victory_time"]
        world.state = "victory"
        world.reset()
        self.assertEqual(world.state, "playing")
        self.assertEqual(world.time, 0.0)
        self.assertFalse(world.boss_spawned)
        self.assertEqual(world.enemies, [])


if __name__ == "__main__":
    unittest.main()
