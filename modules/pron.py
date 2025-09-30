# modules/pron.py
# A module for the wholesome erotica joke.
import random
from .base import SimpleCommandModule

def setup(bot):
    return Pron(bot)

class Pron(SimpleCommandModule):
    name = "pron"
    version = "2.0.0" # Dynamic configuration refactor
    description = "Provides wholesome, helpful scenarios with a suggestive trigger."

    SCENARIOS = [
        "You come home to find a reasonably attractive person has done all of your dishes and put them away for you.",
        "You walk into your bedroom to find someone incredibly hot has made your bed, having washed and ironed your sheets.",
        "As you sit down to your computer, you notice a charming individual has perfectly organized your desktop icons and cleared out 3.2 GB of temp files.",
        "You open the fridge to find a delightful stranger has meal-prepped a week's worth of healthy, delicious lunches for you.",
        "A captivating person rings your doorbell, hands you a perfectly brewed coffee, and informs you that your Amazon package has been brought inside.",
        "You were going to do laundry, but it appears a stunning individual has already washed, dried, and folded everything, including that one sock you thought you'd lost forever.",
        "Your car is making a funny noise, but a dangerously good-looking mechanic is already underneath it, saying 'I can fix her.'",
        "You come home to find a gorgeous stranger has not only vacuumed but also shampooed your carpets.",
        "You're about to take out the trash, but a mysterious and alluring person has already taken the bins to the curb for you.",
        "You log into your favorite video game to find a fetching stranger has organized your inventory and completed all of your daily quests.",
        "A dangerously competent person is on your roof, cleaning your gutters and inspecting your shingles for wear.",
        "You were dreading putting together that IKEA furniture, but you walk in to find a handy and handsome individual has already assembled it perfectly.",
        "You open your closet to find a chic and stylish person has organized it by color and season.",
        "Your Wi-Fi goes out, but a tech-savvy and attractive neighbor is already at your door, having diagnosed the problem as a squirrel-related incident.",
        "You find an alluring stranger in your kitchen, sharpening all of your knives to a professional, razor-sharp edge.",
    ]

    def __init__(self, bot):
        # Cooldown is now handled by the command registration and dynamic config.
        super().__init__(bot)

    def _register_commands(self):
        self.register_command(r"^\s*!pron\s*$", self._cmd_pron,
                              name="pron", cooldown=30.0, # This is the default cooldown
                              description="Receive a wholesome scenario.")

    def _cmd_pron(self, connection, event, msg, username, match):
        scenario = random.choice(self.SCENARIOS)
        self.safe_reply(connection, event, f"{username}, {scenario}")
        return True
