# modules/replies.py
# Enhanced question-answering
import re
import random
import functools
import time
from typing import Dict, Any, Optional, List, Pattern
from .base import SimpleCommandModule, admin_required

def setup(bot: Any) -> 'Replies':
    return Replies(bot)

class Replies(SimpleCommandModule):
    name = "replies"
    version = "3.0.0" # Dynamic configuration refactor
    description = "Answers general, advice, and philosophical questions."

    YES_LINES: List[str] = [ "Indeed, {title}.", "At once, {title}.", "Very good, {title}.", "As you wish, {title}.", "Quite so, {title}.", "Naturally, {title}.", "I shall see to it, {title}.", "Absolutely, {title}.", "Without question, {title}.", "Most certainly, {title}.", "I believe so, {title}.", "Undoubtedly, {title}." ]
    NO_LINES: List[str] = [ "I fear not, {title}.", "Alas, no, {title}.", "Regrettably not, {title}.", "That would be unwise, {title}.", "I must decline, {title}.", "Unfortunately, no, {title}.", "On this occasion, I cannot, {title}.", "I think not, {title}.", "Most unlikely, {title}.", "I should advise against it, {title}.", "Not in my professional opinion, {title}.", "I rather doubt it, {title}." ]
    MAYBE_LINES: List[str] = [ "Perhaps, {title}.", "It is possible, {title}.", "Time will tell, {title}.", "Hard to say, {title}.", "One cannot be certain, {title}.", "Possibly, {title}, though I wouldn't wager the silver on it.", "I should not like to speculate, {title}.", "The signs are unclear, {title}.", "It remains to be seen, {title}.", "That depends on several factors, {title}.", "I find myself undecided, {title}.", "The matter requires consideration, {title}." ]
    ADVICE_LINES: List[str] = [ "I would recommend considering all options carefully, {title}.", "Prudence suggests a measured approach, {title}.", "In my experience, the simplest solution often proves best, {title}.", "Perhaps a spot of tea would clarify matters, {title}.", "I find that sleeping on important decisions rarely disappoints, {title}." ]
    PHILOSOPHICAL_LINES: List[str] = [ "An intriguing question that has occupied minds greater than mine, {title}.", "Philosophy falls somewhat outside my usual duties, {title}.", "I defer to wiser heads on such matters, {title}.", "That ventures into territory beyond domestic management, {title}.", "Such questions are best pondered over a proper meal, {title}." ]
    HIDE_LINES: List[str] = [ "I am a professional butler. Such an act would be undignified.", "*gives {username} a withering look*", "I think not, {title}.", "I shall do no such thing. Dignity must be maintained.", "Perhaps the other bots enjoy such frivolity. I do not.", "*adjusts cufflinks* A butler does not 'hide', {username}.", "How utterly beneath me.", "I would sooner serve room-temperature tea.", "Let us not pretend we are children, {username}. We are more dignified than that." ]

    def __init__(self, bot: Any) -> None:
        super().__init__(bot)

        name_pat = getattr(self.bot, "JEEVES_NAME_RE", r"(?:jeeves|jeevesbot)")
        self.RE_PHILOSOPHY: Pattern[str] = re.compile(rf"\b{name_pat}[,!\s]*\s*(what\s+is\s+the\s+meaning|why\s+do\s+we|what\s+is\s+life|philosophy|existence|truth|reality)", re.IGNORECASE)
        self.RE_ADVICE: Pattern[str] = re.compile(rf"\b{name_pat}[,!\s]*\s*(what\s+should\s+i|should\s+i|can\s+you\s+help|advice|suggest|recommend|how\s+do\s+i|how\s+can\s+i)", re.IGNORECASE)
        self.RE_BASIC: Pattern[str] = re.compile(rf"\b{name_pat}\b.*\?\s*$", re.IGNORECASE)
        self.RE_HIDE: Pattern[str] = re.compile(rf"\b{name_pat}[,!\s]*\s*(hide|cloak|sneak|vanish|disappear|go\s+invisible)", re.IGNORECASE)

    def _register_commands(self) -> None:
        # No !commands in this module
        pass

    def on_ambient_message(self, connection, event, msg: str, username: str) -> bool:
        if not self.is_enabled(event.target):
            return False

        if self.RE_HIDE.search(msg):
            self._handle_hide_request(connection, event, username)
            return True
        if self.RE_PHILOSOPHY.search(msg):
            self._handle_philosophical_question(connection, event, username)
            return True
        if self.RE_ADVICE.search(msg):
            self._handle_advice_question(connection, event, username)
            return True
        if self.RE_BASIC.search(msg):
            self._handle_basic_question(connection, event, username)
            return True
        return False

    def _format_response(self, template: str, username: str) -> str:
        title = self.bot.title_for(username)
        return template.format(title=title)

    def _handle_basic_question(self, connection: Any, event: Any, username: str) -> None:
        category = random.choices(["yes", "no", "maybe"], weights=[30, 30, 40], k=1)[0]
        if category == "yes": template = random.choice(self.YES_LINES)
        elif category == "no": template = random.choice(self.NO_LINES)
        else: template = random.choice(self.MAYBE_LINES)
        response = self._format_response(template, username)
        self.safe_reply(connection, event, f"{username}, {response}")

    def _handle_advice_question(self, connection: Any, event: Any, username: str) -> None:
        if random.random() < 0.7:
            template = random.choice(self.ADVICE_LINES)
        else:
            self._handle_basic_question(connection, event, username)
            return
        response = self._format_response(template, username)
        self.safe_reply(connection, event, f"{username}, {response}")

    def _handle_philosophical_question(self, connection: Any, event: Any, username: str) -> None:
        if random.random() < 0.6:
            template = random.choice(self.PHILOSOPHICAL_LINES)
        else:
            template = random.choice(self.MAYBE_LINES)
        response = self._format_response(template, username)
        self.safe_reply(connection, event, f"{username}, {response}")

    def _handle_hide_request(self, connection: Any, event: Any, username: str) -> None:
        template = random.choice(self.HIDE_LINES)
        title = self.bot.title_for(username)
        response = template.format(title=title, username=username)
        self.safe_reply(connection, event, response)
