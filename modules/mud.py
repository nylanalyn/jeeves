import random
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .base import SimpleCommandModule

TEXT_DIR = Path(__file__).resolve().parent / "mud_text"
SUMMARY_FILE = TEXT_DIR / "room_summaries.txt"
DETAIL_FILE = TEXT_DIR / "room_details.txt"
MONSTERS_FILE = TEXT_DIR / "monsters.txt"
WEAPONS_FILE = TEXT_DIR / "weapons.txt"

# Combat constants
MONSTER_SPAWN_CHANCE = 0.30  # 30% chance when entering new rooms
COMMAND_COOLDOWN = 2.0  # seconds between commands
COMMAND_EXPIRE = 30.0  # commands expire after 30 seconds
FLEE_SUCCESS_CHANCE = 0.50  # 50% chance to flee

# XP thresholds for leveling: 50, 150, 300, 500, 800...
XP_THRESHOLDS = [50, 150, 300, 500, 800, 1200, 1700, 2300, 3000, 4000]

# Default party state
DEFAULT_PARTY = {
    "hp": 50,
    "max_hp": 50,
    "ac": 10,
    "xp": 0,
    "level": 1,
    "weapon": {"name": "Bare Fists", "attack_bonus": 0, "damage_dice": "1d2"},
    "inventory": [],
    "gold": 0,
}

# Fumble messages for natural 1
FUMBLE_MESSAGES = [
    "You trip over your own feet!",
    "Your weapon slips from your grasp!",
    "You swing wildly and hit nothing but air!",
    "You stub your toe on a rock!",
    "Your attack goes embarrassingly wide!",
]

# Critical hit messages
CRIT_MESSAGES = [
    "A devastating blow!",
    "Right in the weak spot!",
    "A masterful strike!",
    "The monster reels from the impact!",
]

DIRECTIONS: Dict[str, Tuple[int, int]] = {
    "n": (0, -1),
    "e": (1, 0),
    "s": (0, 1),
    "w": (-1, 0),
}
DIR_NAMES = {"n": "north", "e": "east", "s": "south", "w": "west"}
DIR_OPPOSITE = {"n": "s", "e": "w", "s": "n", "w": "e"}
DIR_ORDER = ["n", "e", "s", "w"]

COUNT_WORDS = {
    0: "no",
    1: "one",
    2: "two",
    3: "three",
    4: "four",
}


def roll_dice(dice_str: str) -> Tuple[int, List[int]]:
    """Roll dice in NdX+Y format. Returns (total, individual_rolls)."""
    match = re.match(r"(\d+)d(\d+)(?:\+(\d+))?", dice_str)
    if not match:
        return (1, [1])
    num_dice = int(match.group(1))
    sides = int(match.group(2))
    bonus = int(match.group(3)) if match.group(3) else 0
    rolls = [random.randint(1, sides) for _ in range(num_dice)]
    return (sum(rolls) + bonus, rolls)


def roll_d20() -> int:
    """Roll a single d20."""
    return random.randint(1, 20)


def setup(bot: Any) -> "Mud":
    return Mud(bot)


