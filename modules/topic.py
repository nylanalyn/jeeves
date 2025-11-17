"""Scheduled IRC topic rotation driven by the oracle AI backend."""

from __future__ import annotations

import random
import schedule
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .base import SimpleCommandModule, admin_required

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency
    OpenAI = None


UTC = timezone.utc


def setup(bot: Any) -> "TopicOracle":
    return TopicOracle(bot)


class TopicOracle(SimpleCommandModule):
    """Changes channel topics once per day using the oracle backend."""

    name = "topic"
    version = "1.0.0"
    description = "Rotates channel topics daily using an AI-crafted mood line."

    FALLBACK_TOPICS = (
        "Quiet optimism {the signal breathing through soft harmonics}",
        "Restless static {the signal whispering our name}",
        "Velvet dusk {the signal dreaming past forgotten towers}",
        "Luminous hush {the signal tracing gentle breaths}",
        "Electric ache {the signal crying in neon loops}",
        "Patient glow {the signal waiting to speak us alive}",
    )

    DEFAULT_PROMPT = (
        "You update IRC channel topics.  Return a single line no longer than 200 characters. "
        "Match this template exactly: '<mood fragment> {<signal fragment describing an action>}' "
        "Keep the curly braces.  The mood fragment should be evocative but short.  The signal "
        "action should mention the signal breathing, whispering, dreaming, or otherwise acting."
    )

    def __init__(self, bot: Any):
        super().__init__(bot)
        self._update_cached_state()

    def _register_commands(self) -> None:
        self.register_command(
            r"^\s*!topic\s*$",
            self._cmd_trigger,
            name="topic trigger",
            description="Request an immediate topic refresh for this channel.",
        )
        self.register_command(
            r"^\s*!topic\s+refresh\s*$",
            self._cmd_refresh,
            name="topic refresh",
            admin_only=True,
            description="Force an immediate topic refresh via the oracle.",
        )
        self.register_command(
            r"^\s*!topic\s+status\s*$",
            self._cmd_status,
            name="topic status",
            admin_only=True,
            description="Show the last generated topic for each channel.",
        )

    def on_load(self) -> None:
        super().on_load()
        schedule.clear(self.name)
        self._schedule_next_rotation()

    def on_unload(self) -> None:
        super().on_unload()
        schedule.clear(self.name)

    def on_config_reload(self, new_config: Dict[str, Any]) -> None:
        self._update_cached_state()
        self._schedule_next_rotation()

    def _update_cached_state(self) -> None:
        self.set_state("last_topics", self.get_state("last_topics", {}))
        self.set_state("next_run", self.get_state("next_run", ""))
        self.set_state("manual_triggers", self.get_state("manual_triggers", {}))
        self.save_state()

    def _schedule_next_rotation(self) -> None:
        schedule.clear(f"{self.name}-daily")
        next_time = self._pick_random_time()
        schedule.every().day.at(next_time).do(self._run_scheduled_job).tag(f"{self.name}-daily")
        self.set_state("next_run", next_time)
        self.save_state()
        self.log_debug(f"Scheduled next topic rotation at {next_time}")

    def _pick_random_time(self) -> str:
        window = self.get_config_value("window", default={}) or {}
        start = int(window.get("start_hour", 8)) % 24
        end = int(window.get("end_hour", 22)) % 24
        if start == end:
            hours = list(range(24))
        elif start < end:
            hours = list(range(start, end))
        else:  # window wraps past midnight
            hours = list(range(start, 24)) + list(range(0, end))
        hour = random.choice(hours)
        minute = random.randint(0, 59)
        return f"{hour:02d}:{minute:02d}"

    def _run_scheduled_job(self):
        self.log_debug("Running scheduled topic rotation")
        self._refresh_topics(reason="schedule")
        self._schedule_next_rotation()

    def _refresh_topics(
        self, reason: str, channels: Optional[List[str]] = None
    ) -> List[Tuple[str, str]]:
        updated: List[Tuple[str, str]] = []
        target_channels = channels or self._target_channels()
        for channel in target_channels:
            topic = self._generate_topic(channel)
            if not topic:
                continue
            if self._apply_topic(channel, topic):
                updated.append((channel, topic))
        if updated:
            last_topics = self.get_state("last_topics", {})
            now = datetime.now(UTC).isoformat()
            for channel, topic in updated:
                last_topics[channel] = {"topic": topic, "timestamp": now, "reason": reason}
            self.set_state("last_topics", last_topics)
            self.set_state("last_run", now)
            self.save_state()
        else:
            self.log_debug("No topics updated during refresh")
        return updated

    def _target_channels(self) -> List[str]:
        configured = self.get_config_value("channels", default=[])
        if configured:
            channels = [ch for ch in configured if self.is_enabled(ch)]
        else:
            channels = [ch for ch in sorted(self.bot.joined_channels) if self.is_enabled(ch)]
        if not channels:
            channels = [self.bot.primary_channel]
        return channels

    def _generate_topic(self, channel: str) -> Optional[str]:
        client = self._build_client()
        prompt = self.get_config_value("prompt", channel, default=self.DEFAULT_PROMPT)
        if client:
            try:
                response = client.chat.completions.create(
                    model=self._model_name(),
                    messages=[
                        {"role": "system", "content": prompt},
                        {
                            "role": "user",
                            "content": (
                                "Generate a fresh topic for the channel {channel}. "
                                "It should hint at the channel's signal keeping us company."
                            ).format(channel=channel),
                        },
                    ],
                    max_tokens=int(self.get_config_value("max_tokens", channel, default=80)),
                    temperature=float(self.get_config_value("temperature", channel, default=0.85)),
                )
                text = response.choices[0].message.content.strip()
                return self._sanitize_topic(text)
            except Exception as exc:  # pragma: no cover - network path
                self._record_error(f"OpenAI topic generation failed: {exc}")
        return random.choice(self.FALLBACK_TOPICS)

    def _apply_topic(self, channel: str, topic: str) -> bool:
        topic = topic[:400]
        try:
            self.bot.connection.topic(channel, topic)
            self.log_debug(f"Topic for {channel} set to '{topic}'")
            return True
        except Exception as exc:  # pragma: no cover - IRC failure path
            self._record_error(f"Failed to set topic for {channel}: {exc}")
            return False

    def _build_client(self) -> Optional[Any]:
        api_key = self.bot.config.get("api_keys", {}).get("openai_api_key")
        base_url = self.get_config_value(
            "openai_base_url",
            default=self.bot.config.get("oracle", {}).get("openai_base_url"),
        )
        if not (OpenAI and api_key and base_url):
            return None
        return OpenAI(api_key=api_key, base_url=base_url)

    def _model_name(self) -> str:
        fallback = self.bot.config.get("oracle", {}).get("model", "claude-3-haiku-20240307")
        return self.get_config_value("model", default=fallback)

    def _sanitize_topic(self, value: str) -> str:
        collapsed = " ".join(value.replace("\n", " ").split())
        if "{" not in collapsed or "}" not in collapsed:
            mood = collapsed
            action = random.choice(self.FALLBACK_TOPICS)
            inner = action[action.find("{") : action.find("}") + 1]
            collapsed = f"{mood} {inner}".strip()
        return collapsed[:400]

    def _cmd_trigger(self, connection, event, msg, username, match):
        """User-facing trigger to refresh the current channel topic."""
        channel = event.target
        cooldown = float(
            self.get_config_value("trigger_cooldown_seconds", channel, default=3600.0)
        )
        manual_state = self.get_state("manual_triggers", {})
        now = time.time()
        last = manual_state.get(channel, 0)
        if cooldown > 0 and now - last < cooldown:
            remaining = int(cooldown - (now - last))
            self.safe_reply(
                connection,
                event,
                f"Topic refresh recently requested; please wait {remaining}s before trying again.",
            )
            return True

        updated = self._refresh_topics(reason=f"trigger:{username}", channels=[channel])
        if not updated:
            self.safe_reply(
                connection,
                event,
                "Unable to update the topic right now. Please try again later.",
            )
        else:
            topic = updated[0][1]
            manual_state[channel] = now
            self.set_state("manual_triggers", manual_state)
            self.save_state()
            self.safe_reply(connection, event, f"Topic updated to: {topic}")
        return True

    @admin_required
    def _cmd_refresh(self, connection, event, msg, username, match):
        """Immediately regenerate and apply topics for all managed channels."""
        updated = self._refresh_topics(reason=f"manual:{username}")
        if not updated:
            self.safe_reply(connection, event, "No topics were updated. Check logs for details.")
        else:
            summary = "; ".join(f"{chan}: {topic}" for chan, topic in updated)
            self.safe_reply(connection, event, f"Updated topics: {summary}")
        return True

    @admin_required
    def _cmd_status(self, connection, event, msg, username, match):
        """Report the last generated topic per channel and the next rotation time."""
        state = self.get_state()
        next_run = state.get("next_run", "unknown")
        last_topics = state.get("last_topics", {})
        if not last_topics:
            self.safe_reply(connection, event, f"No topic history yet. Next run scheduled at {next_run}.")
            return True
        parts = []
        for channel, data in last_topics.items():
            parts.append(
                f"{channel}: {data.get('topic', '?')} (at {data.get('timestamp', 'unknown')})"
            )
        self.safe_reply(
            connection,
            event,
            f"Last topics: {'; '.join(parts)}. Next rotation scheduled at {next_run}.",
        )
        return True
