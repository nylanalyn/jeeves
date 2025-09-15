# modules/replies.py
# Enhanced question-answering using the ResponseModule framework
import re
import random
import functools
import time 
from typing import Dict, Any, Optional
from .base import ResponseModule, SimpleCommandModule, admin_required

def setup(bot):
    return Replies(bot)

class Replies(SimpleCommandModule):
    name = "replies"
    version = "2.1.0"
    description = "Answers general, advice, and philosophical questions."

    YES_LINES = [
        "Indeed, {title}.",
        "At once, {title}.",
        "Very good, {title}.",
        "As you wish, {title}.",
        "Quite so, {title}.",
        "Naturally, {title}.",
        "I shall see to it, {title}.",
        "Absolutely, {title}.",
        "Without question, {title}.",
        "Most certainly, {title}.",
        "I believe so, {title}.",
        "Undoubtedly, {title}."
    ]

    NO_LINES = [
        "I fear not, {title}.",
        "Alas, no, {title}.",
        "Regrettably not, {title}.",
        "That would be unwise, {title}.",
        "I must decline, {title}.",
        "Unfortunately, no, {title}.",
        "On this occasion, I cannot, {title}.",
        "I think not, {title}.",
        "Most unlikely, {title}.",
        "I should advise against it, {title}.",
        "Not in my professional opinion, {title}.",
        "I rather doubt it, {title}."
    ]

    MAYBE_LINES = [
        "Perhaps, {title}.",
        "It is possible, {title}.",
        "Time will tell, {title}.",
        "Hard to say, {title}.",
        "One cannot be certain, {title}.",
        "Possibly, {title}, though I wouldn't wager the silver on it.",
        "I should not like to speculate, {title}.",
        "The signs are unclear, {title}.",
        "It remains to be seen, {title}.",
        "That depends on several factors, {title}.",
        "I find myself undecided, {title}.",
        "The matter requires consideration, {title}."
    ]

    ADVICE_LINES = [
        "I would recommend considering all options carefully, {title}.",
        "Prudence suggests a measured approach, {title}.",
        "In my experience, the simplest solution often proves best, {title}.",
        "Perhaps a spot of tea would clarify matters, {title}.",
        "I find that sleeping on important decisions rarely disappoints, {title}."
    ]

    PHILOSOPHICAL_LINES = [
        "An intriguing question that has occupied minds greater than mine, {title}.",
        "Philosophy falls somewhat outside my usual duties, {title}.",
        "I defer to wiser heads on such matters, {title}.",
        "That ventures into territory beyond domestic management, {title}.",
        "Such questions are best pondered over a proper meal, {title}."
    ]

    def __init__(self, bot):
        super().__init__(bot)
        
        self.set_state("questions_answered", self.get_state("questions_answered", 0))
        self.set_state("response_type_counts", self.get_state("response_type_counts", {
            "yes": 0, "no": 0, "maybe": 0, "advice": 0, "philosophical": 0
        }))
        self.set_state("users_helped", self.get_state("users_helped", []))
        self.set_state("question_types", self.get_state("question_types", {
            "basic": 0, "advice": 0, "philosophical": 0
        }))
        self.save_state()

    def _register_commands(self):
        self.register_command(r"^\s*!replies\s+stats\s*$", self._cmd_stats,
                              admin_only=True, description="Show statistics on questions answered.")

    def on_pubmsg(self, connection, event, msg, username):
        if super().on_pubmsg(connection, event, msg, username):
            return True
        
        # This module uses the base class's _handle_message for all other responses
        if self._handle_message(connection, event, msg, username):
            return True
            
        return False

    def _handle_message(self, connection, event, msg: str, username: str) -> bool:
        name_pat = getattr(self.bot, "JEEVES_NAME_RE", r"(?:jeeves|jeevesbot)")
        
        # Check for philosophical questions first (most specific)
        philosophy_patterns = [
            re.compile(rf"\b{name_pat}[,!\s]*\s*(what\s+is\s+the\s+meaning|why\s+do\s+we|what\s+is\s+life)", re.IGNORECASE),
            re.compile(rf"\b{name_pat}[,!\s]*\s*(do\s+you\s+think\s+about|philosophy|existence)", re.IGNORECASE),
            re.compile(rf"\b{name_pat}[,!\s]*\s*(what\s+is\s+truth|what\s+is\s+reality)", re.IGNORECASE)
        ]
        if any(p.search(msg) for p in philosophy_patterns):
            self.safe_reply(connection, event, self._handle_philosophical_question(msg, username))
            return True

        # Check for advice questions
        advice_patterns = [
            re.compile(rf"\b{name_pat}[,!\s]*\s*(what\s+should\s+i|should\s+i|can\s+you\s+help)", re.IGNORECASE),
            re.compile(rf"\b{name_pat}[,!\s]*\s*(advice|suggest|recommend)", re.IGNORECASE),
            re.compile(rf"\b{name_pat}[,!\s]*\s*(how\s+do\s+i|how\s+can\s+i)", re.IGNORECASE)
        ]
        if any(p.search(msg) for p in advice_patterns):
            self.safe_reply(connection, event, self._handle_advice_question(msg, username))
            return True

        # Check for basic questions
        basic_question = re.compile(rf"\b{name_pat}\b.*\?\s*$", re.IGNORECASE)
        if basic_question.search(msg):
            self.safe_reply(connection, event, self._handle_basic_question(msg, username))
            return True

        return False

    def _update_reply_stats(self, username: str, response_type: str, question_type: str = "basic"):
        self.set_state("questions_answered", self.get_state("questions_answered") + 1)
        type_counts = self.get_state("response_type_counts")
        type_counts[response_type] = type_counts.get(response_type, 0) + 1
        self.set_state("response_type_counts", type_counts)
        question_counts = self.get_state("question_types")
        question_counts[question_type] = question_counts.get(question_type, 0) + 1
        self.set_state("question_types", question_counts)
        users_helped = self.get_state("users_helped")
        username_lower = username.lower()
        if username_lower not in users_helped:
            users_helped.append(username_lower)
            self.set_state("users_helped", users_helped)
        self.save_state()

    def _choose_weighted_response_category(self) -> str:
        categories = ["yes"] * 30 + ["no"] * 30 + ["maybe"] * 40
        return random.choice(categories)

    def _format_response(self, template: str, username: str) -> str:
        title = self.bot.title_for(username)
        return template.format(title=title)

    def _handle_basic_question(self, msg: str, username: str) -> str:
        category = self._choose_weighted_response_category()
        if category == "yes": template = random.choice(self.YES_LINES)
        elif category == "no": template = random.choice(self.NO_LINES)
        else: template = random.choice(self.MAYBE_LINES)
        self._update_reply_stats(username, category, "basic")
        return f"{username}, {self._format_response(template, username)}"

    def _handle_advice_question(self, msg: str, username: str) -> str:
        if random.random() < 0.7:
            template = random.choice(self.ADVICE_LINES)
            response_type = "advice"
        else:
            category = self._choose_weighted_response_category()
            if category == "yes": template = random.choice(self.YES_LINES)
            elif category == "no": template = random.choice(self.NO_LINES)
            else: template = random.choice(self.MAYBE_LINES)
            response_type = category
        self._update_reply_stats(username, response_type, "advice")
        return f"{username}, {self._format_response(template, username)}"

    def _handle_philosophical_question(self, msg: str, username: str) -> str:
        if random.random() < 0.6:
            template = random.choice(self.PHILOSOPHICAL_LINES)
            response_type = "philosophical"
        else:
            template = random.choice(self.MAYBE_LINES)
            response_type = "maybe"
        self._update_reply_stats(username, response_type, "philosophical")
        return f"{username}, {self._format_response(template, username)}"

    @admin_required
    def _cmd_stats(self, connection, event, msg, username, match):
        stats = self.get_state()
        lines = [
            f"Questions answered: {stats.get('questions_answered', 0)}",
            f"Unique users helped: {len(stats.get('users_helped', []))}"
        ]
        response_types = stats.get("response_type_counts", {})
        if response_types:
            response_str = ", ".join(f"{k}:{v}" for k, v in response_types.items())
            lines.append(f"Response types: {response_str}")
        question_types = stats.get("question_types", {})
        if question_types:
            question_str = ", ".join(f"{k}:{v}" for k, v in question_types.items())
            lines.append(f"Question types: {question_str}")
        self.safe_reply(connection, event, f"Replies stats: {'; '.join(lines)}")
        return True