class Mud(SimpleCommandModule):
    name = "mud"
    version = "1.0.0"
    description = "A tiny shared MUD map with rooms, exits, and look."

    def __init__(self, bot: Any) -> None:
        super().__init__(bot)
        self.room_summaries = self._load_text_list(
            SUMMARY_FILE,
            [
                "a cramped room",
                "a wide stone hall",
                "a narrow passage",
                "a round chamber",
                "a low ceilinged room",
                "a bright atrium",
                "a damp cavern",
                "a tidy parlor",
                "a dusty library",
                "a tiled vestibule",
            ],
        )
        self.room_details = self._load_text_list(
            DETAIL_FILE,
            [
                "The walls are solid brick, moss grows up each seam. The vibe is comforting.",
                "A steady drip echoes from the ceiling, keeping time with your footsteps.",
                "Someone carved small constellations into the stone. They sparkle with grit.",
                "The floor is cold and smooth, like it was polished by a thousand boots.",
                "A faint scent of cedar hangs in the air, warm against the stone.",
                "Dust motes drift lazily in a narrow beam of light.",
                "The room hums softly, as if the walls are quietly thinking.",
                "You notice a chalk mark: a tiny star, drawn and redrawn.",
                "The corners are piled with old crates, none of them labeled.",
                "A small breeze curls around your ankles and disappears.",
            ],
        )
        self.monsters = self._load_monsters()
        self.weapons = self._load_weapons()
        self.set_state("maps", self.get_state("maps", {}))
        self.set_state("parties", self.get_state("parties", {}))
        self.set_state("command_queues", self.get_state("command_queues", {}))
        self.save_state()

    def _register_commands(self) -> None:
        self.register_command(
            r"^\s*!mud(?:\s+(.+))?\s*$",
            self._cmd_mud,
            name="mud",
            description="Explore the dungeon, fight monsters, and collect loot.",
        )

    def _load_text_list(self, path: Path, fallback: List[str]) -> List[str]:
        if not path.exists():
            return fallback[:]
        try:
            lines: List[str] = []
            for line in path.read_text(encoding="utf-8").splitlines():
                text = line.strip()
                if not text or text.startswith("#"):
                    continue
                lines.append(text)
            return lines if lines else fallback[:]
        except Exception as exc:
            self.log_debug(f"Failed reading {path}: {exc}")
            return fallback[:]

    def _load_monsters(self) -> List[Dict[str, Any]]:
        """Load monster definitions from file."""
        monsters = []
        fallback = [
            {"name": "Irritated Rat", "hp": 8, "ac": 8, "attack_bonus": 1,
             "damage_dice": "1d4", "xp": 10, "loot_chance": 30, "loot_type": "gold"},
        ]
        if not MONSTERS_FILE.exists():
            return fallback
        try:
            for line in MONSTERS_FILE.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("|")
                if len(parts) >= 7:
                    monsters.append({
                        "name": parts[0],
                        "hp": int(parts[1]),
                        "ac": int(parts[2]),
                        "attack_bonus": int(parts[3]),
                        "damage_dice": parts[4],
                        "xp": int(parts[5]),
                        "loot_chance": int(parts[6]),
                        "loot_type": parts[7] if len(parts) > 7 else "gold",
                    })
            return monsters if monsters else fallback
        except Exception as exc:
            self.log_debug(f"Failed loading monsters: {exc}")
            return fallback

    def _load_weapons(self) -> List[Dict[str, Any]]:
        """Load weapon definitions from file."""
        weapons = []
        fallback = [
            {"name": "Bare Fists", "attack_bonus": 0, "damage_dice": "1d2", "rarity": 1},
        ]
        if not WEAPONS_FILE.exists():
            return fallback
        try:
            for line in WEAPONS_FILE.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("|")
                if len(parts) >= 3:
                    weapons.append({
                        "name": parts[0],
                        "attack_bonus": int(parts[1]),
                        "damage_dice": parts[2],
                        "rarity": int(parts[3]) if len(parts) > 3 else 1,
                    })
            return weapons if weapons else fallback
        except Exception as exc:
            self.log_debug(f"Failed loading weapons: {exc}")
            return fallback

    def _get_party(self, channel: str) -> Dict[str, Any]:
        """Get or create party state for a channel."""
        parties = self.get_state("parties", {})
        if channel not in parties:
            parties[channel] = dict(DEFAULT_PARTY)
            parties[channel]["inventory"] = []
            self.set_state("parties", parties)
            self.save_state()
        return parties[channel]

    def _save_party(self, channel: str, party: Dict[str, Any]) -> None:
        """Save party state."""
        parties = self.get_state("parties", {})
        parties[channel] = party
        self.set_state("parties", parties)
        self.save_state()

    def _get_command_queue(self, channel: str) -> Dict[str, Any]:
        """Get command queue for a channel."""
        queues = self.get_state("command_queues", {})
        if channel not in queues:
            queues[channel] = {"pending": [], "last_action_time": 0}
            self.set_state("command_queues", queues)
        return queues[channel]

    def _save_command_queue(self, channel: str, queue: Dict[str, Any]) -> None:
        """Save command queue."""
        queues = self.get_state("command_queues", {})
        queues[channel] = queue
        self.set_state("command_queues", queues)
        self.save_state()

    def _check_queue_cooldown(self, channel: str, username: str, command: str) -> Optional[str]:
        """Check if command can execute. Returns None if OK, or message if on cooldown."""
        queue = self._get_command_queue(channel)
        now = time.time()

        # Check cooldown
        time_since_last = now - queue["last_action_time"]
        if time_since_last < COMMAND_COOLDOWN:
            wait_time = COMMAND_COOLDOWN - time_since_last
            return f"Cooldown! Wait {wait_time:.1f}s before the next action."

        # Cooldown passed, allow command
        queue["last_action_time"] = now
        self._save_command_queue(channel, queue)
        return None

    def _spawn_monster(self, room: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Maybe spawn a monster in a room. Returns monster dict or None."""
        if random.random() > MONSTER_SPAWN_CHANCE:
            return None
        if not self.monsters:
            return None
        # Weight by inverse of HP for variety (weaker monsters more common)
        weights = [1.0 / (m["hp"] ** 0.5) for m in self.monsters]
        monster_template = random.choices(self.monsters, weights=weights, k=1)[0]
        return {
            "name": monster_template["name"],
            "hp": monster_template["hp"],
            "current_hp": monster_template["hp"],
            "ac": monster_template["ac"],
            "attack_bonus": monster_template["attack_bonus"],
            "damage_dice": monster_template["damage_dice"],
            "xp": monster_template["xp"],
            "loot_chance": monster_template["loot_chance"],
            "loot_type": monster_template["loot_type"],
        }

    def _generate_loot(self, monster: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Generate loot from a defeated monster."""
        if random.randint(1, 100) > monster["loot_chance"]:
            return None
        loot_type = monster["loot_type"]
        if loot_type == "gold":
            amount = random.randint(5, 20) + monster["xp"] // 5
            return {"type": "gold", "amount": amount}
        elif loot_type == "weapon":
            # Pick a random weapon, weighted by inverse rarity
            weapons = [w for w in self.weapons if w["name"] != "Bare Fists"]
            if not weapons:
                return {"type": "gold", "amount": random.randint(10, 30)}
            weights = [1.0 / w["rarity"] for w in weapons]
            weapon = random.choices(weapons, weights=weights, k=1)[0]
            return {"type": "weapon", "item": dict(weapon)}
        else:  # item
            items = ["Health Potion", "Torch", "Lucky Coin", "Shiny Gem", "Old Key"]
            return {"type": "item", "name": random.choice(items)}

    def _check_level_up(self, party: Dict[str, Any]) -> Optional[str]:
        """Check if party levels up. Returns message if so."""
        current_level = party["level"]
        if current_level > len(XP_THRESHOLDS):
            return None
        threshold = XP_THRESHOLDS[current_level - 1] if current_level <= len(XP_THRESHOLDS) else float("inf")
        if party["xp"] >= threshold:
            party["level"] += 1
            party["max_hp"] += 10
            party["hp"] = party["max_hp"]
            party["ac"] += 1
            return f"LEVEL UP! Party is now level {party['level']}! +10 Max HP, +1 AC, fully healed!"
        return None

    def _party_wipe(self, channel: str, party: Dict[str, Any]) -> str:
        """Handle party death - respawn at entrance."""
        mud_map = self._get_channel_map(channel)
        # Find entrance (room 1)
        mud_map["current_room_id"] = 1
        maps = self.get_state("maps", {})
        maps[channel] = mud_map
        self.set_state("maps", maps)
        self.save_state()

        # Reset party HP to half
        party["hp"] = party["max_hp"] // 2
        self._save_party(channel, party)
        return "The party has fallen! You respawn at the dungeon entrance with half HP."

    def _cmd_mud(
        self,
        connection: Any,
        event: Any,
        msg: str,
        username: str,
        match: re.Match,
    ) -> bool:
        channel = event.target
        if not self.is_enabled(channel):
            return False

        allowed_channel = self.get_config_value(
            "channel", default=self.bot.primary_channel
        )
        if allowed_channel and channel != allowed_channel:
            return False

        raw_arg = (match.group(1) or "").strip()
        arg = raw_arg.lower()
        parts = arg.split(None, 1)
        cmd = parts[0] if parts else ""
        cmd_arg = parts[1] if len(parts) > 1 else ""

        # Help command (no cooldown)
        if cmd == "help":
            self._cmd_help(connection, event)
            return True

        # Status command (no cooldown)
        if cmd == "status":
            self._cmd_status(connection, event, channel)
            return True

        # Inventory command (no cooldown)
        if cmd in {"inv", "inventory", "i"}:
            self._cmd_inventory(connection, event, channel)
            return True

        # Look command (no cooldown)
        if not cmd or cmd in {"look", "l"}:
            self._reply_look(connection, event, channel)
            return True

        # Commands that use the cooldown queue
        queued_commands = {"attack", "a", "flee", "run", "take", "get", "equip", "n", "e", "s", "w", "north", "east", "south", "west"}
        if cmd in queued_commands:
            queue_msg = self._check_queue_cooldown(channel, username, arg)
            if queue_msg:
                self.safe_reply(connection, event, queue_msg)
                return True

        # Attack command
        if cmd in {"attack", "a"}:
            self._cmd_attack(connection, event, channel, username)
            return True

        # Flee command
        if cmd in {"flee", "run"}:
            self._cmd_flee(connection, event, channel)
            return True

        # Take command
        if cmd in {"take", "get"}:
            self._cmd_take(connection, event, channel, cmd_arg)
            return True

        # Equip command
        if cmd == "equip":
            self._cmd_equip(connection, event, channel, cmd_arg)
            return True

        # Movement commands
        direction = self._normalize_direction(cmd)
        if direction:
            mud_map = self._get_channel_map(channel)
            current_room = self._get_room(mud_map, mud_map["current_room_id"])

            # Can't move if monster is present
            if current_room.get("monster"):
                monster = current_room["monster"]
                self.safe_reply(
                    connection, event,
                    f"A {monster['name']} blocks your path! Fight or flee!"
                )
                return True

            if direction not in current_room["exits"]:
                dir_name = DIR_NAMES[direction]
                self.safe_reply(connection, event, f"There is no exit to the {dir_name}.")
                return True

            summary = self._move(channel, direction)
            self.safe_reply(connection, event, summary)
            return True

        self.safe_reply(
            connection, event,
            "Unknown command. Try: n/e/s/w, attack, flee, take, equip, inv, status, help"
        )
        return True

    def _normalize_direction(self, arg: str) -> Optional[str]:
        if arg in DIRECTIONS:
            return arg
        aliases = {
            "north": "n",
            "east": "e",
            "south": "s",
            "west": "w",
        }
        return aliases.get(arg)

    def _cmd_help(self, connection: Any, event: Any) -> None:
        """Show help message."""
        help_text = (
            "MUD Commands: n/e/s/w (move), look, attack, flee, "
            "take <item>, equip <weapon>, inv, status, help"
        )
        self.safe_reply(connection, event, help_text)

    def _cmd_status(self, connection: Any, event: Any, channel: str) -> None:
        """Show party status."""
        party = self._get_party(channel)
        weapon = party["weapon"]
        next_level_xp = XP_THRESHOLDS[party["level"] - 1] if party["level"] <= len(XP_THRESHOLDS) else "MAX"
        status = (
            f"Party Lv{party['level']} | HP: {party['hp']}/{party['max_hp']} | "
            f"AC: {party['ac']} | XP: {party['xp']}/{next_level_xp} | "
            f"Gold: {party['gold']} | Weapon: {weapon['name']} ({weapon['damage_dice']})"
        )
        self.safe_reply(connection, event, status)

    def _cmd_inventory(self, connection: Any, event: Any, channel: str) -> None:
        """Show party inventory."""
        party = self._get_party(channel)
        if not party["inventory"]:
            self.safe_reply(connection, event, "Inventory is empty.")
            return
        items = []
        for item in party["inventory"]:
            if item.get("type") == "weapon":
                items.append(f"{item['name']} (+{item['attack_bonus']}, {item['damage_dice']})")
            else:
                items.append(item.get("name", "Unknown item"))
        self.safe_reply(connection, event, f"Inventory: {', '.join(items)}")

    def _cmd_attack(self, connection: Any, event: Any, channel: str, username: str) -> None:
        """Attack the monster in the room."""
        mud_map = self._get_channel_map(channel)
        room = self._get_room(mud_map, mud_map["current_room_id"])
        party = self._get_party(channel)

        monster = room.get("monster")
        if not monster:
            self.safe_reply(connection, event, "There's nothing to attack here.")
            return

        weapon = party["weapon"]
        results = []

        # Player attack roll
        attack_roll = roll_d20()
        total_attack = attack_roll + weapon.get("attack_bonus", 0)

        if attack_roll == 1:
            # Fumble!
            results.append(f"{username} rolls a natural 1! {random.choice(FUMBLE_MESSAGES)}")
        elif attack_roll == 20 or total_attack >= monster["ac"]:
            # Hit (or crit)
            damage, rolls = roll_dice(weapon["damage_dice"])
            if attack_roll == 20:
                # Critical hit - double damage
                damage *= 2
                results.append(
                    f"{username} rolls a natural 20! CRITICAL HIT! "
                    f"{random.choice(CRIT_MESSAGES)} {damage} damage to {monster['name']}!"
                )
            else:
                results.append(
                    f"{username} rolls {attack_roll}+{weapon.get('attack_bonus', 0)}="
                    f"{total_attack} vs AC {monster['ac']}. Hit! "
                    f"{weapon['damage_dice']}={damage} damage to {monster['name']}!"
                )
            monster["current_hp"] -= damage

            # Check if monster is dead
            if monster["current_hp"] <= 0:
                results.append(f"The {monster['name']} is defeated! +{monster['xp']} XP!")
                party["xp"] += monster["xp"]

                # Check for loot
                loot = self._generate_loot(monster)
                if loot:
                    if loot["type"] == "gold":
                        party["gold"] += loot["amount"]
                        results.append(f"Found {loot['amount']} gold!")
                    elif loot["type"] == "weapon":
                        room.setdefault("items", []).append({
                            "type": "weapon",
                            "name": loot["item"]["name"],
                            "attack_bonus": loot["item"]["attack_bonus"],
                            "damage_dice": loot["item"]["damage_dice"],
                        })
                        results.append(f"The monster dropped a {loot['item']['name']}!")
                    else:
                        room.setdefault("items", []).append({
                            "type": "item",
                            "name": loot["name"],
                        })
                        results.append(f"Found a {loot['name']}!")

                # Check level up
                level_msg = self._check_level_up(party)
                if level_msg:
                    results.append(level_msg)

                # Remove monster from room
                room["monster"] = None
                self._save_map(channel, mud_map)
                self._save_party(channel, party)
                self.safe_reply(connection, event, " ".join(results))
                return
        else:
            results.append(
                f"{username} rolls {attack_roll}+{weapon.get('attack_bonus', 0)}="
                f"{total_attack} vs AC {monster['ac']}. Miss!"
            )

        # Monster counterattack
        monster_roll = roll_d20()
        monster_total = monster_roll + monster["attack_bonus"]

        if monster_roll == 1:
            results.append(f"The {monster['name']} fumbles its attack!")
        elif monster_roll == 20 or monster_total >= party["ac"]:
            m_damage, _ = roll_dice(monster["damage_dice"])
            if monster_roll == 20:
                m_damage *= 2
                results.append(
                    f"The {monster['name']} rolls a 20! CRITICAL! {m_damage} damage to party!"
                )
            else:
                results.append(
                    f"The {monster['name']} ({monster['current_hp']} HP) hits for {m_damage} damage!"
                )
            party["hp"] -= m_damage

            # Check party wipe
            if party["hp"] <= 0:
                results.append(self._party_wipe(channel, party))
                room["monster"] = None
                self._save_map(channel, mud_map)
                self.safe_reply(connection, event, " ".join(results))
                return
        else:
            results.append(f"The {monster['name']} misses!")

        self._save_map(channel, mud_map)
        self._save_party(channel, party)
        self.safe_reply(connection, event, " ".join(results))

    def _cmd_flee(self, connection: Any, event: Any, channel: str) -> None:
        """Attempt to flee from combat."""
        mud_map = self._get_channel_map(channel)
        room = self._get_room(mud_map, mud_map["current_room_id"])
        party = self._get_party(channel)

        monster = room.get("monster")
        if not monster:
            self.safe_reply(connection, event, "There's nothing to flee from!")
            return

        if random.random() < FLEE_SUCCESS_CHANCE:
            # Success - pick a random exit
            exits = list(room["exits"].keys())
            if exits:
                direction = random.choice(exits)
                room["monster"] = None  # Monster stays but combat ends
                self._save_map(channel, mud_map)
                summary = self._move(channel, direction)
                self.safe_reply(connection, event, f"You flee {DIR_NAMES[direction]}! {summary}")
            else:
                self.safe_reply(connection, event, "Nowhere to run!")
        else:
            # Failed flee - monster gets a free hit
            monster_roll = roll_d20()
            monster_total = monster_roll + monster["attack_bonus"]
            if monster_total >= party["ac"]:
                damage, _ = roll_dice(monster["damage_dice"])
                party["hp"] -= damage
                result = f"Failed to flee! The {monster['name']} hits you for {damage} as you turn!"
                if party["hp"] <= 0:
                    result += " " + self._party_wipe(channel, party)
                    room["monster"] = None
                    self._save_map(channel, mud_map)
                self._save_party(channel, party)
                self.safe_reply(connection, event, result)
            else:
                self.safe_reply(
                    connection, event,
                    f"Failed to flee! The {monster['name']} swings but misses!"
                )

    def _cmd_take(self, connection: Any, event: Any, channel: str, item_name: str) -> None:
        """Pick up an item from the room."""
        mud_map = self._get_channel_map(channel)
        room = self._get_room(mud_map, mud_map["current_room_id"])
        party = self._get_party(channel)

        items = room.get("items", [])
        if not items:
            self.safe_reply(connection, event, "There's nothing here to take.")
            return

        # If no item specified, take first item
        if not item_name:
            item = items[0]
        else:
            # Find item by name (case insensitive partial match)
            item = None
            for i in items:
                if item_name in i.get("name", "").lower():
                    item = i
                    break
            if not item:
                self.safe_reply(connection, event, f"No item matching '{item_name}' here.")
                return

        items.remove(item)
        room["items"] = items
        party["inventory"].append(item)

        self._save_map(channel, mud_map)
        self._save_party(channel, party)
        self.safe_reply(connection, event, f"Picked up {item['name']}.")

    def _cmd_equip(self, connection: Any, event: Any, channel: str, weapon_name: str) -> None:
        """Equip a weapon from inventory."""
        party = self._get_party(channel)

        if not weapon_name:
            self.safe_reply(connection, event, "Equip what? Try: !mud equip <weapon name>")
            return

        # Find weapon in inventory
        weapon = None
        for item in party["inventory"]:
            if item.get("type") == "weapon" and weapon_name in item["name"].lower():
                weapon = item
                break

        if not weapon:
            self.safe_reply(connection, event, f"No weapon matching '{weapon_name}' in inventory.")
            return

        # Swap weapons
        old_weapon = party["weapon"]
        party["weapon"] = {
            "name": weapon["name"],
            "attack_bonus": weapon["attack_bonus"],
            "damage_dice": weapon["damage_dice"],
        }
        party["inventory"].remove(weapon)

        # Put old weapon in inventory (unless bare fists)
        if old_weapon["name"] != "Bare Fists":
            party["inventory"].append({
                "type": "weapon",
                "name": old_weapon["name"],
                "attack_bonus": old_weapon["attack_bonus"],
                "damage_dice": old_weapon["damage_dice"],
            })

        self._save_party(channel, party)
        self.safe_reply(
            connection, event,
            f"Equipped {weapon['name']} (+{weapon['attack_bonus']}, {weapon['damage_dice']})."
        )

    def _save_map(self, channel: str, mud_map: Dict[str, Any]) -> None:
        """Save the map state."""
        maps = self.get_state("maps", {})
        maps[channel] = mud_map
        self.set_state("maps", maps)
        self.save_state()

    def _reply_look(self, connection: Any, event: Any, channel: str) -> None:
        mud_map = self._get_channel_map(channel)
        room = self._get_room(mud_map, mud_map["current_room_id"])
        exits = self._format_exits(room["exits"])
        detail = room["detail"]
        parts = [detail]

        # Show monster if present
        monster = room.get("monster")
        if monster:
            parts.append(f"A {monster['name']} ({monster['current_hp']}/{monster['hp']} HP) blocks your way!")

        # Show items on ground
        items = room.get("items", [])
        if items:
            item_names = [i.get("name", "something") for i in items]
            parts.append(f"On the ground: {', '.join(item_names)}.")

        parts.append(f"Exits: {exits}.")
        self.safe_reply(connection, event, " ".join(parts))

    def _get_channel_map(self, channel: str) -> Dict[str, Any]:
        maps = self.get_state("maps", {})
        mud_map = maps.get(channel)
        if mud_map:
            return mud_map

        mud_map = {
            "current_room_id": 1,
            "next_room_id": 2,
            "rooms": {},
            "coords": {},
        }
        room_id = self._create_room(mud_map, (0, 0), entry_dir=None)
        mud_map["current_room_id"] = room_id
        maps[channel] = mud_map
        self.set_state("maps", maps)
        self.save_state()
        return mud_map

    def _get_room(self, mud_map: Dict[str, Any], room_id: int) -> Dict[str, Any]:
        return mud_map["rooms"][str(room_id)]

    def _coords_key(self, coords: Tuple[int, int]) -> str:
        return f"{coords[0]},{coords[1]}"

    def _create_room(
        self, mud_map: Dict[str, Any], coords: Tuple[int, int], entry_dir: Optional[str]
    ) -> int:
        room_id = mud_map["next_room_id"] if mud_map["rooms"] else 1
        mud_map["next_room_id"] = max(mud_map["next_room_id"], room_id + 1)

        exits = {}
        if entry_dir:
            exits[DIR_OPPOSITE[entry_dir]] = None
        available = [d for d in DIR_ORDER if d not in exits]
        if available:
            extra_count = random.randint(0 if entry_dir else 1, len(available))
            for direction in random.sample(available, extra_count):
                exits[direction] = None

        room = {
            "id": room_id,
            "coords": [coords[0], coords[1]],
            "summary": random.choice(self.room_summaries),
            "detail": random.choice(self.room_details),
            "exits": exits,
        }
        mud_map["rooms"][str(room_id)] = room
        mud_map["coords"][self._coords_key(coords)] = room_id
        return room_id

    def _move(self, channel: str, direction: str) -> str:
        mud_map = self._get_channel_map(channel)
        current_id = mud_map["current_room_id"]
        current_room = self._get_room(mud_map, current_id)

        x, y = current_room["coords"]
        dx, dy = DIRECTIONS[direction]
        new_coords = (x + dx, y + dy)
        coord_key = self._coords_key(new_coords)

        is_new_room = False
        dest_id = mud_map["coords"].get(coord_key)
        if dest_id is None:
            dest_id = self._create_room(mud_map, new_coords, entry_dir=direction)
            is_new_room = True
        current_room["exits"][direction] = dest_id

        dest_room = self._get_room(mud_map, dest_id)
        opposite_dir = DIR_OPPOSITE[direction]
        existing = dest_room["exits"].get(opposite_dir)
        if existing is None:
            dest_room["exits"][opposite_dir] = current_id
        elif existing != current_id:
            self.log_debug(
                f"Room {dest_id} opposite exit {opposite_dir} already set to {existing}"
            )

        # Spawn monster in new rooms (30% chance)
        if is_new_room and not dest_room.get("monster"):
            monster = self._spawn_monster(dest_room)
            if monster:
                dest_room["monster"] = monster

        mud_map["current_room_id"] = dest_id
        maps = self.get_state("maps", {})
        maps[channel] = mud_map
        self.set_state("maps", maps)
        self.save_state()

        exits = self._format_exits(dest_room["exits"])
        exit_count = len(dest_room["exits"])
        count_word = COUNT_WORDS.get(exit_count, str(exit_count))
        parts = [f"You enter {dest_room['summary']} with {count_word} exits, {exits}."]

        # Alert about monster
        monster = dest_room.get("monster")
        if monster:
            parts.append(f"A {monster['name']} appears! ({monster['current_hp']} HP)")

        # Show items
        items = dest_room.get("items", [])
        if items:
            item_names = [i.get("name", "something") for i in items]
            parts.append(f"You see: {', '.join(item_names)}.")

        return " ".join(parts)

    def _format_exits(self, exits: Dict[str, Optional[int]]) -> str:
        names = [DIR_NAMES[d] for d in DIR_ORDER if d in exits]
        if not names:
            return "none"
        if len(names) == 1:
            return names[0]
        if len(names) == 2:
            return f"{names[0]} and {names[1]}"
        return ", ".join(names[:-1]) + f", and {names[-1]}"
