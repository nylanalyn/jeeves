# modules/roll.py
# Dice rolling, coin flips, and other fair gambling implements.

import random
import re
from typing import Any

from .base import SimpleCommandModule


def setup(bot: Any) -> "Roll":
    return Roll(bot)


class Roll(SimpleCommandModule):
    name = "roll"
    version = "1.0.0"
    description = "Roll dice of any denomination, flip coins, and other fair gambling."

    COIN_SIDES = ["heads", "tails"]


    def __init__(self, bot: Any) -> None:
        super().__init__(bot)

    def _register_commands(self) -> None:
        self.register_command(
            r'^\s*!roll(?:\s+(.+))?\s*$',
            self._cmd_roll,
            name="roll",
            description="Roll dice. !roll, !roll 2d6, !roll d20, !roll 2d6+3",
        )
        self.register_command(
            r'^\s*!flip\s*$',
            self._cmd_flip,
            name="flip",
            description="Flip a coin.",
        )
        

    def _cmd_roll(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        spec = match.group(1) if match.group(1) else "d20"
        spec = spec.strip().lower()

        # Parse NdX+Y or dX
        m = re.match(r"^(?:(\d+)d(\d+)|d(\d+))(?:\s*([+-])\s*(\d+))?\s*$", spec)
        if not m:
            self.safe_reply(
                connection,
                event,
                f"{self.bot.title_for(username)}, I'm not familiar with that. Try !roll, !roll 2d6, or !roll d20+3.",
            )
            return True

        if m.group(3):
            # dX shorthand
            num = 1
            sides = int(m.group(3))
        else:
            num = min(int(m.group(1)), 1000)  # Cap at 1000 dice
            sides = int(m.group(2))

        if sides < 1 or sides > 16777216:  # 2^24, generous
            self.safe_reply(
                connection,
                event,
                f"{self.bot.title_for(username)}, I've no idea how to count that high.",
            )
            return True

        modifier = 0
        if m.group(4):
            modifier = int(m.group(5)) * (1 if m.group(4) == "+" else -1)

        if num == 1:
            result = random.randint(1, sides) + modifier
            if m.group(4):
                self.safe_reply(
                    connection,
                    event,
                    f"{self.bot.title_for(username)} rolls a **d{sides} {m.group(4)}{abs(modifier)}: {result}."
                )
            else:
                self.safe_reply(
                    connection,
                    event,
                    f"{self.bot.title_for(username)} rolls a **d{sides}: {result}."
                )
        else:
            rolls = [random.randint(1, sides) for _ in range(num)]
            total = sum(rolls) + modifier
            roll_str = ", ".join(str(r) for r in rolls)
            if len(roll_str) > 200:
                # For massive rolls, just show total
                if m.group(4):
                    self.safe_reply(
                        connection,
                        event,
                        f"{self.bot.title_for(username)} rolls **{num}d{sides} {m.group(4)}{abs(modifier)}: total **{total}**."
                    )
                else:
                    self.safe_reply(
                        connection,
                        event,
                        f"{self.bot.title_for(username)} rolls **{num}d{sides}: total **{total}**."
                    )
            else:
                if len(rolls) > 8:
                    detail = f"({roll_str})"
                else:
                    detail = f"({roll_str}) = {total}"
                if m.group(4):
                    self.safe_reply(
                        connection,
                        event,
                        f"{self.bot.title_for(username)} rolls **{num}d{sides} {m.group(4)}{abs(modifier)}: {detail}."
                    )
                else:
                    self.safe_reply(
                        connection,
                        event,
                        f"{self.bot.title_for(username)} rolls **{num}d{sides}: {detail}."
                    )
        return True

    def _cmd_flip(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        result = random.choice(self.COIN_SIDES)
        if result == "heads":
            self.safe_reply(
                connection,
                event,
                f"{self.bot.title_for(username)} flips a coin: **{result}**. "
                f"Ah, the regal visage of authority."
            )
        else:
            self.safe_reply(
                connection,
                event,
                f"{self.bot.title_for(username)} flips a coin: **{result}**. "
                f"The humble side, but no less important."
            )
        return True
