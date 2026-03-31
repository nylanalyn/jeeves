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
#        "Aye, {title}! The wind's fair and the tide's turning - time to splice the mainbrace!",
#        "Steady as she goes, {title}! Mind the mizzen and watch for squalls off the starboard bow.",
#        "Heave away, {title}! The bosun's pipe calls and the capstan awaits your shanty.",
#        "By the beard of Neptune, {title}! The sea's singing her siren song once more.",
#        "Fair winds and following seas, {title}! May your sheets stay taut and your compass true.",
#        "Hoist the burgee, {title}! The ancient mariners say a red sky at night means sailor's delight.",
#        "Batten down the hatches, {title}! Remember: one hand for the ship, one for yourself.",
#        "The albatross circles, {title} - but we'll not be shooting any today, if Coleridge is to be believed.",
#        "Mind the doldrums, {title}! Even the Trade Winds must pause to gather their strength.",
#        "Sheet home the topsails, {title}! The old salts say the sea never forgives the unprepared.",
#        "Avast, {title}! Soon may the Wellerman come, to bring us sugar and tea and rum!",
#        "Three sheets to the wind already, {title}? Save some grog for the crossing!",
#        "Aye, {title}! Dead men tell no tales, but living sailors spin the finest yarns.",
#        "Shiver me timbers, {title}! The kraken stirs, but we've got plenty of salt to ward it off.",
#        "Cast off the bowlines, {title}! The harbor's safe, but that's not where the adventure lies.",
#        "Man the halyards, {title}! There's a whale off the lee bow, and she's breaching magnificent!",
#        "Steady on your heading, {title}! Even Magellan had to tack into the wind sometimes.",
#        "Yo ho ho, {title}! The binnacle's lit, the charts are spread - let's find that horizon.",
#        "Reef the mainsail, {title}! A sailor who ignores the sky learns his lessons the hard way.",
#        "All hands on deck, {title}! The phosphorescence in the wake means we're making good speed.",
#        "Strike the bell, {title}! Eight bells and all's well - time to change the watch.",
#        "Break out the sea anchor, {title}! Sometimes the bravest thing is to ride out the storm.",
#        "Trim those jibs, {title}! A well-trimmed sail is worth three strong backs at the oars.",
#        "The compass rose beckons, {title}! North, south, east, or west - they all lead to adventure.",
#        "Belay that, {title}! The old hands say when the gulls fly inland, it's time to secure for weather.",
#        "Dead reckoning time, {title}! Trust your sextant, trust your chronometer, trust the stars.",
#        "Scuttle the rumor, {title} - mermaids are real, but they're terrible at keeping secrets!",
#        "The crow's nest calls out, {title}! Land ho? Nay, just another wandering iceberg dressed as an island.",
#        "Splice the mainbrace again, {title}! If we're going down, at least we'll go down singing!",
#        "Chart a new course, {title}! The Sargasso Sea won't navigate itself out of your way.",

        "Mind the telltales, {title}! They're not just decorations—they're telling you everything about the wind.",
        "Cleat the dock lines, {title}! A cleat isn't a cleat is not a cleat—cl掌 cleats need to be twisted clockwise!",
        "Starboard tack, {title}! Port tack gives way, but starboard always has the right of way—Rule 10, COLREGS.",
        "Turbulence at the dock, {title}! That ferry wake isn't going to flatten itself—patience, captain.",
        "Check your EPIRB, {title}! It's not the sexiest piece of kit, but it'll sure find you when everything else fails.",
        "Full and by, {title}! The wind's on your nose but you're still making six knots—classic close-hauled bliss.",
        "The Gulf Stream's shifted, {title}! No wonder the water temperature dropped two degrees overnight.",
        "MOB procedure, {title}! Reach, rack, pitch, punch—the quick-stop method isn't quick if you skip the reach.",
        "That shore power indicator, {title}! Red means reverse polarity, and red means don't plug in that shore power cord.",
        "Aye, {title}! The KISS principle applies to anchoring too—scope ratio matters more than chain length.",
        "Tide's running four knots, {title}! Set your drift angle now or you'll be fetching up against the pier.",
        "Radar reflector up, {title}! Those fishing boat returns aren't going to disappear on their own.",
        "Handheld VHF channel 16, {title}! Mayday, mayday—but only if you really need it, not if you've just lost your anchor.",
        "Hove to under storm jib, {title}! Sometimes the bravest thing a sailor does is heave to and wait for morning.",
        "The ASI multifunction display, {title}! It's not a fishfinder—just because it's on the same network doesn't mean it's the same.",
        "Autopilot compass calibration, {title}! Eight figure-eights through the marina and you'll finally have deviation under 1°.",
        "Aye, {title}! Beneteau, Hunter, Jeanneau—they all say the same thing: less winch handle, more wine in the harbor.",
        "Cowichan Bay on a falling tide, {title}! The dock's already listing six inches and it's only been an hour.",
        "SOG over ground or SOG through water, {title}? Current set makes all the difference on the passage to Victoria.",
        "Garmin CHIRP sonar, {title}! Traditional sonar is so 2005—CHIRP is where it's at for distinguishing bait from bass.",
        "The masthead vane's spinning, {title}! That means the wind's clocked past 45 knots—time to reef before you reef.",
        "Aye, {title}! J/105 fleet racing and they're all over you like a bad rash—duck downwind or take your punishment.",
        "Catalina crossing in August, {title}! Fifty miles of nothing but heat shimmer and your crew asking 'are we there yet.'",
        "Fenders deployed, {title}! The local ferry captain doesn't care about your topsides, only his own schedule.",
        "The holding tank baffles, {title}! They slosh and they shift and they somehow always find the one seasick crewmember.",
        "Dodger up, {title}! Rain gear on, rain gear off—welcome to the Salish Sea in November.",
        "That Raymarine Seatalk alarm, {title}! It's not screaming at you for fun—something on the NMEA network is actually wrong.",
        "Aye, {title}! Knots are chaos—but 7 knots through 4 knots of current still gets you 3 knots over ground toward that marina.",
        "The head sail's luffing, {title}! Ease the sheet a smidge—just enough to keep that telltale streaming, not fluttering.",
        "Southern Strait at slack, {title}! Fifteen minutes of almost-nothing current before the flood rips through again.",
        "Headsail change in 20 knots, {title}! The #3 genoa is up and you're wondering why you don't have roller furling.",
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
