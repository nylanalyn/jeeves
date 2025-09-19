# modules/bell.py
# A reaction-based game for Jeeves where users answer a service bell.
import random
import re
import time
import schedule
from datetime import datetime, timezone
from typing import Optional
from .base import SimpleCommandModule, admin_required

UTC = timezone.utc

def setup(bot, config):
    return Bell(bot, config)

class Bell(SimpleCommandModule):
    name = "bell"
    version = "1.0.0"
    description = "A reaction game to answer the service bell."

    # Different ways Jeeves can announce the bell.
    RING_ANNOUNCEMENTS = [
        "The service bell has been rung!",
        "Ah, the bell. A summons awaits.",
        "Someone has rung for service!",
        "The bell sounds. Who shall be the first to attend?",
        "A sharp ring from the drawing-room bell!"
    ]
    
    # The command to win the game.
    ANSWER_PATTERN = re.compile(r"^\s*!answer\s*$", re.IGNORECASE)

    def __init__(self, bot, config):
        super().__init__(bot)
        
        self.MIN_HOURS_BETWEEN_RINGS = config.get("min_hours_between_rings", 2)
        self.MAX_HOURS_BETWEEN_RINGS = config.get("max_hours_between_rings", 12)
        self.RESPONSE_WINDOW_SECONDS = config.get("response_window_seconds", 30)

        # State initialization
        self.set_state("scores", self.get_state("scores", {}))
        self.set_state("current_round", self.get_state("current_round", None))
        self.set_state("stats", self.get_state("stats", {"rounds_played": 0, "total_answers": 0}))
        self.save_state()

    def _register_commands(self):
        self.register_command(r"^\s*!bell\s+stats\s*$", self._cmd_stats,
                              name="bell stats", admin_only=True, description="Show game statistics.")
        self.register_command(r"^\s*!bell\s+score(?:\s+(\S+))?\s*$", self._cmd_score,
                              name="bell score", description="Check your score or someone else's. Usage: !bell score [nick]")
        self.register_command(r"^\s*!bell\s+top(?:\s+(\d+))?\s*$", self._cmd_top,
                              name="bell top", description="Show the top players. Usage: !bell top [count]")

    def on_load(self):
        super().on_load()
        schedule.clear(self.name)
        # If the bot restarts mid-game, cancel it.
        if self.get_state("current_round"):
            self.set_state("current_round", None)
            self.save_state()
        self._schedule_next_ring()

    def on_unload(self):
        super().on_unload()
        schedule.clear(self.name)

    def on_pubmsg(self, connection, event, msg, username):
        if super().on_pubmsg(connection, event, msg, username):
            return True

        current_round = self.get_state("current_round")
        if not current_round or not current_round.get("active"):
            return False

        if self.ANSWER_PATTERN.match(msg):
            # We have a winner!
            reaction_time = time.time() - current_round["start_time"]
            winner_nick = username
            
            # End the round immediately
            self._end_round(winner=winner_nick, reaction_time=reaction_time)
            return True
        return False

    def _schedule_next_ring(self):
        """Schedules the next time the bell will ring."""
        delay_hours = random.uniform(self.MIN_HOURS_BETWEEN_RINGS, self.MAX_HOURS_BETWEEN_RINGS)
        schedule.every(delay_hours).hours.do(self._ring_the_bell).tag(self.name, "next_ring")

    def _ring_the_bell(self):
        """Starts a new round of the game."""
        # Ensure only one game runs at a time
        if self.get_state("current_round"):
            return schedule.CancelJob

        announcement = random.choice(self.RING_ANNOUNCEMENTS)
        self.safe_say(announcement)

        new_round = {
            "room": self.bot.primary_channel,
            "active": True,
            "start_time": time.time()
        }
        self.set_state("current_round", new_round)
        self.save_state()

        # Schedule the end of the round if no one answers
        schedule.every(self.RESPONSE_WINDOW_SECONDS).seconds.do(self._end_round).tag(self.name, "end_round")
        
        # This job has run, so cancel it. A new one will be scheduled when the round ends.
        return schedule.CancelJob

    def _end_round(self, winner: Optional[str] = None, reaction_time: Optional[float] = None):
        """Ends the current round, updates scores, and schedules the next one."""
        schedule.clear("end_round")
        current_round = self.get_state("current_round")
        if not current_round: return

        if winner:
            title = self.bot.title_for(winner)
            self.safe_say(f"Excellent reflexes, {title}! You answered in {reaction_time:.2f} seconds.")
            
            # Update scores
            scores = self.get_state("scores", {})
            scores[winner.lower()] = scores.get(winner.lower(), 0) + 1
            self.set_state("scores", scores)
            
            stats = self.get_state("stats")
            stats["total_answers"] += 1
            self.set_state("stats", stats)

        else:
            self.safe_say("It appears no one is available to answer the bell. Very well.")

        stats = self.get_state("stats")
        stats["rounds_played"] += 1
        self.set_state("stats", stats)
        self.set_state("current_round", None)
        self.save_state()
        
        # Schedule the next game
        self._schedule_next_ring()
        return schedule.CancelJob

    # --- Commands ---
    @admin_required
    def _cmd_stats(self, connection, event, msg, username, match):
        stats = self.get_state("stats")
        scores = self.get_state("scores", {})
        unique_players = len(scores)
        self.safe_reply(connection, event, 
            f"Bell Game Stats: {stats['rounds_played']} rounds played, "
            f"{stats['total_answers']} bells answered by {unique_players} unique players.")
        return True

    def _cmd_score(self, connection, event, msg, username, match):
        target_user = match.group(1) or username
        scores = self.get_state("scores", {})
        user_score = scores.get(target_user.lower(), 0)
        
        if target_user.lower() == username.lower():
            self.safe_reply(connection, event, f"{username}, you have answered the bell {user_score} time(s).")
        else:
            self.safe_reply(connection, event, f"{target_user} has answered the bell {user_score} time(s).")
        return True

    def _cmd_top(self, connection, event, msg, username, match):
        count_str = match.group(1)
        count = int(count_str) if count_str and count_str.isdigit() else 5
        
        scores = self.get_state("scores", {})
        if not scores:
            self.safe_reply(connection, event, "No scores have been recorded yet.")
            return True
            
        sorted_scores = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        top_players = sorted_scores[:count]
        
        leaderboard = ", ".join([f"{nick}({score})" for nick, score in top_players])
        self.safe_reply(connection, event, f"Top {len(top_players)} responders: {leaderboard}")
        return True

