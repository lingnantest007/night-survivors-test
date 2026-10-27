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


class GemTests(unittest.TestCase):
    def test_dead_enemy_drops_a_gem_with_its_xp(self):
        world = make_world()
        add_enemy(world, 100.0, 0.0, hp=0.0, xp=2)
        world.update()
        self.assertEqual(world.kills, 1)
        self.assertEqual(len(world.gems), 1)
        self.assertAlmostEqual(world.gems[0].x, 100.0)
        self.assertAlmostEqual(world.gems[0].y, 0.0)
        self.assertEqual(world.gems[0].xp, 2)

    def test_gem_outside_magnet_radius_stays_put(self):
        world = make_world()
        world.gems.append(rules.Gem(100.0, 0.0, 1))
        world.update()
        self.assertAlmostEqual(world.gems[0].x, 100.0)
        self.assertAlmostEqual(world.gems[0].y, 0.0)

    def test_gem_inside_magnet_radius_flies_at_300_pixels_per_second(self):
        world = make_world()
        world.gems.append(rules.Gem(50.0, 0.0, 1))
        world.update()
        self.assertAlmostEqual(world.gems[0].x, 45.0)

    def test_gem_reaches_the_hero_and_gives_xp(self):
        world = make_world()
        world.gems.append(rules.Gem(20.0, 0.0, 2))
        world.update()
        world.update()
        self.assertEqual(world.gems, [])
        self.assertEqual(world.xp, 2)
        self.assertEqual(world.level, 1)

    def test_magnet_upgrade_pulls_gems_from_farther_away(self):
        world = make_world()
        world._apply_card(world._passive_card("magnet", 1))
        self.assertAlmostEqual(world.hero.magnet_radius, 90.0)
        world.gems.append(rules.Gem(80.0, 0.0, 1))
        world.update()
        self.assertAlmostEqual(world.gems[0].x, 75.0)


class XpAndLevelTests(unittest.TestCase):
    def test_xp_needed_starts_at_five_and_grows_by_four(self):
        world = make_world()
        world._gain_xp(5)
        self.assertEqual((world.level, world.xp, world.xp_needed), (2, 0, 9))
        world._gain_xp(9)
        self.assertEqual((world.level, world.xp, world.xp_needed), (3, 0, 13))
        world._gain_xp(4)
        self.assertEqual((world.level, world.xp, world.xp_needed), (3, 4, 13))
        world._gain_xp(9)
        self.assertEqual((world.level, world.xp, world.xp_needed), (4, 0, 17))

    def test_level_up_pauses_the_game_and_shows_three_cards(self):
        world = make_world()
        world.gems.append(rules.Gem(0.0, 0.0, 5))
        world.update()
        self.assertEqual(world.state, "level_up")
        self.assertEqual(world.level, 2)
        self.assertEqual(len(world.cards), 3)
        frozen = world.time
        world.set_pointer(100.0, 0.0)
        world.update()
        self.assertEqual(world.time, frozen)
        self.assertEqual(world.hero.x, 0.0)

    def test_one_gem_can_cause_two_level_ups_in_a_row(self):
        world = make_world()
        world._gain_xp(14)
        self.assertEqual(world.pending_levelups, 2)
        self.assertEqual((world.level, world.xp, world.xp_needed), (3, 0, 13))
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
        world._gain_xp(5)
        world.update()
        self.assertFalse(world.choose_card(3))
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
    def test_cards_never_offer_an_item_past_level_five(self):
        world = make_world()
        world.weapon_levels = {"spark_wand": 5, "spin_blades": 5, "holy_ring": 5}
        world.passive_levels = {"swift_boots": 5, "big_heart": 5, "magnet": 5}
        cards = world._offer_cards()
        self.assertEqual(len(cards), 3)
        self.assertTrue(all(card.kind == "heal" for card in cards))
        self.assertTrue(all(card.name == "Heal 30 HP" for card in cards))

    def test_a_level_four_item_is_offered_for_level_five(self):
        world = make_world()
        world.weapon_levels = {"spark_wand": 4, "spin_blades": 5, "holy_ring": 5}
        world.passive_levels = {"swift_boots": 5, "big_heart": 5, "magnet": 5}
        spark_cards = [card for card in world._offer_cards() if card.key == "spark_wand"]
        self.assertEqual(len(spark_cards), 1)
        self.assertEqual(spark_cards[0].level, 5)

    def test_no_new_weapon_once_max_weapons_is_reached(self):
        config = copy.deepcopy(rules.load_config())
        config["weapons"]["max_weapons"] = 2
        world = rules.World(config, rng=random.Random(9))
        world.weapon_levels = {"spark_wand": 5, "spin_blades": 5}
        world.passive_levels = {"swift_boots": 5, "big_heart": 5, "magnet": 5}
        cards = world._offer_cards()
        self.assertFalse(any(card.kind == "weapon" for card in cards))
        self.assertTrue(all(card.kind == "heal" for card in cards))

    def test_new_weapons_are_offered_below_three_weapons(self):
        world = make_world()
        world.weapon_levels = {"spark_wand": 5, "spin_blades": 5}
        world.passive_levels = {"swift_boots": 5, "big_heart": 5, "magnet": 5}
        weapon_keys = {
            card.key for card in world._offer_cards() if card.kind == "weapon"
        }
        self.assertEqual(weapon_keys, {"holy_ring"})


