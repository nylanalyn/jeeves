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
    version = "2.1.1" # Fixed user lookup for top scores
    description = "A reaction game to answer the service bell."

    def __init__(self, bot, config):
        super().__init__(bot)
        self.set_state("scores", self.get_state("scores", {})) # Keyed by user_id
        self.set_state("active_bell", self.get_state("active_bell", None))
        self.set_state("next_ring_time", self.get_state("next_ring_time", None))
        self.save_state()

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
        allowed_channels = self.get_config_value("allowed_channels", default=[])
        if not allowed_channels:
            return

        min_hours = self.get_config_value("min_hours_between_rings", default=1)
        max_hours = self.get_config_value("max_hours_between_rings", default=8)
        delay_hours = random.uniform(min_hours, max_hours)
        next_ring_time = datetime.now(UTC) + timedelta(hours=delay_hours)
        
        self.set_state("next_ring_time", next_ring_time.isoformat())
        self.save_state()
        
        schedule.every(delay_hours * 3600).seconds.do(self._ring_the_bell).tag(self.name, "ring")

    def _ring_the_bell(self):
        schedule.clear("ring")
        
        allowed_channels = self.get_config_value("allowed_channels", default=[])
        active_channels = [room for room in allowed_channels if room in self.bot.joined_channels and self.is_enabled(room)]
        
        if not active_channels:
            self._schedule_next_bell()
            return schedule.CancelJob

        response_window = self.get_config_value("response_window_seconds", default=15)

        for room in active_channels:
            self.safe_say("The service bell has been rung!", target=room)
        
        end_time = time.time() + response_window
        self.set_state("active_bell", {"end_time": end_time})
        self.set_state("next_ring_time", None)
        self.save_state()

        schedule.every(response_window).seconds.do(self._end_bell_round).tag(self.name, "end")
        return schedule.CancelJob

    def _end_bell_round(self):
        if self.get_state("active_bell"):
            self.set_state("active_bell", None)
            self.save_state()
            allowed_channels = self.get_config_value("allowed_channels", default=[])
            active_channels = [room for room in allowed_channels if room in self.bot.joined_channels and self.is_enabled(room)]
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

        users_module = self.bot.pm.plugins.get("users")
        user_map = {}
        if users_module:
            user_map = users_module.get_state("user_map", {})
        else:
            self.log_debug("Could not get 'users' module instance to resolve nicknames for top scores.")

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

