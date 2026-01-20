import random
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .base import SimpleCommandModule

TEXT_DIR = Path(__file__).resolve().parent / "mud_text"
SUMMARY_FILE = TEXT_DIR / "room_summaries.txt"
DETAIL_FILE = TEXT_DIR / "room_details.txt"

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
        self.set_state("maps", self.get_state("maps", {}))
        self.save_state()

    def _register_commands(self) -> None:
        self.register_command(
            r"^\s*!mud(?:\s+(\S+))?\s*$",
            self._cmd_mud,
            name="mud",
            description="Move the shared MUD bot or look around.",
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

        arg = (match.group(1) or "").strip().lower()
        if not arg or arg in {"look", "l"}:
            self._reply_look(connection, event, channel)
            return True

        direction = self._normalize_direction(arg)
        if not direction:
            self.safe_reply(connection, event, "Valid directions are n, e, s, w.")
            return True

        mud_map = self._get_channel_map(channel)
        current_room = self._get_room(mud_map, mud_map["current_room_id"])
        if direction not in current_room["exits"]:
            dir_name = DIR_NAMES[direction]
            self.safe_reply(connection, event, f"There is no exit to the {dir_name}.")
            return True

        summary = self._move(channel, direction)
        self.safe_reply(connection, event, summary)
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

    def _reply_look(self, connection: Any, event: Any, channel: str) -> None:
        mud_map = self._get_channel_map(channel)
        room = self._get_room(mud_map, mud_map["current_room_id"])
        exits = self._format_exits(room["exits"])
        detail = room["detail"]
        response = f"{detail} Exits: {exits}."
        self.safe_reply(connection, event, response)

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

        dest_id = mud_map["coords"].get(coord_key)
        if dest_id is None:
            dest_id = self._create_room(mud_map, new_coords, entry_dir=direction)
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

        mud_map["current_room_id"] = dest_id
        maps = self.get_state("maps", {})
        maps[channel] = mud_map
        self.set_state("maps", maps)
        self.save_state()

        exits = self._format_exits(dest_room["exits"])
        exit_count = len(dest_room["exits"])
        count_word = COUNT_WORDS.get(exit_count, str(exit_count))
        return f"You enter {dest_room['summary']} with {count_word} exits, {exits}."

    def _format_exits(self, exits: Dict[str, Optional[int]]) -> str:
        names = [DIR_NAMES[d] for d in DIR_ORDER if d in exits]
        if not names:
            return "none"
        if len(names) == 1:
            return names[0]
        if len(names) == 2:
            return f"{names[0]} and {names[1]}"
        return ", ".join(names[:-1]) + f", and {names[-1]}"
