# modules/sailing.py
# Nautical responses for a specific user's SAIL triggers
import re
import random
import time
import functools
from typing import Dict, Any, Optional, List, Pattern
from .base import SimpleCommandModule, admin_required

def setup(bot: Any) -> 'Sailing':
    return Sailing(bot)

class Sailing(SimpleCommandModule):
    name = "sailing"
    version = "2.0.0" # Dynamic configuration refactor
    description = "Responds to the 'SAIL' trigger from a specific user with nautical lore."

    NAUTICAL_RESPONSES: List[str] = [
        "Aye, {title}! The wind's fair and the tide's turning - time to splice the mainbrace!",
        "Steady as she goes, {title}! Mind the mizzen and watch for squalls off the starboard bow.",
        "Heave away, {title}! The bosun's pipe calls and the capstan awaits your shanty.",
        "By the beard of Neptune, {title}! The sea's singing her siren song once more.",
        "Fair winds and following seas, {title}! May your sheets stay taut and your compass true.",
        "Hoist the burgee, {title}! The ancient mariners say a red sky at night means sailor's delight.",
        "Batten down the hatches, {title}! Remember: one hand for the ship, one for yourself.",
        "The albatross circles, {title} - but we'll not be shooting any today, if Coleridge is to be believed.",
        "Mind the doldrums, {title}! Even the Trade Winds must pause to gather their strength.",
        "Sheet home the topsails, {title}! The old salts say the sea never forgives the unprepared.",
        "Avast, {title}! Soon may the Wellerman come, to bring us sugar and tea and rum!",
        "Three sheets to the wind already, {title}? Save some grog for the crossing!",
        "Aye, {title}! Dead men tell no tales, but living sailors spin the finest yarns.",
        "Shiver me timbers, {title}! The kraken stirs, but we've got plenty of salt to ward it off.",
        "Cast off the bowlines, {title}! The harbor's safe, but that's not where the adventure lies.",
        "Man the halyards, {title}! There's a whale off the lee bow, and she's breaching magnificent!",
        "Steady on your heading, {title}! Even Magellan had to tack into the wind sometimes.",
        "Yo ho ho, {title}! The binnacle's lit, the charts are spread - let's find that horizon.",
        "Reef the mainsail, {title}! A sailor who ignores the sky learns his lessons the hard way.",
        "All hands on deck, {title}! The phosphorescence in the wake means we're making good speed.",
        "Strike the bell, {title}! Eight bells and all's well - time to change the watch.",
        "Break out the sea anchor, {title}! Sometimes the bravest thing is to ride out the storm.",
        "Trim those jibs, {title}! A well-trimmed sail is worth three strong backs at the oars.",
        "The compass rose beckons, {title}! North, south, east, or west - they all lead to adventure.",
        "Belay that, {title}! The old hands say when the gulls fly inland, it's time to secure for weather.",
        "Dead reckoning time, {title}! Trust your sextant, trust your chronometer, trust the stars.",
        "Scuttle the rumor, {title} - mermaids are real, but they're terrible at keeping secrets!",
        "The crow's nest calls out, {title}! Land ho? Nay, just another wandering iceberg dressed as an island.",
        "Splice the mainbrace again, {title}! If we're going down, at least we'll go down singing!",
        "Chart a new course, {title}! The Sargasso Sea won't navigate itself out of your way.",
    ]

    def __init__(self, bot: Any) -> None:
        super().__init__(bot)
        self.static_keys: List[str] = ["nautical_responses"]
        self.set_state("last_response_time", self.get_state("last_response_time", 0.0))
        self.save_state()
        self.RE_SAIL: Pattern[str] = re.compile(r'\bSAIL\b')

    def _register_commands(self) -> None:
        # This module has no !commands.
        pass

    def on_ambient_message(self, connection, event, msg: str, username: str) -> bool:
        if not self.is_enabled(event.target):
            return False

        target_user = self.get_config_value("target_user", event.target, "witeshark2")
        
        if username.lower() == target_user.lower() and self.RE_SAIL.search(msg):
            cooldown = self.get_config_value("cooldown_seconds", event.target, 5.0)
            now = time.time()
            if now - self.get_state("last_response_time", 0.0) >= cooldown:
                self.set_state("last_response_time", now)
                self.save_state()
                title = self.bot.title_for(username)
                response = random.choice(self.NAUTICAL_RESPONSES).format(title=title)
                self.safe_reply(connection, event, response)
                return True
        return False
