# modules/replies.py
# Enhanced question-answering - Already correctly targets rooms
import re
import random

def setup(bot):
    return Replies(bot)

class Replies:
    name = "replies"
    version = "2.0.0"
    
    # Response categories with different weightings for variety
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

    # Special responses for specific question types
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
        self.bot = bot
        self.st = bot.get_module_state(self.name)
        
        # Initialize state
        self.st.setdefault("questions_answered", 0)
        self.st.setdefault("response_type_counts", {
            "yes": 0, "no": 0, "maybe": 0, "advice": 0, "philosophical": 0
        })
        self.st.setdefault("users_helped", [])
        self.st.setdefault("question_types", {
            "basic": 0, "advice": 0, "philosophical": 0
        })
        
        # Set up patterns
        name_pat = getattr(self.bot, "JEEVES_NAME_RE", r"(?:jeeves|jeevesbot)")
        
        # Basic question pattern
        self.basic_question = re.compile(rf"\b{name_pat}\b.*\?\s*$", re.IGNORECASE)
        
        # Advice-seeking patterns
        self.advice_patterns = [
            re.compile(rf"\b{name_pat}[,\s]+(what\s+should\s+i|should\s+i|can\s+you\s+help)", re.IGNORECASE),
            re.compile(rf"\b{name_pat}[,\s]+(advice|suggest|recommend)", re.IGNORECASE),
            re.compile(rf"\b{name_pat}[,\s]+(how\s+do\s+i|how\s+can\s+i)", re.IGNORECASE)
        ]
        
        # Philosophical patterns
        self.philosophy_patterns = [
            re.compile(rf"\b{name_pat}[,\s]+(what\s+is\s+the\s+meaning|why\s+do\s+we|what\s+is\s+life)", re.IGNORECASE),
            re.compile(rf"\b{name_pat}[,\s]+(do\s+you\s+think\s+about|philosophy|existence)", re.IGNORECASE),
            re.compile(rf"\b{name_pat}[,\s]+(what\s+is\s+truth|what\s+is\s+reality)", re.IGNORECASE)
        ]
        
        bot.save()

    def on_load(self):
        pass

    def on_unload(self):
        pass

    def _update_reply_stats(self, username: str, response_type: str, question_type: str = "basic"):
        """Update statistics for reply tracking."""
        self.st["questions_answered"] = self.st.get("questions_answered", 0) + 1
        
        # Update response type counts
        type_counts = self.st.get("response_type_counts", {})
        type_counts[response_type] = type_counts.get(response_type, 0) + 1
        self.st["response_type_counts"] = type_counts
        
        # Update question type counts
        question_counts = self.st.get("question_types", {})
        question_counts[question_type] = question_counts.get(question_type, 0) + 1
        self.st["question_types"] = question_counts
        
        # Track users helped
        users_helped = self.st.get("users_helped", [])
        username_lower = username.lower()
        if username_lower not in users_helped:
            users_helped.append(username_lower)
            self.st["users_helped"] = users_helped
        
        self.bot.save()

    def _choose_weighted_response_category(self) -> str:
        """Choose response category with weighted randomness."""
        # Weights: yes=30%, no=30%, maybe=40% for balanced responses
        categories = ["yes"] * 30 + ["no"] * 30 + ["maybe"] * 40
        return random.choice(categories)

    def _format_response(self, template: str, username: str) -> str:
        """Format response template with user-specific information."""
        title = self.bot.title_for(username)
        return template.format(title=title)

    def _handle_basic_question(self, msg: str, username: str) -> str:
        """Handle basic yes/no/maybe questions."""
        category = self._choose_weighted_response_category()
        
        if category == "yes":
            template = random.choice(self.YES_LINES)
        elif category == "no":
            template = random.choice(self.NO_LINES)
        else:  # maybe
            template = random.choice(self.MAYBE_LINES)
        
        self._update_reply_stats(username, category, "basic")
        return f"{username}, {self._format_response(template, username)}"

    def _handle_advice_question(self, msg: str, username: str) -> str:
        """Handle advice-seeking questions."""
        # 70% chance for advice, 30% for regular response
        if random.random() < 0.7:
            template = random.choice(self.ADVICE_LINES)
            response_type = "advice"
        else:
            category = self._choose_weighted_response_category()
            if category == "yes":
                template = random.choice(self.YES_LINES)
            elif category == "no":
                template = random.choice(self.NO_LINES)
            else:
                template = random.choice(self.MAYBE_LINES)
            response_type = category
        
        self._update_reply_stats(username, response_type, "advice")
        return f"{username}, {self._format_response(template, username)}"

    def _handle_philosophical_question(self, msg: str, username: str) -> str:
        """Handle philosophical or existential questions."""
        # 60% chance for philosophical response, 40% for maybe
        if random.random() < 0.6:
            template = random.choice(self.PHILOSOPHICAL_LINES)
            response_type = "philosophical"
        else:
            template = random.choice(self.MAYBE_LINES)
            response_type = "maybe"
        
        self._update_reply_stats(username, response_type, "philosophical")
        return f"{username}, {self._format_response(template, username)}"

    def on_pubmsg(self, connection, event, msg, username):
        room = event.target
        
        # Admin stats command
        if self.bot.is_admin(username) and msg.strip().lower() == "!replies stats":
            stats = self.st
            
            lines = [
                f"Questions answered: {stats.get('questions_answered', 0)}",
                f"Unique users helped: {len(stats.get('users_helped', []))}"
            ]
            
            # Add response type breakdown
            response_types = stats.get("response_type_counts", {})
            if response_types:
                response_str = ", ".join(f"{k}:{v}" for k, v in response_types.items())
                lines.append(f"Response types: {response_str}")
            
            # Add question type breakdown
            question_types = stats.get("question_types", {})
            if question_types:
                question_str = ", ".join(f"{k}:{v}" for k, v in question_types.items())
                lines.append(f"Question types: {question_str}")
            
            connection.privmsg(room, f"Replies stats: {'; '.join(lines)}")
            return True

        # Check for philosophical questions first (most specific)
        for pattern in self.philosophy_patterns:
            if pattern.search(msg):
                reply = self._handle_philosophical_question(msg, username)
                connection.privmsg(room, reply)
                return True

        # Check for advice questions
        for pattern in self.advice_patterns:
            if pattern.search(msg):
                reply = self._handle_advice_question(msg, username)
                connection.privmsg(room, reply)
                return True

        # Check for basic questions
        if self.basic_question.search(msg):
            reply = self._handle_basic_question(msg, username)
            connection.privmsg(room, reply)
            return True

        return False