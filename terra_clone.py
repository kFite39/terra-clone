"""
TERRA CLONE - a 2D sandbox survival game (Terraria-style) built with Pygame.

Controls
  A / D or arrows ... move          W / UP / SPACE ... jump
  Left mouse ........ mine blocks / attack zombies (hold it down)
  Right mouse ....... place the selected block
  E or F ............ also place the selected block (aim with the mouse)
  1-0 or mouse wheel  select hotbar slot
  C ................. open / close crafting (then press 1-7 to craft)
  H ................. show / hide help       F5 ... save      F9 ... load
  ESC or P .......... pause menu (resume, save, load, controls, save & quit)

Run with:  python3 terra_clone.py       (needs: pip install pygame)
"""
import json
import math
import os
import random
import sys

import pygame

# ----------------------------------------------------------------- settings
WIDTH, HEIGHT, FPS = 960, 640, 60
T = 24                              # tile size in pixels
WORLD_W, WORLD_H = 240, 130         # world size in tiles
GRAVITY, MAX_FALL = 0.45, 12
JUMP_SPEED, MOVE_SPEED = 7.6, 3.2
REACH = 5.5 * T                     # how far the player can mine / place
DAY_LENGTH = 7200                   # frames in one full day (2 minutes)
SAVE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "terra_save.json")

# ----------------------------------------------------------------- tile data
AIR, GRASS, DIRT, STONE, WOOD, LEAVES, COAL, IRON, PLANKS, BEDROCK = range(10)

# hard = frames to mine with bare hands, tier = pickaxe tier needed, drop = item name
TILES = {
    GRASS:   dict(color=(112, 78, 48),  hard=25,   tier=0, drop="dirt",   solid=True),
    DIRT:    dict(color=(121, 85, 52),  hard=25,   tier=0, drop="dirt",   solid=True),
    STONE:   dict(color=(122, 122, 130), hard=90,  tier=1, drop="stone",  solid=True),
    WOOD:    dict(color=(105, 70, 35),  hard=40,   tier=0, drop="wood",   solid=False),
    LEAVES:  dict(color=(52, 128, 58),  hard=10,   tier=0, drop=None,     solid=False),
    COAL:    dict(color=(122, 122, 130), hard=100, tier=1, drop="coal",   solid=True, ore=(25, 25, 30)),
    IRON:    dict(color=(122, 122, 130), hard=160, tier=2, drop="iron",   solid=True, ore=(224, 170, 130)),
    PLANKS:  dict(color=(172, 126, 72), hard=50,   tier=0, drop="planks", solid=True),
    BEDROCK: dict(color=(35, 35, 42),   hard=None, tier=99, drop=None,    solid=True),
}
PLACEABLE = {"dirt": DIRT, "stone": STONE, "wood": WOOD, "planks": PLANKS}
ICON_TILE = {"dirt": DIRT, "stone": STONE, "wood": WOOD, "planks": PLANKS, "coal": COAL, "iron": IRON}

# tool name -> (tier, mining speed multiplier) and sword damage
PICKAXES = {None: (0, 1.0), "wood": (1, 2.0), "stone": (2, 3.5), "iron": (3, 5.5)}
SWORDS = {None: 5, "wood": 9, "stone": 13, "iron": 20}
TOOL_COLORS = {"wood": (170, 125, 70), "stone": (170, 170, 180), "iron": (235, 200, 170)}
TOOL_ORDER = ["iron", "stone", "wood"]

RECIPES = [
    dict(name="4 Planks",      cost={"wood": 1},                          give=("item", "planks", 4)),
    dict(name="Wood Pickaxe",  cost={"planks": 6},                        give=("tool", "wood", "pick")),
    dict(name="Wood Sword",    cost={"planks": 5},                        give=("tool", "wood", "sword")),
    dict(name="Stone Pickaxe", cost={"stone": 8, "planks": 3},            give=("tool", "stone", "pick")),
    dict(name="Stone Sword",   cost={"stone": 6, "planks": 2},            give=("tool", "stone", "sword")),
    dict(name="Iron Pickaxe",  cost={"iron": 10, "coal": 3, "planks": 3}, give=("tool", "iron", "pick")),
    dict(name="Iron Sword",    cost={"iron": 8, "coal": 2, "planks": 2},  give=("tool", "iron", "sword")),
]


def shade(color, d):
    return tuple(max(0, min(255, v + d)) for v in color)


