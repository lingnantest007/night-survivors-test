import copy
import math
import random
import unittest

import rules


def make_world(config=None, seed=7):
    return rules.World(config or rules.load_config(), rng=random.Random(seed))


def add_enemy(world, x, y, hp=1000.0, speed=0.0, damage=0.0, radius=10.0, xp=1):
    enemy = rules.Enemy(
        kind="bat",
        x=x,
        y=y,
        hp=hp,
        speed=speed,
        damage=damage,
        xp=xp,
        radius=radius,
    )
    world.enemies.append(enemy)
    return enemy


def weapon_keys(world):
    return [
        key
        for key, data in world.config["weapons"].items()
        if isinstance(data, dict)
    ]


def spark_stats(world, level):
    data = world.config["weapons"]["spark_wand"]
    extra = data["per_level"]
    damage = data["level1"]["damage"] + extra["damage"] * (level - 1)
    cooldown = data["level1"]["cooldown"] - extra["cooldown"] * (level - 1)
    sparks = data["level1"]["sparks"] + sum(
        1 for at in extra["extra_spark_at"] if level >= at
    )
    return damage, cooldown, sparks


class GemTests(unittest.TestCase):
    def test_dead_enemy_drops_a_gem_with_its_xp(self):
        world = make_world()
        xp = world.config["enemies"]["bat"]["xp"]
        self.assertGreater(xp, 0)
        add_enemy(world, 100.0, 0.0, hp=0.0, xp=xp)
        world.update()
        self.assertEqual(world.kills, 1)
        self.assertEqual(len(world.gems), 1)
        self.assertAlmostEqual(world.gems[0].x, 100.0)
        self.assertAlmostEqual(world.gems[0].y, 0.0)
        self.assertEqual(world.gems[0].xp, xp)

    def test_gem_outside_magnet_radius_stays_put(self):
        world = make_world()
        start = world.hero.magnet_radius + 50.0
        world.gems.append(rules.Gem(start, 0.0, 1))
        world.update()
        self.assertAlmostEqual(world.gems[0].x, start)
        self.assertAlmostEqual(world.gems[0].y, 0.0)

    def test_gem_inside_magnet_radius_flies_at_the_data_speed(self):
        world = make_world()
        start = world.hero.magnet_radius - 10.0
        world.gems.append(rules.Gem(start, 0.0, 1))
        world.update()
        self.assertAlmostEqual(
            world.gems[0].x,
            start - world.config["progress"]["gem_speed"] * rules.STEP,
        )

    def test_gem_reaches_the_hero_and_gives_xp(self):
        world = make_world()
        step = world.config["progress"]["gem_speed"] * rules.STEP
        start = world.hero.hit_radius + step + 1.0
        xp = 1
        world.gems.append(rules.Gem(start, 0.0, xp))
        world.update()
        world.update()
        self.assertEqual(world.gems, [])
        self.assertEqual(world.xp, xp)
        self.assertEqual(world.level, 1)

    def test_magnet_upgrade_pulls_gems_from_farther_away(self):
        world = make_world()
        bonus = world.config["passives"]["magnet"]["magnet_radius"]
        world._apply_card(world._passive_card("magnet", 1))
        expected = world.config["hero"]["magnet_radius"] + bonus
        self.assertAlmostEqual(world.hero.magnet_radius, expected)
        start = expected - 10.0
        world.gems.append(rules.Gem(start, 0.0, 1))
        world.update()
        self.assertAlmostEqual(
            world.gems[0].x,
            start - world.config["progress"]["gem_speed"] * rules.STEP,
        )


