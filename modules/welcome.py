# modules/welcome.py
# Module-aware onboarding for the current household.

import inspect
import re
from typing import Any, Callable, List, Optional

from .base import SimpleCommandModule


def setup(bot: Any) -> "Welcome":
    return Welcome(bot)


class Welcome(SimpleCommandModule):
    name = "welcome"
    version = "1.0.0"
    description = "Privately introduces currently loaded Jeeves features."

    def _register_commands(self) -> None:
        self.register_command(
            r"^\s*!welcome(?:\s+(\S+))?\s*$",
            self._cmd_welcome,
            name="welcome",
            description="Send a module-aware welcome guide privately.",
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
            self.log_debug(f"welcome_summary hook failed: {exc}")
            return None

        if not result:
            return None
        return str(result).strip()

    def _collect_welcome_lines(self, channel: str) -> List[str]:
        lines: List[str] = []
        for module_name, module in sorted(self.bot.pm.plugins.items()):
            if module_name == self.name:
                continue
            hook = getattr(module, "welcome_summary", None)
            if not callable(hook):
                continue
            line = self._call_hook(hook, channel)
            if line:
                lines.append(line)
        return lines

    def _fallback_command_lines(self, is_admin: bool) -> List[str]:
        command_names = []
        for module in self.bot.pm.plugins.values():
            commands = getattr(module, "_commands", {})
            for cmd_info in commands.values():
                if cmd_info.get("admin_only") and not is_admin:
                    continue
                name = cmd_info.get("name")
                if name:
                    command_names.append(name.split(" ")[0])
        unique = sorted(set(command_names))
        if not unique:
            return []
        return ["Loaded commands include: " + ", ".join(f"!{name}" for name in unique[:24]) + "."]

    def _cmd_welcome(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        target = match.group(1) or username
        is_self = target.lower() == username.lower()
        recipient = username

        lines = [
            "Welcome to the household. I am Jeeves, a modular IRC butler.",
            "A few useful things currently available:",
        ]
        summaries = self._collect_welcome_lines(event.target)
        if not summaries:
            summaries = self._fallback_command_lines(self.bot.is_admin(event.source))

        max_lines = int(self.get_config_value("max_lines", event.target, default=10) or 10)
        lines.extend(f"- {line}" for line in summaries[:max(1, max_lines)])
        lines.append("Use !house for the current household report, or !help for the full command list.")

        if is_self:
            self.safe_reply(connection, event, f"I have sent you a brief welcome privately, {self.bot.title_for(username)}.")
        else:
            self.safe_reply(connection, event, f"I have sent you a welcome note to pass along, {self.bot.title_for(username)}.")
            lines.insert(0, f"For {target}:")

        for line in lines:
            self.safe_privmsg(recipient, line)
        return True
