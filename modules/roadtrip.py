# modules/roadtrip.py
# Enhanced surprise roadtrips without base class dependency
import random
import re
import time
import schedule
from datetime import datetime, timezone, timedelta

UTC = timezone.utc

def setup(bot):
    return Roadtrip(bot)

class Roadtrip:
    name = "roadtrip"
    version = "2.0.0"
    
    # Configuration constants
    MIN_HOURS_BETWEEN_TRIPS = 3
    MAX_HOURS_BETWEEN_TRIPS = 18
    MIN_MESSAGES_FOR_TRIGGER = 35
    MAX_MESSAGES_FOR_TRIGGER = 85
    TRIGGER_PROBABILITY = 0.25
    JOIN_WINDOW_SECONDS = 120
    MAX_HISTORY_ENTRIES = 20

    # Trip destinations
    LOCATIONS = [
        "the riverside park", "the old museum", "the observatory", "the seaside pier", 
        "the midnight diner", "the botanical gardens", "the antique arcade", "the lighthouse", 
        "the market square", "the hilltop ruins", "the art-house cinema", "the railway depot", 
        "the speakeasy", "the planetarium", "the neon alley", "the tea pavilion", 
        "the bookshop maze", "the clocktower", "the rooftops", "the brothel", "the funfair",
        "the stormbreak causeway",
    ]

    # Trigger messages
    TRIGGER_MESSAGES = [
        "Of course, {title}; I'll prepare the car.",
        "Very good, {title}; I shall ready the motor.",
        "An excellent notion, {title}; let me fetch the keys.",
        "Splendid idea, {title}; the vehicle awaits.",
    ]

    def __init__(self, bot):
        self.bot = bot
        self.st = bot.get_module_state(self.name)
        
        # Initialize state with sensible defaults
        self.st.setdefault("messages_since_last", 0)
        self.st.setdefault("next_trip_earliest", self._compute_next_trip_time().isoformat())
        self.st.setdefault("next_trip_message_threshold", self._compute_message_threshold())
        self.st.setdefault("current_rsvp", None)
        self.st.setdefault("history", [])
        self.st.setdefault("stats", {
            "trips_triggered": 0,
            "trips_completed": 0,
            "total_participants": 0,
            "messages_at_triggers": [],
            "most_popular_destination": None,
            "average_participants": 0.0
        })
        
        # Compile regex patterns
        name_pat = getattr(self.bot, "JEEVES_NAME_RE", r"(?:jeeves|jeevesbot)")
        self._rsvp_pattern = re.compile(rf"^\s*coming\s+{name_pat}!?\s*\.?\s*$", re.IGNORECASE)
        self._rsvp_alt_pattern = re.compile(r"^\s*!me\s*$", re.IGNORECASE)
        
        # Track active timers
        self._active_timers = set()
        
        bot.save()

    def on_load(self):
        """Clean up any existing scheduled jobs and restore RSVP window if needed."""
        schedule.clear(f"{self.name}-close")
        
        # Check if we have an active RSVP window that needs restoration
        current_rsvp = self.st.get("current_rsvp")
        if current_rsvp:
            open_until = float(current_rsvp.get("close_epoch", 0))
            now = time.time()
            
            if now >= open_until:
                self._close_rsvp_window()
            else:
                remaining_seconds = int(open_until - now)
                if remaining_seconds > 0:
                    schedule.every(remaining_seconds).seconds.do(
                        self._close_rsvp_window_scheduled
                    ).tag(f"{self.name}-close")

    def on_unload(self):
        """Clean up scheduled jobs."""
        schedule.clear(f"{self.name}-close")
        self._active_timers.clear()

    def _compute_next_trip_time(self) -> datetime:
        """Compute when the next trip can be triggered."""
        hours = random.randint(self.MIN_HOURS_BETWEEN_TRIPS, self.MAX_HOURS_BETWEEN_TRIPS)
        return datetime.now(UTC) + timedelta(hours=hours)

    def _compute_message_threshold(self) -> int:
        """Compute message threshold for next trip trigger."""
        return random.randint(self.MIN_MESSAGES_FOR_TRIGGER, self.MAX_MESSAGES_FOR_TRIGGER)

    def _time_gate_passed(self) -> bool:
        """Check if enough time has passed since last trip."""
        try:
            earliest_str = self.st.get("next_trip_earliest")
            if not earliest_str:
                return True
            earliest = datetime.fromisoformat(earliest_str)
            return datetime.now(UTC) >= earliest
        except (ValueError, TypeError):
            self.st["next_trip_earliest"] = self._compute_next_trip_time().isoformat()
            self.bot.save()
            return False

    def _message_gate_passed(self) -> bool:
        """Check if enough messages have passed since last trip."""
        message_count = self.st.get("messages_since_last", 0)
        threshold = self.st.get("next_trip_message_threshold", 0)
        return message_count >= threshold

    def _should_trigger_roadtrip(self) -> bool:
        """Check if all conditions are met to trigger a roadtrip."""
        if self.st.get("current_rsvp"):
            return False
        
        if not self._time_gate_passed() or not self._message_gate_passed():
            return False
        
        return random.random() < self.TRIGGER_PROBABILITY

    def _reset_trigger_conditions(self):
        """Reset the trigger conditions after a trip."""
        self.st["messages_since_last"] = 0
        self.st["next_trip_earliest"] = self._compute_next_trip_time().isoformat()
        self.st["next_trip_message_threshold"] = self._compute_message_threshold()
        self.bot.save()

    def _open_rsvp_window(self, connection, room: str):
        """Open an RSVP window for a new roadtrip."""
        destination = random.choice(self.LOCATIONS)
        trigger_msg = random.choice(self.TRIGGER_MESSAGES)
        
        # Announce the trip
        title = self.bot.title_for("nobody")
        connection.privmsg(room, trigger_msg.format(title=title))
        connection.privmsg(
            room,
            f"Shall we? I've in mind a little excursion to {destination}. "
            f'Say "coming jeeves!" or "coming jeevesbot!" or "!me" within {self.JOIN_WINDOW_SECONDS} seconds to be shown to the car.'
        )
        
        # Set up RSVP window state
        now = datetime.now(UTC)
        close_time = time.time() + self.JOIN_WINDOW_SECONDS
        
        rsvp_state = {
            "destination": destination,
            "room": room,
            "participants": [],
            "triggered_at": now.isoformat(),
            "close_epoch": close_time,
            "messages_at_trigger": self.st.get("messages_since_last", 0)
        }
        
        self.st["current_rsvp"] = rsvp_state
        self.bot.save()
        
        # Schedule window close
        schedule.every(self.JOIN_WINDOW_SECONDS).seconds.do(
            self._close_rsvp_window_scheduled
        ).tag(f"{self.name}-close")
        
        # Update statistics
        stats = self.st.get("stats", {})
        stats["trips_triggered"] = stats.get("trips_triggered", 0) + 1
        messages_list = stats.get("messages_at_triggers", [])
        messages_list.append(rsvp_state["messages_at_trigger"])
        stats["messages_at_triggers"] = messages_list[-20:]
        self.st["stats"] = stats

    def _close_rsvp_window_scheduled(self):
        """Scheduled window closer."""
        self._close_rsvp_window()
        return schedule.CancelJob

    def _close_rsvp_window(self):
        """Close the RSVP window and announce results."""
        current_rsvp = self.st.get("current_rsvp")
        if not current_rsvp:
            return
        
        schedule.clear(f"{self.name}-close")
        
        room = current_rsvp["room"]
        participants = current_rsvp.get("participants", [])
        destination = current_rsvp["destination"]
        
        # Remove duplicates while preserving order
        participants = list(dict.fromkeys(participants))
        
        # Create history entry
        history_entry = {
            "date_iso": current_rsvp["triggered_at"],
            "participants": participants,
            "messages_at_trigger": current_rsvp["messages_at_trigger"],
            "destination": destination,
            "room": room,
            "participant_count": len(participants)
        }
        
        # Update history
        history = self.st.get("history", [])
        history.append(history_entry)
        
        if len(history) > self.MAX_HISTORY_ENTRIES:
            history = history[-self.MAX_HISTORY_ENTRIES:]
        
        # Update statistics
        stats = self.st.get("stats", {})
        stats["trips_completed"] = stats.get("trips_completed", 0) + 1
        stats["total_participants"] = stats.get("total_participants", 0) + len(participants)
        
        completed = stats["trips_completed"]
        if completed > 0:
            stats["average_participants"] = stats["total_participants"] / completed
        
        # Track most popular destination
        dest_counts = {}
        for h in history:
            dest = h.get("destination")
            if dest:
                dest_counts[dest] = dest_counts.get(dest, 0) + 1
        
        if dest_counts:
            stats["most_popular_destination"] = max(dest_counts, key=dest_counts.get)
        
        # Save state
        self.st["history"] = history
        self.st["current_rsvp"] = None
        self.st["stats"] = stats
        self.bot.save()

        # Announce results
        try:
            if participants:
                details = []
                for participant in participants:
                    pronouns = self.bot.pronouns_for(participant)
                    details.append(f"{participant} ({pronouns})")
                
                self.bot.connection.privmsg(
                    room, 
                    f"Very good. Outing to {destination}: {', '.join(details)}. Do buckle up."
                )
            else:
                self.bot.connection.privmsg(
                    room, 
                    f"No takers. I shall cancel the reservation for {destination}."
                )
        except Exception as e:
            print(f"[roadtrip] error announcing results: {e}", file=sys.stderr)

        self._reset_trigger_conditions()

    def _try_collect_rsvp(self, msg: str, username: str, room: str) -> bool:
        """Try to collect an RSVP for the current trip."""
        current_rsvp = self.st.get("current_rsvp")
        if not current_rsvp or current_rsvp.get("room") != room:
            return False
        
        close_time = float(current_rsvp.get("close_epoch", 0))
        if time.time() > close_time:
            self._close_rsvp_window()
            return True

        if self._rsvp_pattern.match(msg) or self._rsvp_alt_pattern.match(msg):
            participants = current_rsvp.get("participants", [])
            
            if username not in participants:
                participants.append(username)
                current_rsvp["participants"] = participants
                self.st["current_rsvp"] = current_rsvp
                self.bot.save()
                
                self.bot.connection.privmsg(room, f"Noted, {username}. Mind the running board.")
            
            return True
        
        return False

    def _increment_message_count(self):
        """Increment message counter toward trigger threshold."""
        self.st["messages_since_last"] = self.st.get("messages_since_last", 0) + 1
        self.bot.save()

    def _answer_latest(self, connection, room: str, username: str):
        """Answer query about the latest roadtrip."""
        history = self.st.get("history", [])
        if not history:
            title = self.bot.title_for(username)
            connection.privmsg(room, f"{username}, no roadtrips on the books yet, {title}.")
            return True
        
        last_trip = history[-1]
        when = last_trip.get("date_iso", "unknown time")[:16]
        participants = last_trip.get("participants", [])
        destination = last_trip.get("destination", "parts unknown")
        
        if participants:
            details = []
            for participant in participants:
                pronouns = self.bot.pronouns_for(participant)
                details.append(f"{participant} ({pronouns})")
            
            connection.privmsg(
                room, 
                f"{username}, most recent outing to {destination} ({when}): {', '.join(details)}."
            )
        else:
            title = self.bot.title_for(username)
            connection.privmsg(
                room, 
                f"{username}, the most recent outing to {destination} ({when}) departed without passengers, {title}."
            )
        return True

    def on_pubmsg(self, connection, event, msg, username):
        room = event.target

        # Handle !roadtrip command
        if re.match(r"^\s*!roadtrip\s*$", msg, re.IGNORECASE):
            return self._answer_latest(connection, room, username)

        # Admin stats command
        if self.bot.is_admin(username) and re.match(r"^\s*!roadtrip\s+stats\s*$", msg, re.IGNORECASE):
            stats = self.st.get("stats", {})
            
            triggered = stats.get("trips_triggered", 0)
            completed = stats.get("trips_completed", 0)
            total_participants = stats.get("total_participants", 0)
            avg_participants = stats.get("average_participants", 0.0)
            popular_dest = stats.get("most_popular_destination", "None")
            
            # Current state info
            messages_count = self.st.get("messages_since_last", 0)
            threshold = self.st.get("next_trip_message_threshold", 0)
            
            time_ok = "✓" if self._time_gate_passed() else "✗"
            msg_ok = "✓" if self._message_gate_passed() else "✗"
            
            lines = [
                f"Triggered: {triggered}",
                f"Completed: {completed}",
                f"Total participants: {total_participants}",
                f"Avg participants: {avg_participants:.1f}",
                f"Popular destination: {popular_dest}",
                f"Messages: {messages_count}/{threshold} {msg_ok}",
                f"Time gate: {time_ok}"
            ]
            
            connection.privmsg(room, f"Roadtrip stats: {'; '.join(lines)}")
            return True

        # Admin force trigger command
        if self.bot.is_admin(username) and re.match(r"^\s*!roadtrip\s+trigger\s*$", msg, re.IGNORECASE):
            if self.st.get("current_rsvp"):
                connection.privmsg(room, "A roadtrip RSVP window is already active.")
            else:
                self._open_rsvp_window(connection, room)
            return True

        # Try to handle RSVP first
        if self._try_collect_rsvp(msg, username, room):
            return True
        
        # Count message toward trigger threshold
        self._increment_message_count()
        
        # Check if we should trigger a roadtrip
        if self._should_trigger_roadtrip():
            self._open_rsvp_window(connection, room)

        return False