# ----------------------------------------------------------------- the world
class World:
    """Holds the tile grid: tiles[x][y] is a tile id. Also generates and saves terrain."""

    def __init__(self, seed=None):
        self.w, self.h = WORLD_W, WORLD_H
        self.seed = seed if seed is not None else random.randrange(10 ** 6)
        self.tiles = [[AIR] * self.h for _ in range(self.w)]
        self.surf = [0] * self.w          # surface height of every column
        self.generate()

    def get(self, x, y):
        if x < 0 or x >= self.w or y >= self.h:
            return BEDROCK                # the world edges act like solid walls
        if y < 0:
            return AIR
        return self.tiles[x][y]

    def set(self, x, y, tile):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.tiles[x][y] = tile

    def solid(self, x, y):
        t = self.get(x, y)
        return t != AIR and TILES[t]["solid"]

    def surface_y(self, x):
        for y in range(self.h):
            if self.solid(x, y):
                return y
        return self.h - 1

    def generate(self):
        rng = random.Random(self.seed)
        w, h = self.w, self.h
        p = [rng.uniform(0, 6.28) for _ in range(3)]
        for x in range(w):
            height = 40 + 6 * math.sin(x * 0.03 + p[0]) + 3 * math.sin(x * 0.09 + p[1]) \
                + 1.5 * math.sin(x * 0.23 + p[2])
            s = int(height)
            self.surf[x] = s
            dirt_depth = 4 + rng.randint(0, 2)
            for y in range(s, h):
                if y == s:
                    self.tiles[x][y] = GRASS
                elif y < s + dirt_depth:
                    self.tiles[x][y] = DIRT
                else:
                    self.tiles[x][y] = STONE
            self.tiles[x][h - 1] = BEDROCK

        # caves: wandering "worms" that carve tunnels
        for _ in range(45):
            x = rng.randint(5, w - 5)
            y = float(rng.randint(self.surf[x] + 12, h - 8))
            x = float(x)
            ang = rng.uniform(0, 6.28)
            r = rng.choice([1, 1, 2])
            for _ in range(rng.randint(40, 120)):
                ang += rng.uniform(-0.5, 0.5)
                x = max(3.0, min(w - 4.0, x + math.cos(ang)))
                y += math.sin(ang) * 0.7
                for dx in range(-r, r + 1):
                    for dy in range(-r, r + 1):
                        tx, ty = int(x) + dx, int(y) + dy
                        if dx * dx + dy * dy <= r * r + 1 and 0 <= tx < w \
                                and self.surf[tx] + 6 < ty < h - 1:
                            self.tiles[tx][ty] = AIR

        # ore veins: coal is common and shallow, iron is rarer and deeper
        for ore, count, min_depth in ((COAL, 130, 8), (IRON, 80, 22)):
            for _ in range(count):
                x = rng.randint(2, w - 3)
                y = rng.randint(self.surf[x] + min_depth, h - 3)
                for _ in range(rng.randint(3, 8)):
                    if self.get(x, y) == STONE:
                        self.tiles[x][y] = ore
                    x = max(1, min(w - 2, x + rng.randint(-1, 1)))
                    y = max(1, min(h - 3, y + rng.randint(-1, 1)))

        # trees
        x = 4
        while x < w - 6:
            x += rng.randint(4, 9)
            if x < w - 4 and self.tiles[x][self.surf[x]] == GRASS:
                top = self.surf[x] - rng.randint(4, 6)
                for ly in range(top - 2, top + 1):
                    for lx in range(x - 2, x + 3):
                        if self.tiles[lx][ly] == AIR and abs(lx - x) + (top - ly) < 4:
                            self.tiles[lx][ly] = LEAVES
                for ty in range(top, self.surf[x]):
                    self.tiles[x][ty] = WOOD

    def to_dict(self):
        return {"seed": self.seed, "surf": self.surf,
                "tiles": [bytes(col).hex() for col in self.tiles]}

    @classmethod
    def from_dict(cls, data):
        world = cls.__new__(cls)
        world.w, world.h = WORLD_W, WORLD_H
        world.seed = data["seed"]
        world.surf = data["surf"]
        world.tiles = [list(bytes.fromhex(col)) for col in data["tiles"]]
        if len(world.tiles) != WORLD_W or any(len(c) != WORLD_H for c in world.tiles):
            raise ValueError("save file does not match this version")
        return world


