# modules/bell.py
# A reaction game where users "answer" a service bell.
import random
import re
import schedule
import sys
import time
from typing import Optional, List, Dict, Any
from .base import SimpleCommandModule, admin_required

def setup(bot, config):
    return Bell(bot, config)

class Bell(SimpleCommandModule):
    name = "bell"
    version = "1.2.0"
    description = "A reaction game to answer the service bell."

    def __init__(self, bot, config):
        super().__init__(bot)
        self._load_config(config)

        self.set_state("scores", self.get_state("scores", {}))
        self.set_state("active_bell", self.get_state("active_bell", None))
        self.save_state()

    def _load_config(self, config: Dict[str, Any]):
        self.MIN_HOURS = config.get("min_hours_between_rings", 1)
        self.MAX_HOURS = config.get("max_hours_between_rings", 8)
        self.WINDOW = config.get("response_window_seconds", 15)
        self.ALLOWED_CHANNELS = config.get("allowed_channels", [])

    def on_config_reload(self, new_config: Dict[str, Any]):
        old_min = self.MIN_HOURS
        old_max = self.MAX_HOURS
        
        self._load_config(new_config)

        if (old_min, old_max) != (self.MIN_HOURS, self.MAX_HOURS):
            print(f"[{self.name}] Bell timing changed, rescheduling.", file=sys.stderr)
            schedule.clear("ring")
            self._schedule_next_bell()

    def _register_commands(self):
        self.register_command(r"^\s*!answer\s*$", self._cmd_answer,
                              name="answer", description="Answer the service bell when it rings.")
        self.register_command(r"^\s*!bell\s+score\s*$", self._cmd_score_self,
                              name="bell score", description="Check your service bell score.")
        self.register_command(r"^\s*!bell\s+top\s*$", self._cmd_top,
                              name="bell top", description="Show the top 5 most attentive users.")
        self.register_command(r"^\s*!bell\s+stats\s*$", self._cmd_stats,
                              name="bell stats", admin_only=True, description="Show service bell statistics.")
        self.register_command(r"^\s*!bell\s+ring\s*$", self._cmd_ring,
                              name="bell ring", admin_only=True, description="Force the bell to ring now.")

    def on_load(self):
        super().on_load()
        schedule.clear(self.name)
        self._schedule_next_bell()

    def on_unload(self):
        super().on_unload()
        schedule.clear(self.name)

    def _schedule_next_bell(self):
        if not self.ALLOWED_CHANNELS:
            return

        delay_hours = random.uniform(self.MIN_HOURS, self.MAX_HOURS)
        schedule.every(delay_hours).hours.do(self._ring_the_bell).tag(self.name, "ring")

    def _ring_the_bell(self):
        schedule.clear("ring")
        active_channels = [room for room in self.ALLOWED_CHANNELS if room in self.bot.joined_channels]
        
        if not active_channels:
            self._schedule_next_bell()
            return schedule.CancelJob

        for room in active_channels:
            self.safe_say("The service bell has been rung!", target=room)
        
        end_time = time.time() + self.WINDOW
        self.set_state("active_bell", {"end_time": end_time})
        self.save_state()

        schedule.every(self.WINDOW).seconds.do(self._end_bell_round).tag(self.name, "end")
        return schedule.CancelJob

    def _end_bell_round(self):
        if self.get_state("active_bell"):
            self.set_state("active_bell", None)
            self.save_state()
            active_channels = [room for room in self.ALLOWED_CHANNELS if room in self.bot.joined_channels]
            for room in active_channels:
                self.safe_say("Too slow. The bell has been silenced.", target=room)
        
        self._schedule_next_bell()
        return schedule.CancelJob

    def _cmd_answer(self, connection, event, msg, username, match):
        active_bell = self.get_state("active_bell")
        
        if not active_bell:
            self.safe_reply(connection, event, f"The bell is silent, {self.bot.title_for(username)}.")
            return True
        
        if time.time() > active_bell["end_time"]:
            self.safe_reply(connection, event, f"You are too late, {self.bot.title_for(username)}. The moment has passed.")
            return True

        schedule.clear("end")
        self.set_state("active_bell", None)
        
        scores = self.get_state("scores", {})
        user_key = username.lower()
        scores[user_key] = scores.get(user_key, 0) + 1
        self.set_state("scores", scores)
        self.save_state()

        self.safe_reply(connection, event, f"Congratulations, {self.bot.title_for(username)}. You answered the bell with admirable promptness.")
        self._schedule_next_bell()
        return True

    def _cmd_score_self(self, connection, event, msg, username, match):
        user_key = username.lower()
        score = self.get_state("scores", {}).get(user_key, 0)
        self.safe_reply(connection, event, f"{self.bot.title_for(username)}, you have answered the bell {score} time{'s' if score != 1 else ''}.")
        return True

    def _cmd_top(self, connection, event, msg, username, match):
        scores = self.get_state("scores", {})
        if not scores:
            self.safe_reply(connection, event, "No one has yet answered the call of duty.")
            return True

        sorted_scores = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        top_five = sorted_scores[:5]
        
        response = "The most attentive members of the household: "
        response += ", ".join([f"{nick} ({score})" for nick, score in top_five])
        self.safe_reply(connection, event, response)
        return True

    @admin_required
    def _cmd_stats(self, connection, event, msg, username, match):
        scores = self.get_state("scores", {})
        total_players = len(scores)
        total_answers = sum(scores.values())
        self.safe_reply(connection, event, f"Service Bell Stats: {total_players} users have answered a total of {total_answers} times.")
        return True

    @admin_required
    def _cmd_ring(self, connection, event, msg, username, match):
        if self.get_state("active_bell"):
            self.safe_reply(connection, event, "The bell is already ringing.")
            return True
        
        schedule.clear("ring")
        self._ring_the_bell()
        self.safe_reply(connection, event, "As you wish. The bell has been rung.")
        return True

