"""Night Survivors: window, drawing, sound and input. Step 5 (Sound and feel)."""

import asyncio
import math
import random
from pathlib import Path

import pygame

import rules

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
SOUNDS_DIR = Path(__file__).resolve().parent / "sounds"
SOUND_NAMES = ("hit", "gem", "level_up", "hurt", "end")
SOUND_VOLUMES = {
    "hit": 0.35,
    "gem": 0.5,
    "level_up": 0.65,
    "hurt": 0.55,
    "end": 0.7,
}
HIT_SOUND_GAP = 0.045
SHAKE_TIME = 0.25
SHAKE_STRENGTH = 7.0
DAMAGE_LIFE = 0.65
DAMAGE_RISE = 38.0
FLASH_LIFE = 0.16
DAMAGE_COLOR = (255, 238, 150)
DAMAGE_SHADOW = (24, 22, 30)
BACKGROUND = (24, 26, 36)
SPARK_COLOR = (255, 240, 130)
TEXT_COLOR = (238, 240, 248)
TEXT_DIM = (176, 184, 202)
HP_BACK = (60, 24, 28)
HP_FRONT = (224, 62, 62)
XP_BACK = (24, 34, 58)
XP_FRONT = (78, 140, 255)
OVERLAY = (8, 9, 14, 195)
LOADOUT_BACK = (14, 16, 24, 170)
RING_COLOR = (150, 214, 255, 110)
CARD_COLOR = (34, 38, 54)
CARD_HOVER = (52, 60, 86)
CARD_EDGE = (90, 102, 140)
ACCENT_COLOR = (255, 221, 105)
VICTORY_COLOR = (120, 235, 140)
CARD_WIDTH = 340
CARD_HEIGHT = 150
CARD_TOP = 170
CARD_GAP = 14


def load_image(name):
    path = ASSETS_DIR / name
    if not path.is_file():
        raise SystemExit(f"Missing {path}. Run: python make_assets.py")
    return pygame.image.load(str(path)).convert_alpha()


def load_sound(name):
    for extension in (".ogg", ".wav"):
        path = SOUNDS_DIR / f"{name}{extension}"
        if path.is_file():
            return pygame.mixer.Sound(str(path))
    raise SystemExit(f"Missing sounds/{name}.ogg or .wav. Run: python make_sounds.py")


def play_sound(sounds, name):
    sound = sounds.get(name)
    if sound is not None:
        sound.play()


class FloatingNumber:
    def __init__(self, x, y, amount):
        self.x = x
        self.y = y
        self.text = f"{amount:g}"
        self.life = DAMAGE_LIFE
        self.max_life = DAMAGE_LIFE


class Flash:
    def __init__(self, x, y, radius):
        self.x = x
        self.y = y
        self.radius = radius
        self.life = FLASH_LIFE
        self.max_life = FLASH_LIFE


def format_time(seconds):
    whole = int(seconds)
    return f"{whole // 60}:{whole % 60:02d}"


def camera_origin(world, width, height):
    return world.hero.x - width / 2.0, world.hero.y - height / 2.0


def screen_to_world(world, width, height, screen_x, screen_y):
    cam_x, cam_y = camera_origin(world, width, height)
    return cam_x + screen_x, cam_y + screen_y


def card_rects(width, count):
    left = (width - CARD_WIDTH) // 2
    return [
        pygame.Rect(
            left,
            CARD_TOP + index * (CARD_HEIGHT + CARD_GAP),
            CARD_WIDTH,
            CARD_HEIGHT,
        )
        for index in range(count)
    ]


def card_at(pos, width, count):
    if pos is None:
        return None
    for index, rect in enumerate(card_rects(width, count)):
        if rect.collidepoint(pos):
            return index
    return None


def wrap_text(font, text, max_width):
    lines = []
    line = ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if line and font.size(candidate)[0] > max_width:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines


def draw_floor(screen, tile, cam_x, cam_y, width, height):
    tile_w, tile_h = tile.get_size()
    first_col = math.floor(cam_x / tile_w)
    first_row = math.floor(cam_y / tile_h)
    cols = math.ceil(width / tile_w) + 2
    rows = math.ceil(height / tile_h) + 2
    for row in range(rows):
        top = round((first_row + row) * tile_h - cam_y)
        for col in range(cols):
            left = round((first_col + col) * tile_w - cam_x)
            screen.blit(tile, (left, top))


def blit_centred(screen, image, x, y):
    screen.blit(image, image.get_rect(center=(round(x), round(y))))