class CardApplyTests(unittest.TestCase):
    def test_weapon_card_adds_the_weapon(self):
        world = make_world()
        world._apply_card(world._weapon_card("spin_blades", 1))
        self.assertEqual(world.weapon_levels["spin_blades"], 1)
        self.assertEqual(len(world.blade_positions()), 2)

    def test_swift_boots_add_ten_percent_speed_per_level(self):
        world = make_world()
        world._apply_card(world._passive_card("swift_boots", 1))
        self.assertAlmostEqual(world.hero.speed, 132.0)
        world._apply_card(world._passive_card("swift_boots", 2))
        self.assertAlmostEqual(world.hero.speed, 144.0)

    def test_big_heart_adds_max_hp_and_heals(self):
        world = make_world()
        world.hero.hp = 40.0
        world._apply_card(world._passive_card("big_heart", 1))
        self.assertAlmostEqual(world.hero.max_hp, 120.0)
        self.assertAlmostEqual(world.hero.hp, 60.0)
        world._apply_card(world._passive_card("big_heart", 2))
        self.assertAlmostEqual(world.hero.max_hp, 140.0)
        self.assertAlmostEqual(world.hero.hp, 80.0)

    def test_big_heart_never_heals_past_max_hp(self):
        world = make_world()
        world._apply_card(world._passive_card("big_heart", 1))
        self.assertAlmostEqual(world.hero.hp, 120.0)

    def test_magnet_adds_thirty_pixels_per_level(self):
        world = make_world()
        world._apply_card(world._passive_card("magnet", 1))
        self.assertAlmostEqual(world.hero.magnet_radius, 90.0)
        world._apply_card(world._passive_card("magnet", 2))
        self.assertAlmostEqual(world.hero.magnet_radius, 120.0)

    def test_heal_card_restores_thirty_hp_but_not_above_max(self):
        world = make_world()
        world.hero.hp = 50.0
        world._apply_card(world._heal_card())
        self.assertAlmostEqual(world.hero.hp, 80.0)
        world._apply_card(world._heal_card())
        self.assertAlmostEqual(world.hero.hp, 100.0)

    def test_loadout_lists_weapons_then_passives(self):
        world = make_world()
        world.weapon_levels = {"spark_wand": 2, "spin_blades": 1}
        world.passive_levels = {"swift_boots": 1}
        self.assertEqual(
            world.loadout_entries(), [("Spark", 2), ("Blades", 1), ("Boots", 1)]
        )

    def test_reset_clears_xp_gems_and_items(self):
        world = make_world()
        world._gain_xp(30)
        world.gems.append(rules.Gem(50.0, 50.0, 3))
        world.weapon_levels["spin_blades"] = 1
        world.passive_levels["magnet"] = 1
        world.reset()
        self.assertEqual((world.level, world.xp, world.xp_needed), (1, 0, 5))
        self.assertEqual(world.gems, [])
        self.assertEqual(world.weapon_levels, {"spark_wand": 1})
        self.assertEqual(world.passive_levels, {})
        self.assertEqual(world.cards, [])
        self.assertEqual(world.pending_levelups, 0)


