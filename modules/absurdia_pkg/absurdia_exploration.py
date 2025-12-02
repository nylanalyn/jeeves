# modules/absurdia_pkg/absurdia_exploration.py
# Exploration logic and flavor text for Absurdia

import random
from typing import Dict, Any, Tuple, Optional, List

class ExplorationManager:
    """Handles exploration events and flavor text"""

    FLAVOR_TEXTS = [
        "You wander into a forest of upside-down trees. You find nothing but vertigo.",
        "You stare into the abyss. It blinks.",
        "You find a rock that looks suspiciously like your mother-in-law.",
        "You trip over a concept of time. It hurts.",
        "You discover a small door. Behind it is a brick wall.",
        "You hear a sound like a color. It's purple.",
        "You find a lost sock. It's not yours.",
        "You encounter a cloud shaped like a tax audit. You run.",
        "You find a sign that says 'Do Not Read This'. You read it.",
        "You walk for hours and end up exactly where you started.",
        "You find a puddle that reflects someone else's face.",
        "You see a bird flying backwards. It seems to know what it's doing.",
        "You find a box labeled 'Hope'. It's empty.",
        "You meet a man who speaks only in riddles. You ignore him.",
        "You find a tree that grows books. They are all blank.",
        "You step on a crack. Your mother calls to complain about her back.",
        "You find a coin glued to the ground.",
        "You see a fish walking on land. It looks embarrassed.",
        "You find a hat. It's too small.",
        "You discover a new shade of beige. It's boring.",
        "You hear the wind whispering your search history.",
        "You find a key that fits no lock.",
        "You see a shadow that moves independently.",
        "You find a bottle of 'Instant Regret'. You decide not to drink it.",
        "You walk through a mirror. Everything is backwards now.",
        "You find a calendar with 13 months.",
        "You see a cat barking at a dog.",
        "You find a sandwich. It's made of sand.",
        "You discover a hole in reality. You patch it with duct tape.",
        "You find a map to nowhere."
    ]

    def __init__(self):
        pass

    def get_exploration_flavor(self) -> str:
        """Get a random exploration flavor text"""
        return random.choice(self.FLAVOR_TEXTS)

    def roll_exploration_reward(self) -> Optional[str]:
        """
        Roll for exploration reward.
        Returns: 'basic', 'standard', 'premium', or None
        """
        roll = random.random()

        # 10.5% total chance for a trap
        if roll < 0.005: # 0.5%
            return 'premium'
        elif roll < 0.025: # 2.0%
            return 'standard'
        elif roll < 0.105: # 8.0%
            return 'basic'
        
        return None
