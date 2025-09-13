# modules/replies.py
# Randomized coin-flip style replies when addressed with a question.
# Now with YES, NO, and MAYBE baskets.

import re
import random

YES_LINES = [
    "Indeed, {title}.",
    "At once, {title}.",
    "Very good, {title}.",
    "As you wish, {title}.",
    "Quite so, {title}.",
    "Naturally, {title}.",
    "I shall see to it, {title}.",
]

NO_LINES = [
    "I fear not, {title}.",
    "Alas, no, {title}.",
    "Regrettably not, {title}.",
    "That would be unwise, {title}.",
    "I must decline, {title}.",
    "Unfortunately, no, {title}.",
    "On this occasion, I cannot, {title}.",
]

MAYBE_LINES = [
    "Perhaps, {title}.",
    "It is possible, {title}.",
    "Time will tell, {title}.",
    "Hard to say, {title}.",
    "One cannot be certain, {title}.",
    "Possibly, {title}, though I wouldn’t wager the silver on it.",
    "I should not like to speculate, {title}.",
]

def setup(bot):
    return Replies(bot)

class Replies:
    name = "replies"

    def __init__(self, bot):
        self.bot = bot
        name_pat = getattr(bot, "JEEVES_NAME_RE", r"(?:jeeves|jeevesbot)")
        # Match: "Jeeves ... ?"
        self.RE_QUESTION = re.compile(rf"\b{name_pat}\b.*\?\s*$", re.IGNORECASE)

    def on_load(self): pass
    def on_unload(self): pass

    def _choose_reply(self, username: str) -> str:
        basket = random.choice([YES_LINES, NO_LINES, MAYBE_LINES])
        return random.choice(basket).format(title=self.bot.title_for(username))

    def on_pubmsg(self, connection, event, msg, username):
        if self.RE_QUESTION.search(msg):
            line = self._choose_reply(username)
            connection.privmsg(event.target, f"{username}, {line}")
            return True
        return False

