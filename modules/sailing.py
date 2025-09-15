# modules/sailing.py
# Nautical responses for witeshark2's SAIL triggers
import re
import random
import time
from typing import Dict, Any, Optional
from .base import ResponseModule, admin_required

def setup(bot):
    return Sailing(bot)

class Sailing(ResponseModule):
    name = "sailing"
    version = "1.1.0"
    description = "Responds to the 'SAIL' trigger from a specific user with nautical lore."
    
    # Target user
    TARGET_USER = "witeshark2"
    
    # Cooldown to prevent spam (in seconds)
    COOLDOWN = 5.0
    
    # Deep nautical responses with obscure maritime lore
    NAUTICAL_RESPONSES = [
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
        "Avast, {title}! Time to bend on the storm jib and reef the mainsail - weather's turning.",
        "Belay that order, {title}! The tide's on the make and the glass is falling fast.",
        "Stand by to wear ship, {title}! We'll box the compass before this day is through.",
        "Ready about, {title}! Mind your head when the boom comes across - no landsman's mistake here.",
        "Heave the lead, {title}! Mark twain and by the deep six - safe water beneath our keel.",
        "Splice the yards, {title}! Even Drake himself would approve of such sailing weather.",
        "Hoist the jack, {title}! The ghost of old Blackbeard would be proud to see such seamanship.",
        "Trim the sheets, {title}! Cook's Endeavour never saw finer sailing conditions than these.",
        "Bear away, {title}! Magellan himself would have blessed winds like these for the straits.",
        "Set the stunsails, {title}! Even the Flying Dutchman would envy such a fair breeze.",
        "Hard alee, {title}! Remember - when in doubt, let it out - never cleat a sheet in a blow.",
        "Ease the halyard, {title}! A yacht's not a ship until she's felt blue water beneath her keel.",
        "Stand by the sheets, {title}! The tell-tales are dancing - perfect apparent wind for a reach.",
        "Come about, {title}! Keep her full and by - pinching will only slow our passage.",
        "Douse the spinnaker, {title}! Even a kite needs the right angle of heel to fly true.",
        "Glass is rising, {title}! The old sailors say 'when smoke descends, good weather ends.'",
        "Check the barometer, {title}! 'Red sky at morning, sailors take warning' - but we sail regardless.",
        "Mind the wind shift, {title}! 'When the wind is in the East, 'tis neither good for man nor beast.'",
        "Watch the clouds, {title}! Mare's tails and mackerel skies - never let wise sailors be caught by surprise.",
        "Study the swells, {title}! The sea remembers storms from a thousand miles away.",
        "Check the rigging, {title}! A loose line aloft means trouble below - old bosun's wisdom.",
        "Oil the blocks, {title}! A squeaking block is a sailor's shame - keep the tackle shipshape.",
        "Serve the shrouds, {title}! Hemp and tar have saved more lives than all the king's horses.",
        "Whip the lines, {title}! A frayed end today means a parted line when the blow comes.",
        "Grease the winches, {title}! Mechanical advantage is the sailor's best friend in heavy weather.",
        "No whistling, {title}! The old salts say it calls up the wind - and we've plenty already.",
        "Touch the mast, {title}! Iron and oak have blessed more voyages than prayer alone.",
        "Throw a coin overboard, {title}! Poseidon appreciates tribute from those who know his ways.",
        "Salute the quarterdeck, {title}! Tradition runs deeper than the Mariana Trench.",
        "Mind the cat-o'-nine-tails, {title}! Even in peace, respect the ship's articles and customs.",
        "Heave the log, {title}! Dead reckoning may be old, but GPS can't teach you to read the sea.",
        "Shoot the sun, {title}! A sextant and chronometer - the navigator's true companions.",
        "Take a bearing, {title}! Three points off the starboard bow lies adventure and deep water.",
        "Sound the depths, {title}! The lead line tells truths that charts can only approximate.",
        "Plot the course, {title}! Great circle sailing - the shortest distance on a sphere.",
        "The sea calls, {title}! 'I must go down to the seas again' - Masefield knew the pull.",
        "Heed the ocean's song, {title}! She speaks in languages older than any port or harbor.",
        "Follow the trade winds, {title}! They've guided sailors since before maps marked the edges.",
        "Trust the tide, {title}! The moon's pull connects every drop from here to the Azores.",
        "Embrace the spray, {title}! Salt in the air is the perfume of freedom itself.",
        "Mind the Roaring Forties, {title}! Down south where the wind never sleeps nor forgives.",
        "Beware the Horse Latitudes, {title}! Where Spanish galleons dumped their cargo to catch any breeze.",
        "Navigate the Sargasso, {title}! Where seaweed tangles and legends of lost ships persist.",
        "Cross the Line, {title}! King Neptune demands tribute from every first-time equator crosser.",
        "Round the Horn, {title}! Where Cape pigeons dance and albatross wheel in the westerlies.",
        "Heed the kraken's call, {title}! Deep waters hold mysteries older than human memory.",
        "Watch for St. Elmo's fire, {title}! The masts themselves become torches in the storm.",
        "Listen for the mer-song, {title}! Not all voices on the wind belong to mortal throats.",
        "Seek the green flash, {title}! That moment when sun meets sea and magic is possible.",
        "Follow the ghost lights, {title}! Some navigational aids transcend mere physics.",
    ]

    def __init__(self, bot):
        super().__init__(bot)
        
        # Initialize state with default values
        self.set_state("triggers_responded", self.get_state("triggers_responded", 0))
        self.set_state("responses_given", self.get_state("responses_given", []))
        
        # Add a custom rate-limiting key for the target user's trigger
        self.set_state("last_response_time", self.get_state("last_response_time", 0.0))
        
        self.save_state()
        
        # Register the response pattern
        self.add_response_pattern(
            re.compile(r'\bSAIL\b'), 
            lambda msg, user: self._get_sailing_response(msg, user), 
            probability=1.0 # Always respond if conditions are met
        )
        
        # Register the admin command
        self.register_command(
            r"^\s*!sailing\s+stats\s*$", 
            self._cmd_stats, 
            admin_only=True,
            description="Show sailing module statistics."
        )

    def _get_sailing_response(self, msg: str, username: str) -> Optional[str]:
        """Handles the SAIL trigger and returns a response if conditions are met."""
        # Check if this is our target user and if they are not on cooldown
        if username.lower() != self.TARGET_USER.lower():
            return None

        # Check the custom global cooldown for this module
        now = time.time()
        if now - self.get_state("last_response_time", 0.0) < self.COOLDOWN:
            return None

        # Update state and get a response
        self.set_state("last_response_time", now)
        self.set_state("triggers_responded", self.get_state("triggers_responded") + 1)
        
        title = self.bot.title_for(username)
        recent_responses = self.get_state("responses_given", [])
        
        available_responses = [r for r in self.NAUTICAL_RESPONSES if r not in recent_responses]
        if not available_responses:
            available_responses = self.NAUTICAL_RESPONSES
        
        chosen_response = random.choice(available_responses)
        formatted_response = chosen_response.format(title=title)
        
        # Keep track of recent responses to avoid repeating
        recent_responses.append(chosen_response)
        self.set_state("responses_given", recent_responses[-10:])
        self.save_state()
        
        return f"{username}, {formatted_response}"

    @admin_required
    def _cmd_stats(self, connection, event, msg, username, match):
        """Handle the !sailing stats command."""
        stats = self.get_state()
        triggers = stats.get("triggers_responded", 0)
        recent_responses = len(stats.get("responses_given", []))
        
        self.safe_reply(connection, event, 
            f"Sailing stats: {triggers} SAIL triggers responded to, {recent_responses} recent responses tracked."
        )
        return True