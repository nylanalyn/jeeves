# modules/house.py
# A short, module-aware household report.

import inspect
import random
import re
from typing import Any, Callable, List, Optional

from .base import SimpleCommandModule


def setup(bot: Any) -> "House":
    return House(bot)


class House(SimpleCommandModule):
    name = "house"
    version = "1.0.0"
    description = "Provides a concise report on the currently loaded household services."

    STATUS_PRIORITY = ("wordle",)

    QUIET_LINES = [
        "The house is quiet at present.",
        "All appears orderly for the moment.",
        "There is little to report just now.",
    ]

    def _register_commands(self) -> None:
        self.register_command(
            r"^\s*!house\s*$",
            self._cmd_house,
            name="house",
            description="Show a short, module-aware household report.",
            cooldown=10.0,
        )

    def _call_hook(self, hook: Callable[..., Any], channel: str) -> Optional[str]:
        try:
            params = inspect.signature(hook).parameters
            if len(params) >= 1:
                result = hook(channel)
            else:
                result = hook()
        except Exception as exc:
            self.log_debug(f"house_status hook failed: {exc}")
            return None

        if not result:
            return None
        return str(result).strip()

    def _status_sort_key(self, module_name: str) -> tuple:
        if module_name in self.STATUS_PRIORITY:
            return (0, self.STATUS_PRIORITY.index(module_name), module_name)
        return (1, len(self.STATUS_PRIORITY), module_name)

    def _collect_status_lines(self, channel: str) -> List[str]:
        lines: List[str] = []
        for module_name, module in sorted(
            self.bot.pm.plugins.items(),
            key=lambda item: self._status_sort_key(item[0]),
        ):
            if module_name == self.name:
                continue
            hook = getattr(module, "house_status", None)
            if not callable(hook):
                continue
            line = self._call_hook(hook, channel)
            if line:
                lines.append(line)
        return lines

    def _loaded_services_line(self) -> str:
        hidden = {"admin", "base", "house", "hints", "help", "matrix_admin", "users", "welcome"}
        names = [
            name for name in sorted(self.bot.pm.plugins.keys())
            if name not in hidden and not name.startswith("_")
        ]
        if not names:
            return ""
        shown = ", ".join(names[:10])
        if len(names) > 10:
            shown += f", and {len(names) - 10} more"
        return f"Available services include {shown}."

    def _cmd_house(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        lines = self._collect_status_lines(event.target)
        if not lines:
            fallback = self._loaded_services_line()
            if fallback:
                lines = [random.choice(self.QUIET_LINES), fallback]
            else:
                lines = [random.choice(self.QUIET_LINES)]

        max_lines = int(self.get_config_value("max_lines", event.target, default=6) or 6)
        report = " ".join(lines[:max(1, max_lines)])
        self.safe_reply(connection, event, f"Household report: {report}")
        return True
