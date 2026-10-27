import random
import unittest

import rules


def make_world(seed=7):
    return rules.World(rules.load_config(), rng=random.Random(seed))


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


def events_of(world, kind):
    return [event for event in world.events if event[0] == kind]


class EventTests(unittest.TestCase):
    def test_damage_event_carries_position_and_amount(self):
        world = make_world()
        world.weapon_levels["holy_ring"] = 1
        add_enemy(world, "slime", 40.0, 0.0)
        world.update()
        damage = events_of(world, "damage")
        self.assertEqual(len(damage), 1)
        self.assertEqual(damage[0][1:], (40.0, 0.0, 5.0))

    def test_death_event_carries_position_and_radius(self):
        world = make_world()
        world.weapon_levels["holy_ring"] = 1
        enemy = add_enemy(world, "bat", 40.0, 0.0, hp=5.0)
        world.update()
        deaths = events_of(world, "death")
        self.assertEqual(len(deaths), 1)
        self.assertEqual(deaths[0][1:], (40.0, 0.0, enemy.radius))
        self.assertEqual(world.gems[0].xp, enemy.xp)

    def test_boss_death_emits_death_but_no_gem(self):
        world = make_world()
        world.weapon_levels["holy_ring"] = 1
        add_enemy(world, "demon", 40.0, 0.0, hp=1.0)
        world.update()
        self.assertEqual(len(events_of(world, "death")), 1)
        self.assertEqual(world.gems, [])

    def test_gem_event_when_a_gem_is_collected(self):
        world = make_world()
        world.gems.append(rules.Gem(world.hero.x, world.hero.y, 1))
        world.update()
        self.assertEqual(len(events_of(world, "gem")), 1)

    def test_hurt_event_only_once_per_contact_cooldown(self):
        world = make_world()
        add_enemy(world, "bat", world.hero.x, world.hero.y)
        world.update()
        self.assertEqual(len(events_of(world, "hurt")), 1)
        world.update()
        self.assertEqual(len(events_of(world, "hurt")), 1)
        world.time += world.config["contact"]["hurt_cooldown"]
        for _ in range(31):
            world.update()
        self.assertEqual(len(events_of(world, "hurt")), 2)

    def test_level_up_event_when_a_gem_gives_a_level(self):
        world = make_world()
        world.gems.append(rules.Gem(world.hero.x, world.hero.y, world.xp_needed))
        world.update()
        self.assertEqual(world.state, "level_up")
        self.assertEqual(len(events_of(world, "level_up")), 1)
        self.assertEqual(len(events_of(world, "gem")), 1)

    def test_end_event_on_victory(self):
        world = make_world()
        world.time = world.config["game"]["victory_time"] - rules.STEP * 0.5
        world.update()
        self.assertEqual(world.state, "victory")
        self.assertEqual(len(events_of(world, "end")), 1)

    def test_end_event_on_game_over(self):
        world = make_world()
        world.hero.hp = 1.0
        add_enemy(world, "bat", world.hero.x, world.hero.y)
        world.update()
        self.assertEqual(world.state, "game_over")
        self.assertEqual(len(events_of(world, "hurt")), 1)
        self.assertEqual(len(events_of(world, "end")), 1)

    def test_reset_clears_events(self):
        world = make_world()
        world.events.append(("gem",))
        world.reset()
        self.assertEqual(world.events, [])


if __name__ == "__main__":
    unittest.main()
