# modules/hints.py
# Rate-limited contextual hints contributed by loaded modules.

import inspect
import re
import time
from typing import Any, Callable, Optional

from .base import SimpleCommandModule


def setup(bot: Any) -> "Hints":
    return Hints(bot)


class Hints(SimpleCommandModule):
    name = "hints"
    version = "1.0.0"
    description = "Shares occasional contextual hints from loaded modules."

    def __init__(self, bot: Any) -> None:
        super().__init__(bot)
        self.set_state("last_channel_hint", self.get_state("last_channel_hint", {}))
        self.set_state("last_user_hint", self.get_state("last_user_hint", {}))
        self.save_state()

    def _register_commands(self) -> None:
        self.register_command(
            r"^\s*!hint\s*$",
            self._cmd_hint,
            name="hint",
            description="Show a useful hint for the currently loaded household.",
            cooldown=10.0,
        )

    def _call_hook(self, hook: Callable[..., Any], msg: str, username: str, channel: str) -> Optional[str]:
        try:
            params = inspect.signature(hook).parameters
            if len(params) >= 3:
                result = hook(msg, username, channel)
            elif len(params) == 2:
                result = hook(msg, username)
            elif len(params) == 1:
                result = hook(msg)
            else:
                result = hook()
        except Exception as exc:
            self.log_debug(f"contextual_hint hook failed: {exc}")
            return None

        if not result:
            return None
        return str(result).strip()

    def _find_hint(self, msg: str, username: str, channel: str) -> Optional[str]:
        for module_name, module in sorted(self.bot.pm.plugins.items()):
            if module_name == self.name:
                continue
            hook = getattr(module, "contextual_hint", None)
            if not callable(hook):
                continue
            hint = self._call_hook(hook, msg, username, channel)
            if hint:
                return hint
        return None

    def _cooldown_allows(self, username: str, channel: str) -> bool:
        now = time.time()
        channel_cooldown = float(self.get_config_value("channel_cooldown_seconds", channel, default=86400) or 86400)
        user_cooldown = float(self.get_config_value("user_cooldown_seconds", channel, default=604800) or 604800)

        last_channel = self.get_state("last_channel_hint", {})
        last_user = self.get_state("last_user_hint", {})
        user_id = self.bot.get_user_id(username)

        if now - float(last_channel.get(channel, 0) or 0) < channel_cooldown:
            return False
        if now - float(last_user.get(user_id, 0) or 0) < user_cooldown:
            return False
        return True

    def _record_hint(self, username: str, channel: str) -> None:
        now = time.time()
        last_channel = self.get_state("last_channel_hint", {})
        last_user = self.get_state("last_user_hint", {})
        last_channel[channel] = now
        last_user[self.bot.get_user_id(username)] = now
        self.set_state("last_channel_hint", last_channel)
        self.set_state("last_user_hint", last_user)
        self.save_state()

    def _cmd_hint(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        hint = self._find_hint("", username, event.target)
        if not hint:
            hint = "Use !welcome for a short tour of the currently loaded household services."
        self.safe_reply(connection, event, f"A brief note, if I may: {hint}")
        return True

    def on_ambient_message(self, connection: Any, event: Any, msg: str, username: str) -> bool:
        if not self.is_enabled(event.target):
            return False
        if msg.lstrip().startswith(("!", ",")):
            return False
        if not self.has_flavor_enabled(username):
            return False
        if not self._cooldown_allows(username, event.target):
            return False

        hint = self._find_hint(msg, username, event.target)
        if not hint:
            return False

        self.safe_reply(connection, event, f"A brief note, if I may: {hint}")
        self._record_hint(username, event.target)
        return False
