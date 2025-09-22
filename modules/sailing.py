# modules/sailing.py
# Nautical responses for witeshark2's SAIL triggers
import re
import random
import time
import functools
from typing import Dict, Any, Optional
from .base import SimpleCommandModule, admin_required

def setup(bot, config):
    return Sailing(bot, config)

class Sailing(SimpleCommandModule):
    name = "sailing"
    version = "1.3.0"
    description = "Responds to the 'SAIL' trigger from a specific user with nautical lore."
    
    NAUTICAL_RESPONSES = [ "Aye, {title}! The wind's fair and the tide's turning - time to splice the mainbrace!", "Steady as she goes, {title}! Mind the mizzen and watch for squalls off the starboard bow.", "Heave away, {title}! The bosun's pipe calls and the capstan awaits your shanty.", "By the beard of Neptune, {title}! The sea's singing her siren song once more.", "Fair winds and following seas, {title}! May your sheets stay taut and your compass true.", "Hoist the burgee, {title}! The ancient mariners say a red sky at night means sailor's delight.", "Batten down the hatches, {title}! Remember: one hand for the ship, one for yourself.", "The albatross circles, {title} - but we'll not be shooting any today, if Coleridge is to be believed.", "Mind the doldrums, {title}! Even the Trade Winds must pause to gather their strength.", "Sheet home the topsails, {title}! The old salts say the sea never forgives the unprepared.", ]

    def __init__(self, bot, config):
        super().__init__(bot)
        
        self.TARGET_USER = config.get("target_user", "witeshark2")
        self.COOLDOWN = config.get("cooldown", 5.0)

        self.set_state("last_response_time", self.get_state("last_response_time", 0.0))
        self.save_state()
        
        self.RE_SAIL = re.compile(r'\bSAIL\b')

    def _register_commands(self):
        # This module has no !commands.
        pass

    def on_ambient_message(self, connection, event, msg: str, username: str) -> bool:
        if username.lower() == self.TARGET_USER.lower() and self.RE_SAIL.search(msg):
            now = time.time()
            if now - self.get_state("last_response_time", 0.0) >= self.COOLDOWN:
                self.set_state("last_response_time", now)
                self.save_state()
                title = self.bot.title_for(username)
                response = random.choice(self.NAUTICAL_RESPONSES).format(title=title)
                self.safe_reply(connection, event, response)
                return True
        return False