def draw_scene(screen, world, images, cam_x, cam_y, width, height):
    draw_floor(screen, images["floor"], cam_x, cam_y, width, height)

    hero = world.hero
    hx = hero.x - cam_x
    hy = hero.y - cam_y

    radius = world.ring_radius()
    if radius is not None:
        size = int(radius * 2) + 8
        ring = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(ring, RING_COLOR, (size // 2, size // 2), int(radius), 3)
        screen.blit(ring, (round(hx) - size // 2, round(hy) - size // 2))

    for gem in world.gems:
        blit_centred(screen, images["gem"], gem.x - cam_x, gem.y - cam_y)

    spark_radius = int(world.config["weapons"]["spark_wand"]["spark_radius"])
    for spark in world.sparks:
        pygame.draw.circle(
            screen, SPARK_COLOR, (round(spark.x - cam_x), round(spark.y - cam_y)), spark_radius
        )

    for enemy in world.enemies:
        blit_centred(screen, images[enemy.kind], enemy.x - cam_x, enemy.y - cam_y)

    for blade_x, blade_y in world.blade_positions():
        angle = math.degrees(math.atan2(blade_y - hero.y, blade_x - hero.x))
        blade = pygame.transform.rotate(images["sword"], -angle - 90)
        blit_centred(screen, blade, blade_x - cam_x, blade_y - cam_y)

    blit_centred(screen, images["hero"], hx, hy)


def draw_effects(screen, damage_numbers, flashes, cam_x, cam_y, font):
    for flash in flashes:
        progress = 1.0 - flash.life / flash.max_life
        radius = max(2, int(flash.radius * (1.0 + progress * 0.9)))
        alpha = max(0, int(220 * flash.life / flash.max_life))
        size = radius * 2 + 4
        burst = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(burst, (255, 255, 255, alpha), (size // 2, size // 2), radius)
        screen.blit(
            burst,
            (round(flash.x - cam_x) - size // 2, round(flash.y - cam_y) - size // 2),
        )

    for number in damage_numbers:
        alpha = max(0, int(255 * number.life / number.max_life))
        text = font.render(number.text, True, DAMAGE_COLOR)
        shadow = font.render(number.text, True, DAMAGE_SHADOW)
        text.set_alpha(alpha)
        shadow.set_alpha(alpha)
        left = round(number.x - cam_x - text.get_width() / 2)
        top = round(number.y - cam_y - text.get_height() / 2)
        screen.blit(shadow, (left + 2, top + 2))
        screen.blit(text, (left, top))


def age_effects(damage_numbers, flashes, seconds):
    for number in damage_numbers:
        number.life -= seconds
        number.y -= DAMAGE_RISE * seconds
    for flash in flashes:
        flash.life -= seconds
    damage_numbers[:] = [number for number in damage_numbers if number.life > 0]
    flashes[:] = [flash for flash in flashes if flash.life > 0]


def draw_hud(screen, world, font, width):
    bar = pygame.Rect(12, 12, 180, 16)
    pygame.draw.rect(screen, HP_BACK, bar)
    fraction = max(0.0, min(1.0, world.hero.hp / world.hero.max_hp))
    pygame.draw.rect(screen, HP_FRONT, (bar.x, bar.y, round(bar.width * fraction), bar.height))
    pygame.draw.rect(screen, TEXT_COLOR, bar, 1)
    label = f"HP {max(0, math.ceil(world.hero.hp))}/{math.ceil(world.hero.max_hp)}"
    screen.blit(font.render(label, True, TEXT_COLOR), (bar.right + 8, bar.y - 2))

    xp_bar = pygame.Rect(12, 40, 180, 10)
    pygame.draw.rect(screen, XP_BACK, xp_bar)
    fraction = max(0.0, min(1.0, world.xp / world.xp_needed))
    pygame.draw.rect(screen, XP_FRONT, (xp_bar.x, xp_bar.y, round(xp_bar.width * fraction), 10))
    pygame.draw.rect(screen, TEXT_COLOR, xp_bar, 1)
    screen.blit(font.render(f"Lv {world.level}", True, TEXT_COLOR), (xp_bar.right + 8, xp_bar.y - 8))

    timer = f"{format_time(world.time)} / {format_time(world.config['game']['victory_time'])}"
    timer_surface = font.render(timer, True, TEXT_COLOR)
    screen.blit(timer_surface, (width - 12 - timer_surface.get_width(), 30))


def draw_loadout(screen, world, font, width, height):
    entries = [f"{short} {level}" for short, level in world.loadout_entries()]
    rows = [entries[index : index + 3] for index in range(0, len(entries), 3)]
    line_height = 26
    band_height = len(rows) * line_height + 12
    shade = pygame.Surface((width, band_height), pygame.SRCALPHA)
    shade.fill(LOADOUT_BACK)
    screen.blit(shade, (0, height - band_height))
    y = height - band_height + 8
    for row in rows:
        screen.blit(font.render("   ".join(row), True, TEXT_COLOR), (12, y))
        y += line_height


def draw_overlay(screen, width, height, title, lines, title_colour, big_font, font):
    shade = pygame.Surface((width, height), pygame.SRCALPHA)
    shade.fill(OVERLAY)
    screen.blit(shade, (0, 0))
    title_surface = big_font.render(title, True, title_colour)
    screen.blit(title_surface, title_surface.get_rect(center=(width / 2, height / 2 - 100)))
    y = height / 2 - 10
    for line in lines:
        surface = font.render(line, True, TEXT_COLOR)
        screen.blit(surface, surface.get_rect(center=(width / 2, y)))
        y += 36


def draw_level_up(screen, world, width, height, big_font, card_font, font, mouse_pos):
    shade = pygame.Surface((width, height), pygame.SRCALPHA)
    shade.fill(OVERLAY)
    screen.blit(shade, (0, 0))
    title = big_font.render("LEVEL UP", True, ACCENT_COLOR)
    screen.blit(title, title.get_rect(center=(width / 2, 110)))
    hint = font.render("Choose one card", True, TEXT_DIM)
    screen.blit(hint, hint.get_rect(center=(width / 2, 148)))

    hover = card_at(mouse_pos, width, len(world.cards))
    for index, (card, rect) in enumerate(zip(world.cards, card_rects(width, len(world.cards)))):
        colour = CARD_HOVER if index == hover else CARD_COLOR
        pygame.draw.rect(screen, colour, rect)
        pygame.draw.rect(screen, CARD_EDGE, rect, 2)
        screen.blit(card_font.render(card.name, True, TEXT_COLOR), (rect.x + 18, rect.y + 12))
        level_text = f"Lv {card.level}" if card.level is not None else "Instant"
        screen.blit(font.render(level_text, True, ACCENT_COLOR), (rect.x + 18, rect.y + 52))
        y = rect.y + 88
        for line in wrap_text(font, card.text, rect.width - 36):
            screen.blit(font.render(line, True, TEXT_DIM), (rect.x + 18, y))
            y += 26


async def main():
    config = rules.load_config()
    width = config["screen"]["width"]
    height = config["screen"]["height"]
    fps = config["screen"]["fps"]

    pygame.mixer.pre_init(22050, -16, 1, 512)
    pygame.init()
    pygame.display.set_caption("Night Survivors")
    screen = pygame.display.set_mode((width, height))
    clock = pygame.time.Clock()
    sounds = {}
    if pygame.mixer.get_init():
        pygame.mixer.set_num_channels(16)
        for name in SOUND_NAMES:
            sound = load_sound(name)
            sound.set_volume(SOUND_VOLUMES[name])
            sounds[name] = sound
    else:
        print("No sound device found: playing without sound.")
    big_font = pygame.font.Font(None, 64)
    card_font = pygame.font.Font(None, 38)
    font = pygame.font.Font(None, 30)
    small_font = pygame.font.Font(None, 24)
    images = {
        "hero": load_image("hero.png"),
        "gem": load_image("gem.png"),
        "sword": load_image("sword.png"),
        "floor": load_image("floor.png"),
    }
    for key, stats in config["enemies"].items():
        image = load_image(stats["picture"])
        scale = stats.get("draw_scale", 1.0)
        if scale != 1.0:
            image = pygame.transform.scale(
                image,
                (round(image.get_width() * scale), round(image.get_height() * scale)),
            )
        images[key] = image

    world = rules.World(config)
    mouse_pos = None
    touch_id = None
    touch_pos = None
    accumulator = 0.0
    running = True
    damage_numbers = []
    flashes = []
    shake_timer = 0.0
    hit_sound_timer = 0.0

    while running:
        frame_seconds = min(clock.tick(fps) / 1000.0, 0.25)
        restarted = False

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_p and world.state == "playing":
                    world.paused = not world.paused
                    accumulator = 0.0
            elif event.type == pygame.MOUSEMOTION:
                if getattr(event, "touch", False) or touch_id is not None:
                    continue
                mouse_pos = event.pos
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if world.state in ("game_over", "victory"):
                    world.reset()
                    restarted = True
                    mouse_pos = None
                    touch_id = None
                    touch_pos = None
                elif getattr(event, "touch", False) or touch_id is not None:
                    continue
                elif world.state == "level_up":
                    index = card_at(event.pos, width, len(world.cards))
                    if index is not None:
                        world.choose_card(index)
                    mouse_pos = None
                    touch_pos = None
                else:
                    mouse_pos = event.pos
            elif event.type == pygame.FINGERDOWN:
                if world.state in ("game_over", "victory"):
                    world.reset()
                    restarted = True
                    mouse_pos = None
                    touch_id = None
                    touch_pos = None
                elif world.state == "level_up":
                    tap = (event.x * width, event.y * height)
                    index = card_at(tap, width, len(world.cards))
                    if index is not None:
                        world.choose_card(index)
                    mouse_pos = None
                    touch_id = None
                    touch_pos = None
                else:
                    touch_id = event.finger_id
                    touch_pos = (event.x * width, event.y * height)
                    mouse_pos = None
            elif event.type == pygame.FINGERMOTION:
                if event.finger_id == touch_id:
                    touch_pos = (event.x * width, event.y * height)
            elif event.type == pygame.FINGERUP:
                if event.finger_id == touch_id:
                    touch_id = None
                    touch_pos = None
                    world.clear_pointer()

        if restarted:
            accumulator = 0.0
            damage_numbers.clear()
            flashes.clear()
            shake_timer = 0.0
            hit_sound_timer = 0.0

        if world.state == "playing" and not world.paused:
            if touch_pos is not None:
                world.set_pointer(*screen_to_world(world, width, height, *touch_pos))
            elif mouse_pos is not None:
                world.set_pointer(*screen_to_world(world, width, height, *mouse_pos))
            accumulator += frame_seconds
            while accumulator >= rules.STEP:
                world.update()
                accumulator -= rules.STEP

            age_effects(damage_numbers, flashes, frame_seconds)
            shake_timer = max(0.0, shake_timer - frame_seconds)
            hit_sound_timer = max(0.0, hit_sound_timer - frame_seconds)

            for event in world.events:
                kind = event[0]
                if kind == "damage":
                    damage_numbers.append(
                        FloatingNumber(event[1], event[2] - 18, event[3])
                    )
                    if hit_sound_timer <= 0:
                        play_sound(sounds, "hit")
                        hit_sound_timer = HIT_SOUND_GAP
                elif kind == "death":
                    flashes.append(Flash(event[1], event[2], event[3]))
                elif kind == "gem":
                    play_sound(sounds, "gem")
                elif kind == "level_up":
                    play_sound(sounds, "level_up")
                elif kind == "hurt":
                    play_sound(sounds, "hurt")
                    shake_timer = SHAKE_TIME
                elif kind == "end":
                    play_sound(sounds, "end")
            world.events.clear()
        else:
            accumulator = 0.0

        cam_x, cam_y = camera_origin(world, width, height)
        if shake_timer > 0 and world.state == "playing" and not world.paused:
            power = SHAKE_STRENGTH * shake_timer / SHAKE_TIME
            cam_x += random.uniform(-power, power)
            cam_y += random.uniform(-power, power)

        screen.fill(BACKGROUND)
        draw_scene(screen, world, images, cam_x, cam_y, width, height)
        draw_effects(screen, damage_numbers, flashes, cam_x, cam_y, small_font)
        draw_hud(screen, world, font, width)
        draw_loadout(screen, world, small_font, width, height)

        if world.state == "game_over":
            draw_overlay(
                screen,
                width,
                height,
                "GAME OVER",
                [
                    f"Time {format_time(world.time)}",
                    f"Kills {world.kills}",
                    f"Lv {world.level}",
                    "Click or tap to play again",
                ],
                HP_FRONT,
                big_font,
                font,
            )
        elif world.state == "victory":
            draw_overlay(
                screen,
                width,
                height,
                "VICTORY",
                [
                    f"Time {format_time(world.time)}",
                    f"Kills {world.kills}",
                    f"Lv {world.level}",
                    "Click or tap to play again",
                ],
                VICTORY_COLOR,
                big_font,
                font,
            )
        elif world.state == "level_up":
            draw_level_up(screen, world, width, height, big_font, card_font, font, mouse_pos)
        elif world.paused:
            draw_overlay(
                screen,
                width,
                height,
                "PAUSED",
                ["Press P to continue"],
                TEXT_COLOR,
                big_font,
                font,
            )

        pygame.display.flip()
        await asyncio.sleep(0)

    pygame.quit()


asyncio.run(main())
