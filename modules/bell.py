# modules/bell.py
# A reaction game where users "answer" a service bell.
import random
import re
import schedule
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from .base import SimpleCommandModule, admin_required

UTC = timezone.utc

def setup(bot, config):
    return Bell(bot, config)

class Bell(SimpleCommandModule):
    name = "bell"
    version = "2.0.0" # UUID Refactor
    description = "A reaction game to answer the service bell."

    def __init__(self, bot, config):
        super().__init__(bot)
        self.set_state("scores", self.get_state("scores", {})) # Keyed by user_id
        self.set_state("active_bell", self.get_state("active_bell", None))
        self.set_state("next_ring_time", self.get_state("next_ring_time", None))
        self.on_config_reload(config)

    def on_config_reload(self, config):
        bell_config = config.get(self.name, {})
        self.MIN_HOURS = bell_config.get("min_hours_between_rings", 1)
        self.MAX_HOURS = bell_config.get("max_hours_between_rings", 8)
        self.WINDOW = bell_config.get("response_window_seconds", 15)
        self.ALLOWED_CHANNELS = bell_config.get("allowed_channels", [])

    def on_load(self):
        super().on_load()
        schedule.clear(self.name)
        
        next_ring_str = self.get_state("next_ring_time")
        if next_ring_str:
            next_ring_time = datetime.fromisoformat(next_ring_str)
            now = datetime.now(UTC)

            if now >= next_ring_time:
                self._ring_the_bell()
            else:
                remaining_seconds = (next_ring_time - now).total_seconds()
                if remaining_seconds > 0:
                    schedule.every(remaining_seconds).seconds.do(self._ring_the_bell).tag(self.name, "ring")
        elif not self.get_state("active_bell"):
            self._schedule_next_bell()

    def on_unload(self):
        super().on_unload()
        schedule.clear(self.name)

    def _register_commands(self):
        self.register_command(r"^\s*!answer\s*$", self._cmd_answer,
                              name="answer", description="Answer the service bell when it rings.")
        self.register_command(r"^\s*!bell\s+score\s*$", self._cmd_score_self,
                              name="bell score", description="Check your service bell score.")
        self.register_command(r"^\s*!bell\s+top\s*$", self._cmd_top,
                              name="bell top", description="Show the top 5 most attentive users.")
        self.register_command(r"^\s*!bell\s+ring\s*$", self._cmd_ring,
                              name="bell ring", admin_only=True, description="Force the bell to ring now.")

    def _schedule_next_bell(self):
        if not self.ALLOWED_CHANNELS:
            return

        delay_hours = random.uniform(self.MIN_HOURS, self.MAX_HOURS)
        next_ring_time = datetime.now(UTC) + timedelta(hours=delay_hours)
        
        self.set_state("next_ring_time", next_ring_time.isoformat())
        self.save_state()
        
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
        self.set_state("next_ring_time", None)
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
        
        schedule.clear("end")
        self.set_state("active_bell", None)
        
        user_id = self.bot.get_user_id(username)
        scores = self.get_state("scores", {})
        scores[user_id] = scores.get(user_id, 0) + 1
        self.set_state("scores", scores)
        self.save_state()

        self.safe_reply(connection, event, f"Congratulations, {self.bot.title_for(username)}. You answered the bell with admirable promptness.")
        self._schedule_next_bell()
        return True

    def _cmd_score_self(self, connection, event, msg, username, match):
        user_id = self.bot.get_user_id(username)
        score = self.get_state("scores", {}).get(user_id, 0)
        self.safe_reply(connection, event, f"{self.bot.title_for(username)}, you have answered the bell {score} time{'s' if score != 1 else ''}.")
        return True

    def _cmd_top(self, connection, event, msg, username, match):
        scores = self.get_state("scores", {})
        if not scores:
            self.safe_reply(connection, event, "No one has yet answered the call of duty.")
            return True

        user_module_state = self.bot.get_module_state("users")
        user_map = user_module_state.get("user_map", {})

        sorted_scores = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:5]
        
        top_list = []
        for user_id, score in sorted_scores:
            user_profile = user_map.get(user_id)
            display_nick = user_profile.get("canonical_nick", "An unknown user") if user_profile else "An unknown user"
            top_list.append(f"{display_nick} ({score})")
            
        self.safe_reply(connection, event, f"The most attentive members of the household: {', '.join(top_list)}")
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