class XpAndLevelTests(unittest.TestCase):
    def test_xp_needed_starts_from_the_data_and_grows_by_the_data(self):
        world = make_world()
        first = world.config["progress"]["xp_first_level"]
        increase = world.config["progress"]["xp_increase"]
        world._gain_xp(first)
        self.assertEqual(
            (world.level, world.xp, world.xp_needed), (2, 0, first + increase)
        )
        world._gain_xp(first + increase)
        self.assertEqual(
            (world.level, world.xp, world.xp_needed), (3, 0, first + 2 * increase)
        )
        world._gain_xp(increase)
        self.assertEqual(
            (world.level, world.xp, world.xp_needed), (3, increase, first + 2 * increase)
        )
        world._gain_xp(first + increase)
        self.assertEqual(
            (world.level, world.xp, world.xp_needed), (4, 0, first + 3 * increase)
        )

    def test_level_up_pauses_the_game_and_shows_the_configured_cards(self):
        world = make_world()
        world.gems.append(rules.Gem(0.0, 0.0, world.xp_needed))
        world.update()
        self.assertEqual(world.state, "level_up")
        self.assertEqual(world.level, 2)
        self.assertEqual(
            len(world.cards), world.config["progress"]["cards_per_level_up"]
        )
        frozen = world.time
        world.set_pointer(100.0, 0.0)
        world.update()
        self.assertEqual(world.time, frozen)
        self.assertEqual(world.hero.x, 0.0)

    def test_one_gem_can_cause_two_level_ups_in_a_row(self):
        world = make_world()
        first = world.config["progress"]["xp_first_level"]
        increase = world.config["progress"]["xp_increase"]
        world._gain_xp(first + (first + increase))
        self.assertEqual(world.pending_levelups, 2)
        self.assertEqual(
            (world.level, world.xp, world.xp_needed), (3, 0, first + 2 * increase)
        )
        world.update()
        self.assertEqual(world.state, "level_up")
        self.assertTrue(world.choose_card(0))
        self.assertEqual(world.state, "level_up")
        self.assertEqual(world.pending_levelups, 1)
        self.assertTrue(world.choose_card(0))
        self.assertEqual(world.state, "playing")
        self.assertEqual(world.pending_levelups, 0)
        self.assertEqual(world.cards, [])
        self.assertIsNone(world.pointer)

    def test_choosing_an_invalid_card_does_nothing(self):
        world = make_world()
        world._gain_xp(world.config["progress"]["xp_first_level"])
        world.update()
        self.assertFalse(world.choose_card(len(world.cards)))
        self.assertEqual(world.state, "level_up")

    def test_xp_thresholds_come_from_the_data_file(self):
        config = copy.deepcopy(rules.load_config())
        config["progress"]["xp_first_level"] = 1
        config["progress"]["xp_increase"] = 1
        world = rules.World(config, rng=random.Random(2))
        world._gain_xp(1)
        self.assertEqual(world.level, 2)
        self.assertEqual(world.xp_needed, 2)


class CardOfferTests(unittest.TestCase):
    def test_cards_never_offer_an_item_past_max_level(self):
        world = make_world()
        max_level = world.config["progress"]["item_max_level"]
        world.weapon_levels = {key: max_level for key in weapon_keys(world)}
        world.passive_levels = {
            key: max_level for key in world.config["passives"]
        }
        cards = world._offer_cards()
        self.assertEqual(
            len(cards), world.config["progress"]["cards_per_level_up"]
        )
        self.assertTrue(all(card.kind == "heal" for card in cards))
        heal_name = f"Heal {world.config['progress']['heal_amount']:g} HP"
        self.assertTrue(all(card.name == heal_name for card in cards))

    def test_an_item_one_level_below_max_is_offered_for_max(self):
        world = make_world()
        max_level = world.config["progress"]["item_max_level"]
        keys = weapon_keys(world)
        owner = keys[0]
        world.weapon_levels = {key: max_level for key in keys}
        world.weapon_levels[owner] = max_level - 1
        world.passive_levels = {
            key: max_level for key in world.config["passives"]
        }
        cards = [card for card in world._offer_cards() if card.key == owner]
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0].level, max_level)

    def test_no_new_weapon_once_max_weapons_is_reached(self):
        config = copy.deepcopy(rules.load_config())
        config["weapons"]["max_weapons"] = 2
        world = rules.World(config, rng=random.Random(9))
        max_level = world.config["progress"]["item_max_level"]
        keys = weapon_keys(world)
        world.weapon_levels = {key: max_level for key in keys[:2]}
        world.passive_levels = {
            key: max_level for key in world.config["passives"]
        }
        cards = world._offer_cards()
        self.assertFalse(any(card.kind == "weapon" for card in cards))
        self.assertTrue(all(card.kind == "heal" for card in cards))

    def test_unowned_weapons_are_offered_below_max_weapons(self):
        world = make_world()
        max_level = world.config["progress"]["item_max_level"]
        keys = weapon_keys(world)
        owned = keys[: max(0, world.config["weapons"]["max_weapons"] - 1)]
        world.weapon_levels = {key: max_level for key in owned}
        world.passive_levels = {
            key: max_level for key in world.config["passives"]
        }
        offered = {
            card.key for card in world._offer_cards() if card.kind == "weapon"
        }
        self.assertEqual(offered, set(keys) - set(owned))


