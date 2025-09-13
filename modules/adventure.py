# modules/adventure.py
# Enhanced choose-your-own-adventure with better state management and no base dependency
import random
import re
import time
import schedule
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple

UTC = timezone.utc

def setup(bot):
    return Adventure(bot)

class Adventure:
    name = "adventure"
    version = "2.0.0"
    
    # Configuration constants
    VOTE_WINDOW_SEC = 75
    STORY_SENTENCES_PER_ROUND = 3
    MAX_HISTORY_ENTRIES = 50

    # Adventure locations
    PLACES = [
        "the Neon Bazaar", "the Clockwork Conservatory", "the Signal Archives", 
        "the Subterranean Gardens", "the Rusted Funicular", "the Mirror Maze", 
        "the Lattice Observatory", "the Stormbreak Causeway", "the Midnight Diner", 
        "the Old Museum", "the Lighthouse", "the Planetarium", "the Rooftops",
        "the Antique Arcade", "the Bookshop Maze", "the Railway Depot", 
        "the Tea Pavilion", "the Neon Alley",
    ]

    # Story fragments with atmospheric tech-goth flavor
    STORY_BITS = [
        "A locked cabinet hummed like a captive beehive in {place}.",
        "Someone had chalked unfamiliar sigils on the floor of {place}.",
        "In {place}, screens woke without power and showed a room three seconds ahead.",
        "The air in {place} tasted like coins and old arguments.",
        "A brass plaque in {place} listed names none of you remembered becoming.",
        "Every footstep in {place} arrived before the boot that made it.",
        "A maintenance door in {place} opened onto an identical maintenance door.",
        "Even the shadows in {place} kept their own inventories.",
        "You found a keyring labeled 'spares' in {place}; none of the keys matched each other.",
        "At {place}, the public address system whispered your question back with an extra word.",
        "Rain pooled in {place} and reflected not the ceiling but a low gray sky.",
        "The map at {place} had a 'you were here' marker that moved if you looked away.",
    ]

    # Command patterns
    RE_VOTE_1 = re.compile(r"^\s*!?1[.,!\s]*\s*$")
    RE_VOTE_2 = re.compile(r"^\s*!?2[.,!\s]*\s*$")
    RE_CMD_START = re.compile(r"^\s*!adventure\s*$", re.IGNORECASE)
    RE_CMD_STATUS = re.compile(r"^\s*!adventure\s+(now|status)\s*$", re.IGNORECASE)
    RE_CMD_LAST = re.compile(r"^\s*!adventure\s+(last|history)\s*$", re.IGNORECASE)

    def __init__(self, bot):
        self.bot = bot
        
        # Get state using bot's method
        self.st = bot.get_module_state(self.name)
        
        # Initialize state with defaults
        self.st.setdefault("current", None)
        self.st.setdefault("history", [])
        self.st.setdefault("stats", {
            "adventures_started": 0,
            "adventures_completed": 0,
            "total_votes_cast": 0,
            "most_popular_location": None
        })
        
        # Track scheduled jobs for cleanup
        self._active_timers = set()
        
        # Save initial state
        bot.save()

    def on_load(self):
        """Initialize and restore adventure state on load."""
        # Clean up any leftover schedule tags
        schedule.clear(f"{self.name}-cleanup")
        
        # Check if we have an active adventure that needs timer restoration
        current = self.st.get("current")
        if current:
            close_time = float(current.get("close_epoch", 0))
            now = time.time()
            
            if now >= close_time:
                # Adventure expired while bot was offline
                self._close_adventure_round()
            else:
                # Schedule close for remaining time
                room = current.get("room")
                if room:
                    remaining_seconds = int(close_time - now)
                    if remaining_seconds > 0:
                        schedule.every(remaining_seconds).seconds.do(
                            lambda: self._close_adventure_scheduled(room)
                        ).tag(f"{self.name}-close-{room}")

    def on_unload(self):
        """Clean up on unload."""
        # Clear all timers
        current = self.st.get("current")
        if current:
            room = current.get("room")
            if room:
                schedule.clear(f"{self.name}-close-{room}")
        
        self._active_timers.clear()

    def _get_two_places(self) -> Tuple[str, str]:
        """Get two random adventure locations."""
        return tuple(random.sample(self.PLACES, 2))

    def _create_story(self, place: str) -> str:
        """Generate atmospheric story for the chosen location."""
        bits = random.sample(self.STORY_BITS, self.STORY_SENTENCES_PER_ROUND)
        lines = [bit.format(place=place) for bit in bits]
        return " ".join(lines)

    def _schedule_adventure_close(self, room: str) -> None:
        """Schedule the adventure to close."""
        # Clear any existing timers for this room
        schedule.clear(f"{self.name}-close-{room}")
        
        # Schedule with the schedule library
        schedule.every(self.VOTE_WINDOW_SEC).seconds.do(
            lambda: self._close_adventure_scheduled(room)
        ).tag(f"{self.name}-close-{room}")

    def _close_adventure_scheduled(self, expected_room: str):
        """Scheduled closer that verifies room matches."""
        current = self.st.get("current")
        if not current or current.get("room") != expected_room:
            return schedule.CancelJob
        
        self._close_adventure_round()
        return schedule.CancelJob

    def _close_adventure_round(self):
        """Close the current adventure and announce results."""
        current = self.st.get("current")
        if not current:
            return
            
        room = current["room"]
        options = current["options"]
        votes_1 = current.get("votes_1", [])
        votes_2 = current.get("votes_2", [])
        
        # Clean up the scheduled job
        schedule.clear(f"{self.name}-close-{room}")
        
        # Remove duplicates while preserving order
        votes_1 = list(dict.fromkeys(votes_1))
        votes_2 = list(dict.fromkeys(votes_2))
        
        c1, c2 = len(votes_1), len(votes_2)

        # Determine winner
        if c1 == c2:
            winner = random.choice(options)
            tie_note = " (tie—decided by the fates)"
        elif c1 > c2:
            winner = options[0]
            tie_note = ""
        else:
            winner = options[1]
            tie_note = ""

        # Generate story
        story = self._create_story(winner)

        # Announce results
        detail_1 = f"{c1} vote{'s' if c1 != 1 else ''}"
        detail_2 = f"{c2} vote{'s' if c2 != 1 else ''}"
        
        try:
            self.bot.connection.privmsg(
                room, 
                f"Votes tallied: 1. {options[0]} → {detail_1}; 2. {options[1]} → {detail_2}.{tie_note}"
            )
            self.bot.connection.privmsg(room, f"To {winner} then. {story}")
        except Exception as e:
            print(f"[adventure] error announcing results: {e}", file=sys.stderr)

        # Record in history
        entry = {
            "when": datetime.now(UTC).isoformat(),
            "room": room,
            "options": list(options),
            "votes_1": votes_1,
            "votes_2": votes_2,
            "winner": winner,
            "starter": current.get("starter"),
            "vote_counts": [c1, c2]
        }
        
        history = self.st.get("history", [])
        history.append(entry)
        
        # Keep history manageable
        if len(history) > self.MAX_HISTORY_ENTRIES:
            history = history[-self.MAX_HISTORY_ENTRIES:]
        
        # Update statistics
        stats = self.st.get("stats", {})
        stats["adventures_completed"] = stats.get("adventures_completed", 0) + 1
        stats["total_votes_cast"] = stats.get("total_votes_cast", 0) + c1 + c2
        
        # Track most popular location
        location_counts = {}
        for h in history:
            winner_loc = h.get("winner")
            if winner_loc:
                location_counts[winner_loc] = location_counts.get(winner_loc, 0) + 1
        
        if location_counts:
            stats["most_popular_location"] = max(location_counts, key=location_counts.get)
        
        # Update state
        self.st["history"] = history
        self.st["current"] = None
        self.st["stats"] = stats
        self.bot.save()

    def _add_vote(self, username: str, vote_option: int) -> bool:
        """Add a vote for the specified option (1 or 2)."""
        current = self.st.get("current")
        if not current:
            return False
            
        # Check if voting window is still open
        close_time = float(current.get("close_epoch", 0))
        if time.time() > close_time:
            self._close_adventure_round()
            return True
        
        votes_1 = current.get("votes_1", [])
        votes_2 = current.get("votes_2", [])
        
        # Remove user from both lists (prevent double voting)
        if username in votes_1:
            votes_1.remove(username)
        if username in votes_2:
            votes_2.remove(username)
        
        # Add to appropriate list
        if vote_option == 1:
            votes_1.append(username)
        else:
            votes_2.append(username)
        
        # Update state
        current["votes_1"] = votes_1
        current["votes_2"] = votes_2
        self.st["current"] = current
        self.bot.save()
        
        return True

    def on_pubmsg(self, connection, event, msg, username):
        room = event.target

        # Status command
        if self.RE_CMD_STATUS.match(msg):
            current = self.st.get("current")
            if current and current.get("room") == room:
                options = current["options"]
                close_time = float(current.get("close_epoch", 0))
                secs_left = max(0, int(close_time - time.time()))
                
                votes_1 = len(current.get("votes_1", []))
                votes_2 = len(current.get("votes_2", []))
                
                connection.privmsg(
                    room,
                    f"{username}, voting in progress: 1. {options[0]} ({votes_1} votes) or 2. {options[1]} ({votes_2} votes) — {secs_left}s remaining."
                )
            else:
                connection.privmsg(room, f"{username}, there is no adventure afoot.")
            return True

        # History command
        if self.RE_CMD_LAST.match(msg):
            history = self.st.get("history", [])
            if not history:
                connection.privmsg(room, f"{username}, no adventures have been logged yet.")
                return True
            
            last = history[-1]
            options = last["options"]
            vote_counts = last.get("vote_counts", [0, 0])
            winner = last["winner"]
            when = last["when"][:16]  # Truncate timestamp
            
            connection.privmsg(
                room,
                f"{username}, last adventure: 1. {options[0]} ({vote_counts[0]}) vs 2. {options[1]} ({vote_counts[1]}) → {winner} at {when}."
            )
            return True

        # Start adventure command
        if self.RE_CMD_START.match(msg):
            # Check if adventure already running in this room
            current = self.st.get("current")
            if current and current.get("room") == room:
                options = current["options"]
                close_time = float(current.get("close_epoch", 0))
                secs_left = max(0, int(close_time - time.time()))
                
                connection.privmsg(
                    room, 
                    f"An adventure is already underway: 1. {options[0]} or 2. {options[1]} — {secs_left}s left."
                )
                return True

            # Check if there's an adventure in a different room
            if current and current.get("room") != room:
                other_room = current.get("room")
                connection.privmsg(
                    room,
                    f"I'm afraid there's already an adventure underway in {other_room}. "
                    "One expedition at a time, if you please."
                )
                return True

            # Start new adventure
            options = self._get_two_places()
            title = self.bot.title_for(username)
            
            connection.privmsg(
                room,
                f"Very good, {title}; an adventure it is. "
                f"Shall we set out for 1. {options[0]} or 2. {options[1]}? Say 1 or 2 to vote."
            )
            
            close_time = time.time() + self.VOTE_WINDOW_SEC
            new_adventure = {
                "room": room,
                "options": options,
                "votes_1": [],
                "votes_2": [],
                "starter": username,
                "close_epoch": close_time,
                "started_at": datetime.now(UTC).isoformat()
            }
            
            # Update state and schedule close
            self.st["current"] = new_adventure
            self.bot.save()
            self._schedule_adventure_close(room)
            
            # Update stats
            stats = self.st.get("stats", {})
            stats["adventures_started"] = stats.get("adventures_started", 0) + 1
            self.st["stats"] = stats
            
            return True

        # Handle votes
        current = self.st.get("current")
        if current and current.get("room") == room:
            # Check if voting is still open
            if time.time() > float(current.get("close_epoch", 0)):
                # Adventure expired, close it
                self._close_adventure_round()
                return True

            # Process votes
            if self.RE_VOTE_1.match(msg):
                self._add_vote(username, 1)
                return True
                
            if self.RE_VOTE_2.match(msg):
                self._add_vote(username, 2)
                return True

        return False