class WeaponTests(unittest.TestCase):
    def test_spark_stats_scale_with_level(self):
        world = make_world()
        self.assertEqual(world._spark_stats(1), (10.0, 0.8, 1))
        damage, cooldown, sparks = world._spark_stats(3)
        self.assertAlmostEqual(damage, 16.0)
        self.assertAlmostEqual(cooldown, 0.64)
        self.assertEqual(sparks, 2)
        damage, cooldown, sparks = world._spark_stats(5)
        self.assertAlmostEqual(damage, 22.0)
        self.assertAlmostEqual(cooldown, 0.48)
        self.assertEqual(sparks, 3)

    def test_blades_circle_the_hero_at_sixty_pixels(self):
        world = make_world()
        world.weapon_levels = {"spin_blades": 1}
        world.time = 0.37
        positions = world.blade_positions()
        self.assertEqual(len(positions), 2)
        for x, y in positions:
            self.assertAlmostEqual(math.hypot(x, y), 60.0)

    def test_blade_count_grows_at_levels_two_and_four(self):
        world = make_world()
        for level, expected in [(1, 2), (2, 3), (3, 3), (4, 4), (5, 4)]:
            world.weapon_levels = {"spin_blades": level}
            world.time = 0.3
            self.assertEqual(len(world.blade_positions()), expected)

    def test_blades_damage_enemies_in_their_path(self):
        world = make_world()
        world.weapon_levels = {"spin_blades": 1}
        enemy = add_enemy(world, 0.0, 0.0, hp=1000.0, damage=0.0, radius=120.0)
        world.update()
        self.assertAlmostEqual(enemy.hp, 984.0)
        world.update()
        self.assertAlmostEqual(enemy.hp, 984.0)

    def test_holy_ring_hurts_only_enemies_inside_the_circle(self):
        world = make_world()
        world.weapon_levels = {"holy_ring": 1}
        inside = add_enemy(world, 40.0, 0.0, hp=1000.0, damage=0.0, radius=1.0)
        outside = add_enemy(world, 60.0, 0.0, hp=1000.0, damage=0.0, radius=1.0)
        world.update()
        self.assertAlmostEqual(inside.hp, 995.0)
        self.assertAlmostEqual(outside.hp, 1000.0)

    def test_holy_ring_level_two_is_wider_and_stronger(self):
        world = make_world()
        world.weapon_levels = {"holy_ring": 2}
        self.assertAlmostEqual(world.ring_radius(), 60.0)
        edge = add_enemy(world, 59.0, 0.0, hp=1000.0, damage=0.0, radius=1.0)
        world.update()
        self.assertAlmostEqual(edge.hp, 993.0)

    def test_holy_ring_pulses_every_half_second(self):
        world = make_world()
        world.weapon_levels = {"holy_ring": 1}
        enemy = add_enemy(world, 30.0, 0.0, hp=1000.0, damage=0.0, radius=1.0)
        world.update()
        self.assertAlmostEqual(enemy.hp, 995.0)
        for _ in range(29):
            world.update()
        self.assertAlmostEqual(enemy.hp, 995.0)
        for _ in range(3):
            world.update()
        self.assertAlmostEqual(enemy.hp, 990.0)

    def test_ring_radius_is_none_when_not_owned(self):
        world = make_world()
        self.assertIsNone(world.ring_radius())


if __name__ == "__main__":
    unittest.main()