class CardApplyTests(unittest.TestCase):
    def test_weapon_card_adds_the_weapon(self):
        world = make_world()
        world._apply_card(world._weapon_card("spin_blades", 1))
        self.assertEqual(world.weapon_levels["spin_blades"], 1)
        self.assertEqual(
            len(world.blade_positions()),
            world.config["weapons"]["spin_blades"]["level1"]["blades"],
        )

    def test_swift_boots_adds_its_percentage_per_level(self):
        world = make_world()
        base = world.config["hero"]["speed"]
        percent = world.config["passives"]["swift_boots"]["speed_percent"]
        world._apply_card(world._passive_card("swift_boots", 1))
        self.assertAlmostEqual(world.hero.speed, base * (1 + percent / 100))
        world._apply_card(world._passive_card("swift_boots", 2))
        self.assertAlmostEqual(world.hero.speed, base * (1 + 2 * percent / 100))

    def test_big_heart_adds_max_hp_and_heals(self):
        world = make_world()
        base_hp = world.config["hero"]["hp"]
        bonus = world.config["passives"]["big_heart"]["max_hp"]
        heal = world.config["passives"]["big_heart"]["heal"]
        world.hero.hp = base_hp / 2
        world._apply_card(world._passive_card("big_heart", 1))
        self.assertAlmostEqual(world.hero.max_hp, base_hp + bonus)
        self.assertAlmostEqual(
            world.hero.hp, min(base_hp + bonus, base_hp / 2 + heal)
        )
        world._apply_card(world._passive_card("big_heart", 2))
        self.assertAlmostEqual(world.hero.max_hp, base_hp + 2 * bonus)
        self.assertAlmostEqual(
            world.hero.hp,
            min(base_hp + 2 * bonus, min(base_hp + bonus, base_hp / 2 + heal) + heal),
        )

    def test_big_heart_never_heals_past_max_hp(self):
        world = make_world()
        base_hp = world.config["hero"]["hp"]
        bonus = world.config["passives"]["big_heart"]["max_hp"]
        world._apply_card(world._passive_card("big_heart", 1))
        self.assertAlmostEqual(world.hero.hp, base_hp + bonus)

    def test_magnet_adds_its_amount_per_level(self):
        world = make_world()
        base = world.config["hero"]["magnet_radius"]
        bonus = world.config["passives"]["magnet"]["magnet_radius"]
        world._apply_card(world._passive_card("magnet", 1))
        self.assertAlmostEqual(world.hero.magnet_radius, base + bonus)
        world._apply_card(world._passive_card("magnet", 2))
        self.assertAlmostEqual(world.hero.magnet_radius, base + 2 * bonus)

    def test_heal_card_restores_its_amount_but_not_above_max(self):
        world = make_world()
        world.hero.hp = world.hero.max_hp / 2
        heal = world.config["progress"]["heal_amount"]
        world._apply_card(world._heal_card())
        self.assertAlmostEqual(
            world.hero.hp, min(world.hero.max_hp, world.hero.max_hp / 2 + heal)
        )
        world._apply_card(world._heal_card())
        self.assertAlmostEqual(world.hero.hp, world.hero.max_hp)

    def test_loadout_lists_weapons_then_passives(self):
        world = make_world()
        world.weapon_levels = {"spark_wand": 2, "spin_blades": 1}
        world.passive_levels = {"swift_boots": 1}
        self.assertEqual(
            world.loadout_entries(),
            [
                (world.config["weapons"]["spark_wand"]["short"], 2),
                (world.config["weapons"]["spin_blades"]["short"], 1),
                (world.config["passives"]["swift_boots"]["short"], 1),
            ],
        )

    def test_reset_clears_xp_gems_and_items(self):
        world = make_world()
        world._gain_xp(world.config["progress"]["xp_first_level"] * 3)
        world.gems.append(rules.Gem(50.0, 50.0, 3))
        world.weapon_levels["spin_blades"] = 1
        world.passive_levels["magnet"] = 1
        world.reset()
        self.assertEqual(
            (world.level, world.xp, world.xp_needed),
            (1, 0, world.config["progress"]["xp_first_level"]),
        )
        self.assertEqual(world.gems, [])
        self.assertEqual(world.weapon_levels, {"spark_wand": 1})
        self.assertEqual(world.passive_levels, {})
        self.assertEqual(world.cards, [])
        self.assertEqual(world.pending_levelups, 0)


