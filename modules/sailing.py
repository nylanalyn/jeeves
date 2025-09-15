# modules/sailing.py
# Nautical responses for witeshark2's SAIL triggers
import re
import random
import time

def setup(bot):
    return Sailing(bot)

class Sailing:
    name = "sailing"
    version = "1.0.0"
    
    # Target user
    TARGET_USER = "witeshark2"
    
    # Cooldown to prevent spam (in seconds)
    COOLDOWN = 5.0
    
    # Deep nautical responses with obscure maritime lore
    NAUTICAL_RESPONSES = [
        # Traditional sailing responses
        "Aye, {title}! The wind's fair and the tide's turning - time to splice the mainbrace!",
        "Steady as she goes, {title}! Mind the mizzen and watch for squalls off the starboard bow.",
        "Heave away, {title}! The bosun's pipe calls and the capstan awaits your shanty.",
        "By the beard of Neptune, {title}! The sea's singing her siren song once more.",
        "Fair winds and following seas, {title}! May your sheets stay taut and your compass true.",
        
        # Deep maritime lore
        "Hoist the burgee, {title}! The ancient mariners say a red sky at night means sailor's delight.",
        "Batten down the hatches, {title}! Remember: one hand for the ship, one for yourself.",
        "The albatross circles, {title} - but we'll not be shooting any today, if Coleridge is to be believed.",
        "Mind the doldrums, {title}! Even the Trade Winds must pause to gather their strength.",
        "Sheet home the topsails, {title}! The old salts say the sea never forgives the unprepared.",
        
        # Obscure nautical terminology
        "Avast, {title}! Time to bend on the storm jib and reef the mainsail - weather's turning.",
        "Belay that order, {title}! The tide's on the make and the glass is falling fast.",
        "Stand by to wear ship, {title}! We'll box the compass before this day is through.",
        "Ready about, {title}! Mind your head when the boom comes across - no landsman's mistake here.",
        "Heave the lead, {title}! Mark twain and by the deep six - safe water beneath our keel.",
        
        # Historical sailing references
        "Splice the yards, {title}! Even Drake himself would approve of such sailing weather.",
        "Hoist the jack, {title}! The ghost of old Blackbeard would be proud to see such seamanship.",
        "Trim the sheets, {title}! Cook's Endeavour never saw finer sailing conditions than these.",
        "Bear away, {title}! Magellan himself would have blessed winds like these for the straits.",
        "Set the stunsails, {title}! Even the Flying Dutchman would envy such a fair breeze.",
        
        # Technical sailing knowledge
        "Hard alee, {title}! Remember - when in doubt, let it out - never cleat a sheet in a blow.",
        "Ease the halyard, {title}! A yacht's not a ship until she's felt blue water beneath her keel.",
        "Stand by the sheets, {title}! The tell-tales are dancing - perfect apparent wind for a reach.",
        "Come about, {title}! Keep her full and by - pinching will only slow our passage.",
        "Douse the spinnaker, {title}! Even a kite needs the right angle of heel to fly true.",
        
        # Weather and navigation lore
        "Glass is rising, {title}! The old sailors say 'when smoke descends, good weather ends.'",
        "Check the barometer, {title}! 'Red sky at morning, sailors take warning' - but we sail regardless.",
        "Mind the wind shift, {title}! 'When the wind is in the East, 'tis neither good for man nor beast.'",
        "Watch the clouds, {title}! Mare's tails and mackerel skies - never let wise sailors be caught by surprise.",
        "Study the swells, {title}! The sea remembers storms from a thousand miles away.",
        
        # Rigging and boat maintenance
        "Check the rigging, {title}! A loose line aloft means trouble below - old bosun's wisdom.",
        "Oil the blocks, {title}! A squeaking block is a sailor's shame - keep the tackle shipshape.",
        "Serve the shrouds, {title}! Hemp and tar have saved more lives than all the king's horses.",
        "Whip the lines, {title}! A frayed end today means a parted line when the blow comes.",
        "Grease the winches, {title}! Mechanical advantage is the sailor's best friend in heavy weather.",
        
        # Superstitions and traditions
        "No whistling, {title}! The old salts say it calls up the wind - and we've plenty already.",
        "Touch the mast, {title}! Iron and oak have blessed more voyages than prayer alone.",
        "Throw a coin overboard, {title}! Poseidon appreciates tribute from those who know his ways.",
        "Salute the quarterdeck, {title}! Tradition runs deeper than the Mariana Trench.",
        "Mind the cat-o'-nine-tails, {title}! Even in peace, respect the ship's articles and customs.",
        
        # Advanced seamanship
        "Heave the log, {title}! Dead reckoning may be old, but GPS can't teach you to read the sea.",
        "Shoot the sun, {title}! A sextant and chronometer - the navigator's true companions.",
        "Take a bearing, {title}! Three points off the starboard bow lies adventure and deep water.",
        "Sound the depths, {title}! The lead line tells truths that charts can only approximate.",
        "Plot the course, {title}! Great circle sailing - the shortest distance on a sphere.",
        
        # Poetic and philosophical
        "The sea calls, {title}! 'I must go down to the seas again' - Masefield knew the pull.",
        "Heed the ocean's song, {title}! She speaks in languages older than any port or harbor.",
        "Follow the trade winds, {title}! They've guided sailors since before maps marked the edges.",
        "Trust the tide, {title}! The moon's pull connects every drop from here to the Azores.",
        "Embrace the spray, {title}! Salt in the air is the perfume of freedom itself.",
        
        # Regional sailing knowledge
        "Mind the Roaring Forties, {title}! Down south where the wind never sleeps nor forgives.",
        "Beware the Horse Latitudes, {title}! Where Spanish galleons dumped their cargo to catch any breeze.",
        "Navigate the Sargasso, {title}! Where seaweed tangles and legends of lost ships persist.",
        "Cross the Line, {title}! King Neptune demands tribute from every first-time equator crosser.",
        "Round the Horn, {title}! Where Cape pigeons dance and albatross wheel in the westerlies.",
        
        # Mystical and legendary
        "Heed the kraken's call, {title}! Deep waters hold mysteries older than human memory.",
        "Watch for St. Elmo's fire, {title}! The masts themselves become torches in the storm.",
        "Listen for the mer-song, {title}! Not all voices on the wind belong to mortal throats.",
        "Seek the green flash, {title}! That moment when sun meets sea and magic is possible.",
        "Follow the ghost lights, {title}! Some navigational aids transcend mere physics.",
    ]

    def __init__(self, bot):
        self.bot = bot
        self.st = bot.get_module_state(self.name)
        
        # Initialize state
        self.st.setdefault("triggers_responded", 0)
        self.st.setdefault("last_response_time", 0.0)
        self.st.setdefault("responses_given", [])
        
        # Pattern to match SAIL in all caps
        self.sail_pattern = re.compile(r'\bSAIL\b')
        
        bot.save()

    def on_load(self):
        pass

    def on_unload(self):
        pass

    def _can_respond(self) -> bool:
        """Check if enough time has passed since last response."""
        now = time.time()
        last_response = self.st.get("last_response_time", 0.0)
        return now - last_response >= self.COOLDOWN

    def _mark_response(self, response_text: str):
        """Record that we've responded."""
        now = time.time()
        self.st["last_response_time"] = now
        self.st["triggers_responded"] = self.st.get("triggers_responded", 0) + 1
        
        # Track recent responses to avoid immediate repeats
        responses = self.st.get("responses_given", [])
        responses.append(response_text)
        
        # Keep only last 10 responses for repeat checking
        if len(responses) > 10:
            responses = responses[-10:]
        
        self.st["responses_given"] = responses
        self.bot.save()

    def _get_nautical_response(self, username: str) -> str:
        """Get a nautical response, avoiding recent repeats."""
        title = self.bot.title_for(username)
        recent_responses = self.st.get("responses_given", [])
        
        # Try to avoid responses we've used recently
        available_responses = [r for r in self.NAUTICAL_RESPONSES if r not in recent_responses]
        
        # If we've exhausted non-repeated responses, use any response
        if not available_responses:
            available_responses = self.NAUTICAL_RESPONSES
        
        chosen_response = random.choice(available_responses)
        return chosen_response.format(title=title)

    def on_pubmsg(self, connection, event, msg, username):
        room = event.target
        
        # Admin stats command
        if self.bot.is_admin(username) and msg.strip().lower() == "!sailing stats":
            stats = self.st
            triggers = stats.get("triggers_responded", 0)
            recent_responses = len(stats.get("responses_given", []))
            
            connection.privmsg(room, f"Sailing stats: {triggers} SAIL triggers responded to, {recent_responses} recent responses tracked")
            return True

        # Check if this is our target user
        if username.lower() != self.TARGET_USER.lower():
            return False

        # Check for SAIL in all caps
        if not self.sail_pattern.search(msg):
            return False

        # Check cooldown
        if not self._can_respond():
            return False

        # Generate and send response
        response = self._get_nautical_response(username)
        self._mark_response(response)
        
        connection.privmsg(room, f"{username}, {response}")
        return True
