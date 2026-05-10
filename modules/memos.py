# modules/memos.py
# Memo delivery with butler flair.
import hashlib
import re
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from .base import SimpleCommandModule, admin_required

UTC = timezone.utc


def _format_relative_time(iso_timestamp: str) -> str:
    """Format an ISO timestamp as a human-readable relative time."""
    if not iso_timestamp:
        return ""
    try:
        sent_time = datetime.fromisoformat(iso_timestamp.replace('Z', '+00:00'))
        now = datetime.now(UTC)
        delta = now - sent_time

        seconds = int(delta.total_seconds())
        if seconds < 0:
            return ""

        minutes = seconds // 60
        hours = minutes // 60
        days = hours // 24

        if seconds < 60:
            return "just now"
        elif minutes < 60:
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        elif hours < 24:
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif days == 1:
            return "yesterday"
        elif days < 7:
            return f"{days} days ago"
        else:
            # For older messages, show the date
            return sent_time.strftime("%b %d")
    except (ValueError, TypeError):
        return ""

def setup(bot):
    return Memos(bot)

class Memos(SimpleCommandModule):
    name = "memos"
    version = "3.2.0"  # Added relative timestamps to memo delivery
    description = "Provides memo functionality for leaving messages for users."

    ACKS = [ "Indeed, {title}; I shall make a note of it.", "Very good, {title}. Your message is recorded.", "Quite so, {title}; I shall see that it is delivered." ]
    DELIVER_LINES = [ "Ah, {to}! {from_} left you a message {when}; {says}: {text}", "{to}, a note from {from_} ({when}): {text}", "Message for {to} from {from_} ({when}): {text}" ]

    def __init__(self, bot):
        super().__init__(bot)
        
        # --- State Migration Logic ---
        pending_memos = self.get_state("pending", {})
        # Check if the first key is likely a user_id (non-channel) to detect old format
        first_key = next(iter(pending_memos), None)
        if first_key and not first_key.startswith('#'):
            self.log_debug("Old memo state format detected. Migrating memos...")
            new_pending = { self.bot.primary_channel: pending_memos }
            self.set_state("pending", new_pending)
            self.log_debug(f"Migrated memos for {len(pending_memos)} users to default channel {self.bot.primary_channel}.")
        else:
            self.set_state("pending", pending_memos)
        # --- End Migration Logic ---
        
        self.save_state()

    def _register_commands(self):
        self.register_command(r"^\s*!memo\s+(\S+)\s+(.+)$", self._cmd_memo, name="memo", description="Leave a message for someone.")
        self.register_command(r"^\s*!note\s+(\S+)\s+(.+)$", self._cmd_memo, name="note", description="Alias for !memo.")
        self.register_command(r"^\s*!tell\s+(\S+)\s+(.+)$", self._cmd_memo, name="tell", description="Alias for !memo.")
        self.register_command(r"^\s*!memos\s+mine\s*$", self._cmd_memos_mine, name="memos mine", description="Show your pending messages.")
        self.register_command(r"^\s*!memos\s+admin\s+summary\s*$", self._cmd_admin_summary, name="memos admin summary", admin_only=True, description="[Admin] Summarize pending memos.")
        self.register_command(r"^\s*!memos\s+admin\s+list(?:\s+(.+))?\s*$", self._cmd_admin_list, name="memos admin list", admin_only=True, description="[Admin] List pending memos privately.")
        self.register_command(r"^\s*!memos\s+admin\s+show\s+([0-9a-f]{10})\s*$", self._cmd_admin_show, name="memos admin show", admin_only=True, description="[Admin] Show one pending memo privately.")
        self.register_command(r"^\s*!memos\s+admin\s+clear\s+([0-9a-f]{10})\s*$", self._cmd_admin_clear, name="memos admin clear", admin_only=True, description="[Admin] Clear one pending memo.")
        self.register_command(r"^\s*!memos\s+admin\s+clear-recipient\s+(\S+)(?:\s+(\S+))?\s*$", self._cmd_admin_clear_recipient, name="memos admin clear recipient", admin_only=True, description="[Admin] Clear pending memos for a recipient.")

    def _pending_count(self) -> int:
        pending = self.get_state("pending", {})
        total = 0
        for channel_memos in pending.values():
            if isinstance(channel_memos, dict):
                total += sum(len(bucket) for bucket in channel_memos.values() if isinstance(bucket, list))
        return total

    def _user_display_name(self, user_id: str) -> str:
        users_module = getattr(getattr(self.bot, "pm", None), "plugins", {}).get("users")
        if users_module:
            user_map = users_module.get_state("user_map", {})
            profile = user_map.get(user_id, {}) if isinstance(user_map, dict) else {}
            nick = profile.get("canonical_nick") if isinstance(profile, dict) else None
            if nick:
                return str(nick)
        return user_id

    def _memo_id(self, channel: str, user_id: str, index: int, memo: Dict[str, Any]) -> str:
        payload = "\x1f".join(
            [
                channel,
                user_id,
                str(index),
                str(memo.get("when", "")),
                str(memo.get("from", "")),
                str(memo.get("text", "")),
            ]
        )
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:10]

    def _iter_pending_memos(self) -> List[Dict[str, Any]]:
        pending = self.get_state("pending", {})
        entries: List[Dict[str, Any]] = []
        if not isinstance(pending, dict):
            return entries
        for channel, channel_memos in sorted(pending.items()):
            if not isinstance(channel_memos, dict):
                continue
            for user_id, bucket in sorted(channel_memos.items()):
                if not isinstance(bucket, list):
                    continue
                for index, memo in enumerate(bucket):
                    if not isinstance(memo, dict):
                        continue
                    entries.append(
                        {
                            "id": self._memo_id(channel, user_id, index, memo),
                            "channel": channel,
                            "recipient_id": user_id,
                            "recipient": self._user_display_name(user_id),
                            "index": index,
                            "from": str(memo.get("from", "?")),
                            "when": str(memo.get("when", "")),
                            "text": str(memo.get("text", "")),
                        }
                    )
        return entries

    def _format_memo_entry(self, entry: Dict[str, Any], include_text: bool = False) -> str:
        when = (entry.get("when") or "")[:16].replace("T", " ")
        text = entry.get("text", "")
        if not include_text and len(text) > 80:
            text = text[:77] + "..."
        return (
            f"{entry['id']} {entry['channel']} -> {entry['recipient']} "
            f"from {entry['from']} at {when or '?'} UTC: {text}"
        )

    def _memo_summary_text(self) -> str:
        entries = self._iter_pending_memos()
        if not entries:
            return "No pending memos."
        channels: Dict[str, int] = {}
        recipients: Dict[str, int] = {}
        for entry in entries:
            channels[entry["channel"]] = channels.get(entry["channel"], 0) + 1
            recipients[entry["recipient"]] = recipients.get(entry["recipient"], 0) + 1
        channel_bits = ", ".join(f"{channel}: {count}" for channel, count in sorted(channels.items()))
        stale = sorted(recipients.items(), key=lambda item: (-item[1], item[0]))[:5]
        stale_bits = ", ".join(f"{recipient}: {count}" for recipient, count in stale)
        return f"{len(entries)} pending memo(s). By channel: {channel_bits}. Top recipients: {stale_bits}."

    def _parse_admin_list_args(self, raw_args: Optional[str]) -> Tuple[Optional[str], int]:
        channel = None
        limit = 10
        if not raw_args:
            return channel, limit
        for part in raw_args.split():
            if part.startswith("#"):
                channel = part
            elif part.isdigit():
                limit = max(1, min(int(part), 50))
        return channel, limit

    def _list_memos_text(self, raw_args: Optional[str] = None) -> str:
        channel, limit = self._parse_admin_list_args(raw_args)
        entries = self._iter_pending_memos()
        if channel:
            entries = [entry for entry in entries if entry["channel"] == channel]
        if not entries:
            scope = f" in {channel}" if channel else ""
            return f"No pending memos{scope}."
        shown = entries[:limit]
        lines = [self._format_memo_entry(entry) for entry in shown]
        remaining = len(entries) - len(shown)
        if remaining > 0:
            lines.append(f"...and {remaining} more. Use !memos admin list [#channel] [limit] to page manually.")
        return "\n".join(lines)

    def _find_memo_entry(self, memo_id: str) -> Optional[Dict[str, Any]]:
        for entry in self._iter_pending_memos():
            if entry["id"] == memo_id:
                return entry
        return None

    def _remove_memo_by_id(self, memo_id: str) -> Optional[Dict[str, Any]]:
        entry = self._find_memo_entry(memo_id)
        if not entry:
            return None
        pending = self.get_state("pending", {})
        channel = entry["channel"]
        user_id = entry["recipient_id"]
        index = entry["index"]
        bucket = pending.get(channel, {}).get(user_id, [])
        if index >= len(bucket):
            return None
        del bucket[index]
        if not bucket:
            del pending[channel][user_id]
        if channel in pending and not pending[channel]:
            del pending[channel]
        self.set_state("pending", pending)
        self.save_state()
        return entry

    def _clear_recipient(self, recipient: str, channel: Optional[str] = None) -> int:
        pending = self.get_state("pending", {})
        if not isinstance(pending, dict):
            return 0
        user_id = self._resolve_recipient_id(recipient, pending)
        removed = 0
        channels = [channel] if channel else list(pending.keys())
        for current_channel in channels:
            channel_memos = pending.get(current_channel)
            if not isinstance(channel_memos, dict):
                continue
            bucket = channel_memos.pop(user_id, [])
            if isinstance(bucket, list):
                removed += len(bucket)
            if not channel_memos:
                pending.pop(current_channel, None)
        if removed:
            self.set_state("pending", pending)
            self.save_state()
        return removed

    def _resolve_recipient_id(self, recipient: str, pending: Dict[str, Any]) -> str:
        recipient_lower = recipient.lower()
        recipient_ids = set()
        for channel_memos in pending.values():
            if isinstance(channel_memos, dict):
                recipient_ids.update(channel_memos.keys())
        if recipient in recipient_ids:
            return recipient
        for user_id in recipient_ids:
            if self._user_display_name(user_id).lower() == recipient_lower:
                return user_id
        return self.bot.get_user_id(recipient)

    @property
    def matrix_admin_commands(self) -> dict:
        return {
            "!memos admin summary": (lambda args: self._memo_summary_text(), "summarize pending memos"),
            "!memos admin list": (lambda args: self._list_memos_text(args), "!memos admin list [#channel] [limit]"),
            "!memos admin show": (self._matrix_admin_show, "!memos admin show <memo_id>"),
            "!memos admin clear": (self._matrix_admin_clear, "!memos admin clear <memo_id>"),
            "!memos admin clear-recipient": (self._matrix_admin_clear_recipient, "!memos admin clear-recipient <nick|user_id> [#channel]"),
        }

    def _matrix_admin_show(self, args: str) -> str:
        memo_id = args.strip().lower()
        entry = self._find_memo_entry(memo_id)
        if not entry:
            return f"No pending memo found for id {memo_id}."
        return self._format_memo_entry(entry, include_text=True)

    def _matrix_admin_clear(self, args: str) -> str:
        memo_id = args.strip().lower()
        entry = self._remove_memo_by_id(memo_id)
        if not entry:
            return f"No pending memo found for id {memo_id}."
        return f"Cleared memo {memo_id} for {entry['recipient']} in {entry['channel']}."

    def _matrix_admin_clear_recipient(self, args: str) -> str:
        parts = args.split()
        if not parts:
            return "Usage: !memos admin clear-recipient <nick|user_id> [#channel]"
        recipient = parts[0]
        channel = parts[1] if len(parts) > 1 else None
        removed = self._clear_recipient(recipient, channel)
        scope = f" in {channel}" if channel else ""
        return f"Cleared {removed} pending memo(s) for {recipient}{scope}."

    def _cmd_admin_summary(self, connection, event, msg, username, match):
        self.safe_reply(connection, event, self._memo_summary_text())
        return True

    def _cmd_admin_list(self, connection, event, msg, username, match):
        self.safe_reply(connection, event, f"{self.bot.title_for(username)}, I have sent the pending memo ledger privately.")
        for line in self._list_memos_text(match.group(1)).splitlines():
            self.safe_privmsg(username, line)
        return True

    def _cmd_admin_show(self, connection, event, msg, username, match):
        memo_id = match.group(1).lower()
        entry = self._find_memo_entry(memo_id)
        if not entry:
            self.safe_reply(connection, event, f"No pending memo found for id {memo_id}.")
            return True
        self.safe_reply(connection, event, f"{self.bot.title_for(username)}, I have sent that memo privately.")
        self.safe_privmsg(username, self._format_memo_entry(entry, include_text=True))
        return True

    def _cmd_admin_clear(self, connection, event, msg, username, match):
        memo_id = match.group(1).lower()
        entry = self._remove_memo_by_id(memo_id)
        if not entry:
            self.safe_reply(connection, event, f"No pending memo found for id {memo_id}.")
            return True
        self.safe_reply(connection, event, f"Cleared memo {memo_id} for {entry['recipient']} in {entry['channel']}.")
        return True

    def _cmd_admin_clear_recipient(self, connection, event, msg, username, match):
        recipient = match.group(1)
        channel = match.group(2)
        removed = self._clear_recipient(recipient, channel)
        scope = f" in {channel}" if channel else ""
        self.safe_reply(connection, event, f"Cleared {removed} pending memo(s) for {recipient}{scope}.")
        return True

    def house_status(self, channel: str = None) -> str:
        count = self._pending_count()
        if count <= 0:
            return ""
        return f"Memos: {count} pending."

    def welcome_summary(self, channel: str = None) -> str:
        return "Leave notes for absent guests with !memo nick message; check yours with !memos mine."

    def contextual_hint(self, msg: str, username: str, channel: str) -> Optional[str]:
        if re.search(r"\b(memo|memos|note|tell)\b", msg, re.IGNORECASE):
            return "You can leave a message for someone with !memo nick message."
        return None

    def on_ambient_message(self, connection, event, msg, username):
        if not self.is_enabled(event.target): return False

        user_id = self.bot.get_user_id(username)
        channel = event.target
        pending = self.get_state("pending", {})

        # Only look for memos in the current channel
        channel_memos = pending.get(channel, {})
        bucket = channel_memos.get(user_id, [])

        if not bucket:
            return False

        max_deliver = self.get_config_value("max_deliver_per_burst", channel, default=3)
        to_deliver = bucket[:max_deliver]
        remainder = bucket[max_deliver:]

        for item in to_deliver:
            line = self._deliver_line(username, item.get("from","?"), item.get("text",""), item.get("when",""))
            self.safe_reply(connection, event, line)

        if remainder:
            # Update pending state with remaining memos
            pending[channel][user_id] = remainder
            self.set_state("pending", pending)
            self.save_state()

            # Inform user there are more, but they'll be delivered on next message
            self.safe_reply(connection, event, f"{username}, you have {len(remainder)} more memo(s). They will be delivered when you next speak (or use '!memos mine' to view all).")
            return True
        else:
            # All memos delivered, clean up
            del pending[channel][user_id]
            if not pending[channel]: # Clean up empty channel dict
                del pending[channel]
            self.set_state("pending", pending)
            self.save_state()
            return True

    def _third_person_says(self, from_user: str) -> str:
        pron = self.bot.pronouns_for(from_user).lower()
        if pron.startswith("he"): return "he says"
        if pron.startswith("she"): return "she says"
        if pron.startswith("it"): return "it says"
        return "they say"

    def _deliver_line(self, to_user: str, from_user: str, text: str, when: str = "") -> str:
        says = self._third_person_says(from_user)
        relative_time = _format_relative_time(when) or "some time ago"
        tmpl = random.choice(self.DELIVER_LINES)
        return tmpl.format(to=to_user, from_=from_user, text=text, says=says, when=relative_time)

    def _cmd_memo(self, connection, event, msg, username, match):
        to_nick, text = match.group(1), match.group(2).strip()
        channel = event.target
        if not text:
            return True

        to_user_id = self.bot.get_user_id(to_nick)
        pending = self.get_state("pending", {})
        
        channel_memos = pending.setdefault(channel, {})
        bucket = channel_memos.setdefault(to_user_id, [])
        
        max_pending = self.get_config_value("max_pending_per_user", channel, default=3)
        if len(bucket) >= max_pending:
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, {to_nick} already has {max_pending} memos queued in this channel.")
            return True
            
        bucket.append({
            "from": username, 
            "text": text, 
            "when": self.bot.get_utc_time(),
        })
        
        self.set_state("pending", pending)
        self.save_state()
        self.safe_reply(connection, event, random.choice(self.ACKS).format(title=self.bot.title_for(username)))
        return True

    def _cmd_memos_mine(self, connection, event, msg, username, match):
        user_id = self.bot.get_user_id(username)
        pending = self.get_state("pending", {})
        all_user_memos = []

        # Collect memos from all channels for the user
        for channel, channel_memos in pending.items():
            if user_id in channel_memos:
                for memo in channel_memos[user_id]:
                    memo_with_context = memo.copy()
                    memo_with_context['channel'] = channel
                    all_user_memos.append(memo_with_context)
        
        if not all_user_memos:
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, there are no memos awaiting you.")
            return True
        
        max_deliver = self.get_config_value("max_deliver_per_burst", event.target, default=3)
        shown = all_user_memos[:max_deliver]
        more = len(all_user_memos) - len(shown)
        
        self.safe_reply(connection, event, f"{self.bot.title_for(username)}, your pending memos:")
        for item in shown:
            when = (item.get("when") or "")[:16].replace("T", " ")
            self.safe_privmsg(username, f"- From {item.get('from','?')} (in {item.get('channel')} at {when} UTC): {item.get('text','')}")
            
        if more > 0:
            self.safe_privmsg(username, f"…and {more} more memo(s) queued.")
        
        self.safe_reply(connection, event, "I have sent you the details privately.")
        return True