class WeaponTests(unittest.TestCase):
    def test_spark_stats_scale_with_level(self):
        world = make_world()
        max_level = world.config["progress"]["item_max_level"]
        for level in (1, 2, max_level):
            damage, cooldown, sparks = world._spark_stats(level)
            expected = spark_stats(world, level)
            self.assertAlmostEqual(damage, expected[0])
            self.assertAlmostEqual(cooldown, expected[1])
            self.assertEqual(sparks, expected[2])

    def test_blades_circle_the_hero_at_the_data_radius(self):
        world = make_world()
        world.weapon_levels = {"spin_blades": 1}
        world.time = 0.37
        radius = world.config["weapons"]["spin_blades"]["orbit_radius"]
        positions = world.blade_positions()
        self.assertEqual(
            len(positions),
            world.config["weapons"]["spin_blades"]["level1"]["blades"],
        )
        for x, y in positions:
            self.assertAlmostEqual(math.hypot(x, y), radius)

    def test_blade_count_follows_the_data(self):
        world = make_world()
        data = world.config["weapons"]["spin_blades"]
        max_level = world.config["progress"]["item_max_level"]
        for level in range(1, max_level + 1):
            world.weapon_levels = {"spin_blades": level}
            world.time = 0.3
            expected = data["level1"]["blades"] + sum(
                1 for at in data["per_level"]["extra_blade_at"] if level >= at
            )
            self.assertEqual(len(world.blade_positions()), expected)

    def test_blades_damage_enemies_in_their_path(self):
        world = make_world()
        world.weapon_levels = {"spin_blades": 1}
        data = world.config["weapons"]["spin_blades"]
        count = data["level1"]["blades"]
        damage = data["level1"]["damage"]
        enemy = add_enemy(world, 0.0, 0.0, hp=1000.0, damage=0.0, radius=200.0)
        world.update()
        self.assertAlmostEqual(enemy.hp, 1000.0 - damage * count)
        world.update()
        self.assertAlmostEqual(enemy.hp, 1000.0 - damage * count)

    def test_holy_ring_hurts_only_enemies_inside_the_circle(self):
        world = make_world()
        world.weapon_levels = {"holy_ring": 1}
        radius = world.ring_radius()
        damage = world.config["weapons"]["holy_ring"]["level1"]["damage"]
        inside = add_enemy(world, radius / 2, 0.0, hp=1000.0, damage=0.0, radius=1.0)
        outside = add_enemy(world, radius + 10.0, 0.0, hp=1000.0, damage=0.0, radius=1.0)
        world.update()
        self.assertAlmostEqual(inside.hp, 1000.0 - damage)
        self.assertAlmostEqual(outside.hp, 1000.0)

    def test_holy_ring_level_two_is_wider_and_stronger(self):
        world = make_world()
        world.weapon_levels = {"holy_ring": 2}
        data = world.config["weapons"]["holy_ring"]
        expected_radius = data["level1"]["radius"] + data["per_level"]["radius"]
        expected_damage = data["level1"]["damage"] + data["per_level"]["damage"]
        self.assertAlmostEqual(world.ring_radius(), expected_radius)
        edge = add_enemy(world, expected_radius - 1.0, 0.0, hp=1000.0, damage=0.0, radius=1.0)
        world.update()
        self.assertAlmostEqual(edge.hp, 1000.0 - expected_damage)

    def test_holy_ring_pulses_at_the_data_cooldown(self):
        world = make_world()
        world.spawn_timer = 10**9
        world.weapon_levels = {"holy_ring": 1}
        data = world.config["weapons"]["holy_ring"]
        damage = data["level1"]["damage"]
        cooldown = data["cooldown"]
        enemy = add_enemy(world, data["level1"]["radius"] / 2, 0.0, hp=1000.0, damage=0.0, radius=1.0)
        world.update()
        first_hp = 1000.0 - damage
        self.assertAlmostEqual(enemy.hp, first_hp)
        frames = 0
        limit = round(cooldown / rules.STEP) + 10
        while enemy.hp == first_hp and frames < limit:
            world.update()
            frames += 1
        self.assertAlmostEqual(enemy.hp, first_hp - damage)
        self.assertAlmostEqual(frames * rules.STEP, cooldown, delta=rules.STEP * 2)

    def test_ring_radius_is_none_when_not_owned(self):
        world = make_world()
        self.assertIsNone(world.ring_radius())


if __name__ == "__main__":
    unittest.main()