# ----------------------------------------------------------------- entities
class Entity:
    """Anything with a position, velocity and tile collisions (player, zombies)."""

    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h
        self.vx = self.vy = self.kb = 0.0
        self.on_ground = False
        self.hit_wall = False

    @property
    def rect(self):
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    @property
    def cx(self):
        return self.x + self.w / 2

    @property
    def cy(self):
        return self.y + self.h / 2

    def physics(self, world):
        self.vy = min(self.vy + GRAVITY, MAX_FALL)
        self.hit_wall = False
        self.x += self.vx + self.kb
        self.kb *= 0.85
        self._resolve(world, horizontal=True)
        self.on_ground = False
        self.y += self.vy
        self._resolve(world, horizontal=False)

    def _resolve(self, world, horizontal):
        move = self.vx + self.kb if horizontal else self.vy
        for ty in range(int(self.y // T), int((self.y + self.h - 0.01) // T) + 1):
            for tx in range(int(self.x // T), int((self.x + self.w - 0.01) // T) + 1):
                if not world.solid(tx, ty):
                    continue
                if horizontal:
                    self.x = tx * T - self.w if move > 0 else (tx + 1) * T
                    self.kb = 0
                    self.hit_wall = True
                elif move > 0:
                    self.y = ty * T - self.h
                    self.on_ground = True
                    self.vy = 0
                else:
                    self.y = (ty + 1) * T
                    self.vy = 0
                return


class Player(Entity):
    def __init__(self, world):
        super().__init__(0, 0, 18, 40)
        self.inv = [None] * 10          # hotbar slots: [item_name, count] or None
        self.tools = set()              # e.g. {"wood_pick", "stone_sword"}
        self.selected = 0
        self.health = 100
        self.invuln = 0
        self.attack_cd = 0
        self.respawn(world)

    def respawn(self, world):
        tx = world.w // 2
        self.x, self.y = tx * T + 3, world.surface_y(tx) * T - self.h - 1
        self.vx = self.vy = self.kb = 0
        self.health = 100
        self.invuln = 90

    # --- inventory helpers
    def count(self, item):
        return sum(s[1] for s in self.inv if s and s[0] == item)

    def add(self, item, n=1):
        for s in self.inv:
            if s and s[0] == item:
                s[1] += n
                return True
        for i, s in enumerate(self.inv):
            if s is None:
                self.inv[i] = [item, n]
                return True
        return False                    # inventory full

    def remove(self, item, n):
        for i, s in enumerate(self.inv):
            if s and s[0] == item:
                s[1] -= n
                if s[1] <= 0:
                    self.inv[i] = None
                return

    def best(self, kind):
        for name in TOOL_ORDER:
            if f"{name}_{kind}" in self.tools:
                return name
        return None


class Zombie(Entity):
    def __init__(self, x, y):
        super().__init__(x, y, 18, 38)
        self.hp = 30
        self.speed = random.uniform(0.9, 1.5)
        self.flash = 0

    def update(self, world, player):
        self.vx = self.speed if player.cx > self.cx else -self.speed
        if self.hit_wall and self.on_ground:
            self.vy = -JUMP_SPEED       # hop over obstacles
        self.flash = max(0, self.flash - 1)
        self.physics(world)


class Chip:
    """A tiny particle that flies out when a block breaks."""

    def __init__(self, x, y, color):
        self.x, self.y, self.color = x, y, color
        self.vx, self.vy = random.uniform(-2, 2), random.uniform(-4, -1)
        self.life = random.randint(15, 30)

    def update(self):
        self.vy += 0.3
        self.x += self.vx
        self.y += self.vy
        self.life -= 1


# ----------------------------------------------------------------- the game
class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Terra Clone")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont(None, 24)
        self.big = pygame.font.SysFont(None, 48)
        self.small = pygame.font.SysFont(None, 20)
        self.tiny = pygame.font.SysFont(None, 16)
        self.tex = self.make_textures()
        self.icons = {name: pygame.transform.scale(self.tex[t][0], (28, 28)) for name, t in ICON_TILE.items()}
        self.dark = pygame.Surface((WIDTH, HEIGHT))
        self.crack = pygame.Surface((T, T), pygame.SRCALPHA)
        self.msg, self.msg_timer = "", 0
        self.show_help, self.crafting = False, False
        self.paused, self.pause_view, self.menu_index = False, "menu", 0
        self.overlay = pygame.Surface((WIDTH, HEIGHT))
        self.overlay.set_alpha(150)
        self.help_timer = 60 * 12
        if not self.load():
            self.new_game()

    # ---------- setup / saving
    def new_game(self):
        self.world = World()
        self.player = Player(self.world)
        self.zombies, self.chips = [], []
        self.time = int(DAY_LENGTH * 0.05)
        self.kills = 0
        self.reset_runtime()

    def reset_runtime(self):
        self.zombies, self.chips = [], []
        self.mine_target, self.mine_prog = None, 0.0
        self.place_cd = self.spawn_cd = self.regen = 0

    def save(self):
        p = self.player
        data = {"world": self.world.to_dict(), "inv": p.inv, "tools": sorted(p.tools),
                "pos": [p.x, p.y], "health": p.health, "time": self.time, "kills": self.kills}
        try:
            with open(SAVE_FILE, "w") as f:
                json.dump(data, f)
            self.say("Game saved")
        except OSError:
            self.say("Could not save the game")

    def load(self):
        try:
            with open(SAVE_FILE) as f:
                data = json.load(f)
            self.world = World.from_dict(data["world"])
            self.player = Player(self.world)
            self.player.inv = data["inv"]
            self.player.tools = set(data["tools"])
            self.player.x, self.player.y = data["pos"]
            self.player.health = data["health"]
            self.time, self.kills = data["time"], data["kills"]
            self.reset_runtime()
            self.say("Game loaded")
            return True
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def make_textures(self):
        """Draw every tile type once (4 slightly different variants each)."""
        tex = {}
        for tid, info in TILES.items():
            variants = []
            for v in range(4):
                rng = random.Random(tid * 10 + v)
                s = pygame.Surface((T, T), pygame.SRCALPHA)
                if tid == WOOD:                       # trunk: see-through sides
                    pygame.draw.rect(s, info["color"], (7, 0, 10, T))
                    pygame.draw.rect(s, shade(info["color"], -25), (7, 0, 3, T))
                else:
                    s.fill(info["color"])
                    for _ in range(18):               # speckled noise
                        px, py = rng.randrange(0, T, 2), rng.randrange(0, T, 2)
                        pygame.draw.rect(s, shade(info["color"], rng.randint(-16, 16)), (px, py, 2, 2))
                if "ore" in info:
                    for _ in range(6):
                        pygame.draw.rect(s, info["ore"], (rng.randint(2, T - 6), rng.randint(2, T - 6), 4, 4))
                if tid == GRASS:
                    pygame.draw.rect(s, (70, 160, 60), (0, 0, T, 6))
                    for gx in range(0, T, 4):
                        pygame.draw.rect(s, (90, 185, 75), (gx, 5, 2, rng.randint(1, 3)))
                if tid == PLANKS:
                    for ly in range(0, T, 8):
                        pygame.draw.line(s, shade(info["color"], -40), (0, ly), (T, ly))
                if tid == BEDROCK:
                    pygame.draw.rect(s, (20, 20, 25), (0, 0, T, T), 2)
                variants.append(s)
            tex[tid] = variants
        return tex

    def say(self, text, frames=150):
        self.msg, self.msg_timer = text, frames

    # ---------- time of day
    @property
    def daylight(self):
        """1.0 at noon, 0.0 at midnight."""
        return (math.cos(2 * math.pi * (self.time % DAY_LENGTH) / DAY_LENGTH) + 1) / 2

    # ---------- crafting
    def can_craft(self, r):
        p = self.player
        if r["give"][0] == "tool" and f"{r['give'][1]}_{r['give'][2]}" in p.tools:
            return False
        return all(p.count(item) >= n for item, n in r["cost"].items())

    def craft(self, index):
        if index >= len(RECIPES):
            return
        r = RECIPES[index]
        if not self.can_craft(r):
            self.say("Not enough materials")
            return
        for item, n in r["cost"].items():
            self.player.remove(item, n)
        if r["give"][0] == "item":
            self.player.add(r["give"][1], r["give"][2])
        else:
            self.player.tools.add(f"{r['give'][1]}_{r['give'][2]}")
        self.say(f"Crafted {r['name']}")

    # ---------- update
    def update(self):
        p, world = self.player, self.world
        self.time += 1
        keys = pygame.key.get_pressed()
        mx, my = pygame.mouse.get_pos()
        buttons = pygame.mouse.get_pressed()

        self.cam_x = int(max(0, min(world.w * T - WIDTH, p.cx - WIDTH / 2)))
        self.cam_y = int(max(0, min(world.h * T - HEIGHT, p.cy - HEIGHT / 2)))
        wx, wy = mx + self.cam_x, my + self.cam_y
        tx, ty = int(wx // T), int(wy // T)
        in_reach = math.hypot(tx * T + T / 2 - p.cx, ty * T + T / 2 - p.cy) <= REACH
        self.target = (tx, ty, in_reach)

        # movement
        dx = (keys[pygame.K_RIGHT] or keys[pygame.K_d]) - (keys[pygame.K_LEFT] or keys[pygame.K_a])
        p.vx = dx * MOVE_SPEED
        if (keys[pygame.K_UP] or keys[pygame.K_w] or keys[pygame.K_SPACE]) and p.on_ground:
            p.vy = -JUMP_SPEED
        p.physics(world)
        if p.y > world.h * T:
            p.respawn(world)
        p.invuln = max(0, p.invuln - 1)
        p.attack_cd = max(0, p.attack_cd - 1)
        self.place_cd = max(0, self.place_cd - 1)

        # left mouse: attack a zombie or mine a block
        mining = False
        if buttons[0] and not self.crafting:
            target_zombie = next((z for z in self.zombies if z.rect.collidepoint(wx, wy)
                                  and math.hypot(z.cx - p.cx, z.cy - p.cy) <= REACH + 20), None)
            if target_zombie:
                if p.attack_cd == 0:
                    p.attack_cd = 22
                    target_zombie.hp -= SWORDS[p.best("sword")]
                    target_zombie.flash = 8
                    target_zombie.kb = 6 if target_zombie.cx > p.cx else -6
                    target_zombie.vy = -3
            elif in_reach:
                mining = self.mine(tx, ty)
        if not mining:
            self.mine_target, self.mine_prog = None, 0.0

        # right mouse: place a block
        place_pressed = buttons[2] or keys[pygame.K_e] or keys[pygame.K_f]
        if place_pressed and not self.crafting and in_reach and self.place_cd == 0:
            self.place(tx, ty)

        # zombies
        self.spawn_zombies()
        for z in self.zombies[:]:
            z.update(world, p)
            if self.daylight > 0.6 and z.y // T < world.surf[min(world.w - 1, max(0, int(z.cx // T)))] + 3 \
                    and self.time % 30 == 0:
                z.hp -= 3                # zombies burn in daylight
            if z.rect.colliderect(p.rect) and p.invuln == 0:
                p.health -= 10
                p.invuln = 45
                p.kb = 7 if p.cx > z.cx else -7
                p.vy = -4
            if z.hp <= 0:
                self.kills += 1
                self.zombies.remove(z)
            elif abs(z.x - p.x) > 70 * T or z.y > world.h * T:
                self.zombies.remove(z)

        # health regen / death
        self.regen += 1
        if self.regen >= 150 and p.health < 100:
            p.health += 1
            self.regen = 0
        if p.health <= 0:
            p.respawn(world)
            self.say("You died! Respawning at the spawn point...", 240)

        for c in self.chips[:]:
            c.update()
            if c.life <= 0:
                self.chips.remove(c)
        if self.msg_timer > 0:
            self.msg_timer -= 1
        if self.help_timer > 0:
            self.help_timer -= 1

    def mine(self, tx, ty):
        """Mine the block under the cursor. Returns True while mining continues."""
        world, p = self.world, self.player
        tile = world.get(tx, ty)
        if tile == AIR:
            return False
        info = TILES[tile]
        tier, speed = PICKAXES[p.best("pick")]
        if info["hard"] is None:
            return False
        if tier < info["tier"]:
            if self.mine_target != (tx, ty):
                self.say("You need a better pickaxe for that!")
                self.mine_target = (tx, ty)
            return False
        if self.mine_target != (tx, ty):
            self.mine_target, self.mine_prog = (tx, ty), 0.0
        self.mine_prog += speed / info["hard"]
        if self.mine_prog >= 1:
            world.set(tx, ty, AIR)
            if info["drop"] and not p.add(info["drop"]):
                self.say("Inventory full!")
            for _ in range(8):
                self.chips.append(Chip(tx * T + T / 2, ty * T + T / 2, info["color"]))
            self.mine_target, self.mine_prog = None, 0.0
        return True

    def place(self, tx, ty):
        world, p = self.world, self.player
        slot = p.inv[p.selected]
        if not slot or slot[0] not in PLACEABLE or world.get(tx, ty) != AIR:
            return
        block = pygame.Rect(tx * T, ty * T, T, T)
        if block.colliderect(p.rect) or any(block.colliderect(z.rect) for z in self.zombies):
            return
        if not any(world.get(tx + a, ty + b) != AIR for a, b in ((1, 0), (-1, 0), (0, 1), (0, -1))):
            return                       # blocks must touch another block
        world.set(tx, ty, PLACEABLE[slot[0]])
        p.remove(slot[0], 1)
        self.place_cd = 6

    def spawn_zombies(self):
        p, world = self.player, self.world
        self.spawn_cd -= 1
        if self.spawn_cd > 0 or len(self.zombies) >= 6:
            return
        self.spawn_cd = random.randint(120, 240)
        ptx = int(p.cx // T)
        depth = p.cy // T - world.surf[min(world.w - 1, max(0, ptx))]
        if self.daylight < 0.35:         # night: zombies walk in from the sides
            tx = max(1, min(world.w - 2, ptx + random.choice([-1, 1]) * random.randint(18, 26)))
            self.zombies.append(Zombie(tx * T + 3, (world.surface_y(tx) - 2) * T))
        elif depth > 15:                 # caves are dangerous even in daytime
            for _ in range(25):
                tx, ty = ptx + random.randint(-22, 22), int(p.cy // T) + random.randint(-12, 12)
                if math.hypot(tx - ptx, ty - p.cy // T) > 10 and world.get(tx, ty) == AIR \
                        and world.get(tx, ty - 1) == AIR and world.solid(tx, ty + 1):
                    self.zombies.append(Zombie(tx * T + 3, ty * T - 20))
                    break

    # ---------- drawing
    def draw_world(self):
        world, p = self.world, self.player
        d = self.daylight
        sky = tuple(int(n + (day - n) * d) for n, day in zip((10, 12, 35), (110, 175, 235)))
        self.screen.fill(sky)

        # sun and moon
        ang = 2 * math.pi * (self.time % DAY_LENGTH) / DAY_LENGTH
        sx = WIDTH / 2 + math.sin(ang) * WIDTH * 0.45
        sy = 380 - 320 * math.cos(ang)
        pygame.draw.circle(self.screen, (255, 235, 140), (int(sx), int(sy)), 26)
        pygame.draw.circle(self.screen, (225, 225, 240), (int(WIDTH - sx), int(760 - sy)), 20)

        # tiles
        x0, x1 = max(0, self.cam_x // T), min(world.w - 1, (self.cam_x + WIDTH) // T)
        y0, y1 = max(0, self.cam_y // T), min(world.h - 1, (self.cam_y + HEIGHT) // T)
        for tx in range(x0, x1 + 1):
            col = world.tiles[tx]
            for ty in range(y0, y1 + 1):
                t = col[ty]
                px, py = tx * T - self.cam_x, ty * T - self.cam_y
                if t == AIR:
                    if ty > world.surf[tx] + 2:       # cave background wall
                        pygame.draw.rect(self.screen, (44, 34, 30), (px, py, T, T))
                else:
                    self.screen.blit(self.tex[t][(tx * 7 + ty * 13) % 4], (px, py))

        # mining crack + cursor outline
        tx, ty, in_reach = self.target
        if self.mine_target and self.mine_prog > 0:
            self.crack.fill((0, 0, 0, int(150 * self.mine_prog)))
            self.screen.blit(self.crack, (self.mine_target[0] * T - self.cam_x, self.mine_target[1] * T - self.cam_y))
        outline = (255, 255, 255) if in_reach else (200, 70, 70)
        pygame.draw.rect(self.screen, outline, (tx * T - self.cam_x, ty * T - self.cam_y, T, T), 1)

        for z in self.zombies:
            self.draw_zombie(z)
        self.draw_player()
        for c in self.chips:
            pygame.draw.rect(self.screen, c.color, (int(c.x - self.cam_x), int(c.y - self.cam_y), 3, 3))

        # darkness: night time, and getting darker the deeper you dig
        depth = max(0, p.cy / T - world.surf[min(world.w - 1, max(0, int(p.cx // T)))])
        darkness = max((1 - d) * 0.6, min(0.75, depth / 60))
        self.dark.fill((4, 4, 18))
        self.dark.set_alpha(int(255 * darkness))
        self.screen.blit(self.dark, (0, 0))

    def draw_player(self):
        p = self.player
        if p.invuln % 6 >= 3:
            return                       # blink while invulnerable
        x, y = int(p.x - self.cam_x), int(p.y - self.cam_y)
        mx = pygame.mouse.get_pos()[0]
        face = 1 if mx > x + p.w / 2 else -1
        pygame.draw.rect(self.screen, (50, 50, 120), (x + 2, y + 26, 14, 14))     # legs
        pygame.draw.rect(self.screen, (60, 110, 200), (x, y + 12, p.w, 16))       # body
        pygame.draw.rect(self.screen, (240, 200, 160), (x + 2, y, 14, 13))        # head
        pygame.draw.rect(self.screen, (30, 30, 30), (x + (10 if face > 0 else 5), y + 4, 3, 3))
        if pygame.mouse.get_pressed()[0] and not self.crafting:   # tool swing
            swing = math.sin(self.time * 0.5) * 8
            tool = p.best("pick") or "wood"
            pygame.draw.line(self.screen, TOOL_COLORS[tool], (x + p.w / 2, y + 18),
                             (x + p.w / 2 + face * 22, y + 10 + swing), 4)

    def draw_zombie(self, z):
        x, y = int(z.x - self.cam_x), int(z.y - self.cam_y)
        body = (255, 255, 255) if z.flash else (80, 140, 80)
        pygame.draw.rect(self.screen, (50, 60, 100), (x + 2, y + 25, 14, 13))
        pygame.draw.rect(self.screen, body, (x, y + 11, z.w, 15))
        pygame.draw.rect(self.screen, body, (x + 2, y, 14, 12))
        pygame.draw.rect(self.screen, (220, 40, 40), (x + 5, y + 4, 3, 3))
        pygame.draw.rect(self.screen, (220, 40, 40), (x + 11, y + 4, 3, 3))
        if z.hp < 30:
            pygame.draw.rect(self.screen, (60, 60, 60), (x, y - 7, z.w, 3))
            pygame.draw.rect(self.screen, (220, 60, 60), (x, y - 7, int(z.w * max(0, z.hp) / 30), 3))

    def text(self, msg, pos, color=(255, 255, 255), font=None, center=False):
        font = font or self.font
        img = font.render(msg, True, color)
        shadow = font.render(msg, True, (0, 0, 0))
        rect = img.get_rect(center=pos) if center else img.get_rect(topleft=pos)
        self.screen.blit(shadow, rect.move(1, 1))
        self.screen.blit(img, rect)

    def draw_hud(self):
        p = self.player
        # health
        pygame.draw.rect(self.screen, (50, 20, 20), (12, 12, 204, 18))
        pygame.draw.rect(self.screen, (210, 50, 60), (14, 14, 2 * max(0, p.health), 14))
        self.text(f"HP {p.health}", (20, 14), font=self.small)
        self.text(f"Pickaxe: {(p.best('pick') or 'hands').title()}   Sword: {(p.best('sword') or 'fists').title()}",
                  (12, 36))
        self.text(f"Zombies slain: {self.kills}", (12, 58))

        # clock
        d = self.daylight
        phase = "Night" if d < 0.35 else ("Day" if d > 0.65 else "Dusk/Dawn")
        depth = int(p.cy / T - self.world.surf[min(self.world.w - 1, max(0, int(p.cx // T)))])
        self.text(f"Day {self.time // DAY_LENGTH + 1} - {phase}", (WIDTH - 190, 12))
        self.text(f"Depth: {max(0, depth)} m", (WIDTH - 190, 36))

        # hotbar
        x0 = WIDTH // 2 - 5 * 46
        for i in range(10):
            r = pygame.Rect(x0 + i * 46, HEIGHT - 56, 42, 42)
            pygame.draw.rect(self.screen, (30, 30, 40), r)
            pygame.draw.rect(self.screen, (255, 220, 80) if i == p.selected else (110, 110, 120), r, 3 if i == p.selected else 1)
            slot = p.inv[i]
            if slot:
                self.screen.blit(self.icons[slot[0]], (r.x + 7, r.y + 5))
                self.text(str(slot[1]), (r.x + 4, r.y + 28), font=self.small)
            self.text(str((i + 1) % 10), (r.x + 3, r.y + 2), (180, 180, 190), self.tiny)

        if self.crafting:
            self.draw_crafting()
        if self.msg_timer > 0:
            self.text(self.msg, (WIDTH // 2, 90), (255, 240, 140), self.big, center=True)
        if self.help_timer > 0 or self.show_help:
            lines = ["WASD / arrows: move & jump    Left click: mine / attack    Right click or E / F: place block",
                     "C: crafting    1-0 / wheel: choose slot    F5: save    F9: load    H: hide this    ESC: pause menu",
                     "Tip: punch trees (wood) -> craft planks -> craft a pickaxe. Zombies come out at night!"]
            for i, line in enumerate(lines):
                self.text(line, (WIDTH // 2, 130 + i * 24), center=True)

    def draw_crafting(self):
        p = self.player
        panel = pygame.Rect(16, 90, 360, 36 + len(RECIPES) * 28)
        pygame.draw.rect(self.screen, (25, 25, 35), panel)
        pygame.draw.rect(self.screen, (200, 200, 210), panel, 2)
        self.text("CRAFTING  (press the number)", (panel.x + 12, panel.y + 8), (255, 220, 80))
        for i, r in enumerate(RECIPES):
            owned = r["give"][0] == "tool" and f"{r['give'][1]}_{r['give'][2]}" in p.tools
            ok = self.can_craft(r)
            color = (110, 110, 110) if owned else ((120, 230, 120) if ok else (230, 120, 120))
            cost = ", ".join(f"{n} {item}" for item, n in r["cost"].items())
            label = f"{i + 1}. {r['name']}  [{cost}]" + ("  (owned)" if owned else "")
            self.text(label, (panel.x + 12, panel.y + 36 + i * 28), color)

    # ---------- main loop
    PAUSE_ITEMS = ["Resume", "Save game", "Load game", "Controls", "Save & quit"]

    def menu_rects(self):
        return [pygame.Rect(WIDTH // 2 - 140, 230 + i * 56, 280, 44) for i in range(len(self.PAUSE_ITEMS))]

    def set_paused(self, value):
        self.paused = value
        self.pause_view, self.menu_index = "menu", 0
        self.crafting = False

    def activate_menu_item(self, index):
        choice = self.PAUSE_ITEMS[index]
        if choice == "Resume":
            self.set_paused(False)
        elif choice == "Save game":
            self.save()
        elif choice == "Load game":
            if self.load():
                self.set_paused(False)
            else:
                self.say("No save file found")
        elif choice == "Controls":
            self.pause_view = "controls"
        elif choice == "Save & quit":
            self.quit()

    def handle_pause_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_p):
                if self.pause_view == "controls":
                    self.pause_view = "menu"
                else:
                    self.set_paused(False)
            elif self.pause_view == "controls":
                if event.key in (pygame.K_RETURN, pygame.K_BACKSPACE):
                    self.pause_view = "menu"
            elif event.key in (pygame.K_UP, pygame.K_w):
                self.menu_index = (self.menu_index - 1) % len(self.PAUSE_ITEMS)
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self.menu_index = (self.menu_index + 1) % len(self.PAUSE_ITEMS)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.activate_menu_item(self.menu_index)
        elif event.type == pygame.MOUSEMOTION and self.pause_view == "menu":
            for i, r in enumerate(self.menu_rects()):
                if r.collidepoint(event.pos):
                    self.menu_index = i
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.pause_view == "controls":
                self.pause_view = "menu"
            else:
                for i, r in enumerate(self.menu_rects()):
                    if r.collidepoint(event.pos):
                        self.activate_menu_item(i)
                        break

    def handle_event(self, event):
        p = self.player
        if event.type == pygame.QUIT:
            self.quit()
        elif self.paused:
            self.handle_pause_event(event)
        elif event.type == pygame.MOUSEWHEEL:
            p.selected = (p.selected - event.y) % 10
        elif event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_p):
                self.set_paused(True)
            elif event.key == pygame.K_c:
                self.crafting = not self.crafting
            elif event.key == pygame.K_h:
                self.show_help = not self.show_help
                self.help_timer = 0
            elif event.key == pygame.K_F5:
                self.save()
            elif event.key == pygame.K_F9:
                if not self.load():
                    self.say("No save file found")
            elif pygame.K_0 <= event.key <= pygame.K_9:
                num = event.key - pygame.K_0
                if self.crafting:
                    if num >= 1:
                        self.craft(num - 1)
                else:
                    p.selected = (num - 1) % 10

    def draw_pause(self):
        self.overlay.fill((0, 0, 0))
        self.screen.blit(self.overlay, (0, 0))
        self.text("PAUSED", (WIDTH // 2, 150), (255, 220, 80), self.big, center=True)
        if self.pause_view == "controls":
            lines = ["A / D or arrows ..... move",
                     "W / Up / Space ...... jump",
                     "Left click .......... mine blocks / attack zombies (hold)",
                     "Right click, E or F . place the selected block",
                     "1-0 or mouse wheel .. choose hotbar slot",
                     "C ................... crafting (then press 1-7)",
                     "H ................... show / hide quick help",
                     "F5 / F9 ............. save / load",
                     "ESC or P ............ pause menu"]
            for i, line in enumerate(lines):
                self.text(line, (WIDTH // 2 - 230, 215 + i * 30))
            self.text("Press ESC or click to go back", (WIDTH // 2, 520), (200, 200, 210), center=True)
            return
        for i, (label, r) in enumerate(zip(self.PAUSE_ITEMS, self.menu_rects())):
            chosen = i == self.menu_index
            pygame.draw.rect(self.screen, (70, 70, 95) if chosen else (35, 35, 50), r, border_radius=6)
            pygame.draw.rect(self.screen, (255, 220, 80) if chosen else (110, 110, 125), r, 2, border_radius=6)
            self.text(label, r.center, (255, 255, 255) if chosen else (190, 190, 200), center=True)
        self.text("Up / Down + Enter, or use the mouse", (WIDTH // 2, 545), (170, 170, 185), center=True)
        if self.msg_timer > 0:
            self.text(self.msg, (WIDTH // 2, 580), (255, 240, 140), center=True)

    def quit(self):
        self.save()
        pygame.quit()
        sys.exit()

    def run(self):
        while True:
            for event in pygame.event.get():
                self.handle_event(event)
            if not self.paused:
                self.update()
            elif self.msg_timer > 0:
                self.msg_timer -= 1
            self.draw_world()
            self.draw_hud()
            if self.paused:
                self.draw_pause()
            pygame.display.flip()
            self.clock.tick(FPS)


if __name__ == "__main__":
    Game().run()
