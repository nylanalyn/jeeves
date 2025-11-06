# modules/pron.py
# A module for the wholesome erotica joke.
import random
import re
from typing import Any, List
from .base import SimpleCommandModule

def setup(bot: Any) -> 'Pron':
    return Pron(bot)

class Pron(SimpleCommandModule):
    name = "pron"
    version = "2.0.0" # Dynamic configuration refactor
    description = "Provides wholesome, helpful scenarios with a suggestive trigger."

    SCENARIOS: List[str] = [
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
        "A mysterious figure has alphabetized your spice rack and labeled everything with a label maker.",
        "You discover an enchanting individual has updated all your software, including those annoying drivers you've been ignoring.",
        "A strikingly capable person has already filed your taxes and found you a $600 refund you didn't know about.",
        "You return home to find a devastatingly efficient stranger has installed blackout curtains in your bedroom.",
        "An irresistible someone has defragmented your hard drive and cleared 47 GB of old log files.",
        "A charming soul has re-caulked your bathtub and fixed that leaky faucet that's been driving you mad.",
        "You find a ravishing individual in your yard, having already pulled all the weeds and mulched the garden beds.",
        "A suspiciously attractive person hands you a flash drive containing all your scattered passwords, properly encrypted.",
        "Someone impossibly thoughtful has replaced all your smoke detector batteries and tested each one.",
        "You walk in to find a dangerously skilled baker has made you fresh sourdough bread and left the starter with detailed care instructions.",
        "An alluring stranger has rotated your mattress and flipped all the couch cushions.",
        "A mysteriously helpful person has sorted through your junk drawer and actually found that one tiny screwdriver you needed.",
        "You discover someone uncommonly kind has paid your utility bills three months in advance.",
        "A beguiling individual has cleaned your phone's charging port and replaced the frayed cable.",
        "You find an absolutely stunning person has pressure-washed your driveway and sidewalk.",
        "Someone incredibly thoughtful has scheduled all your overdue doctor and dentist appointments for you.",
        "A mesmerizing stranger has restocked your cleaning supplies and organized them under the sink.",
        "You return to find an attractive soul has fixed that one drawer that never quite closed right.",
        "A captivating person has updated your resume, cover letter, and LinkedIn profile to perfection.",
        "Someone wickedly competent has cleared all your browser tabs into organized bookmark folders.",
        "You discover a fetching individual has pruned your houseplants and given them the perfect amount of water.",
        "An enchanting stranger has color-coded your entire cable management situation behind your desk.",
        "A gorgeous person has deep-cleaned your oven and it actually looks brand new.",
        "You find someone irresistibly handy has sealed all the drafty windows for winter.",
        "A dangerously thoughtful individual has organized your photos into albums by date and event.",
    ]

    def __init__(self, bot: Any) -> None:
        # Cooldown is now handled by the command registration and dynamic config.
        super().__init__(bot)

    def _register_commands(self) -> None:
        self.register_command(r"^\s*!pron\s*$", self._cmd_pron,
                              name="pron", cooldown=30.0, # This is the default cooldown
                              description="Receive a wholesome scenario.")

    def _cmd_pron(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        scenario = random.choice(self.SCENARIOS)
        self.safe_reply(connection, event, f"{username}, {scenario}")
        return True
