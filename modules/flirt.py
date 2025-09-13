# modules/flirt.py
# Enhanced polite flirt handling without base class dependency
import re
import time
import random

def setup(bot):
    return Flirt(bot)

class Flirt:
    name = "flirt"
    version = "2.0.0"
    
    # Configuration
    GLOBAL_COOLDOWN = 30.0  # seconds between any flirt responses
    PER_USER_COOLDOWN = 60.0  # seconds before same user can trigger again

    def __init__(self, bot):
        self.bot = bot
        self.st = bot.get_module_state(self.name)
        
        # Initialize state
        self.st.setdefault("total_flirts_received", 0)
        self.st.setdefault("responses_given", 0)
        self.st.setdefault("intent_counts", {})
        self.st.setdefault("unique_flirters", [])
        self.st.setdefault("last_global_response", 0.0)
        self.st.setdefault("user_last_response", {})
        
        self._setup_flirt_patterns()
        bot.save()

    def on_load(self):
        pass

    def on_unload(self):
        pass

    def _setup_flirt_patterns(self):
        """Set up flirt detection patterns."""
        name_pat = getattr(self.bot, "JEEVES_NAME_RE", r"(?:jeeves|jeevesbot)")
        
        self.patterns = {
            "marry": re.compile(rf"\b(?:{name_pat}[,!\s]*)?(marry\s+me|marry\s+us)\b", re.IGNORECASE),
            "date": re.compile(rf"\b(?:{name_pat}[,!\s]*)?(date\s+me|go\s+out\s+with\s+me)\b", re.IGNORECASE),
            "like_me": re.compile(rf"\b(?:{name_pat}[,!\s]*)?(do\s+you\s+like\s+me|do\s+you\s+fancy\s+me)\b", re.IGNORECASE),
            "love_you": re.compile(rf"\b(i\s+love\s+you[,!\s]*{name_pat}|love\s+you[,!\s]*{name_pat})\b", re.IGNORECASE),
            "kiss": re.compile(rf"\b(?:{name_pat}[,!\s]*)?(kiss\s+me|mwah|muah|blow\s+a\s+kiss)\b", re.IGNORECASE),
            "compliment_me": re.compile(rf"\b(?:{name_pat}[,!\s]*)?(am\s+i\s+(cute|handsome|pretty|attractive)|do\s+you\s+think\s+i'?m\s+(cute|handsome|pretty|attractive))\b", re.IGNORECASE),
            "be_mine": re.compile(rf"\b(?:{name_pat}[,!\s]*)?(be\s+my\s+(boyfriend|girlfriend|partner)|you'?re\s+mine[,!]?\s*{name_pat})\b", re.IGNORECASE),
            "i_want_you": re.compile(rf"\b(?:{name_pat}[,!\s]*)?i\s+want\s+you\b", re.IGNORECASE),
            "flirt_generic": re.compile(rf"\b(?:{name_pat}[,!\s]*)?(flirt\s+with\s+me|you'?re\s+(hot|sexy|cute))\b", re.IGNORECASE),
        }

    def _can_respond_globally(self) -> bool:
        """Check if enough time has passed since last global response."""
        last_response = self.st.get("last_global_response", 0.0)
        return time.time() - last_response >= self.GLOBAL_COOLDOWN

    def _can_respond_to_user(self, username: str) -> bool:
        """Check if enough time has passed since last response to this user."""
        user_responses = self.st.get("user_last_response", {})
        last_response = user_responses.get(username.lower(), 0.0)
        return time.time() - last_response >= self.PER_USER_COOLDOWN

    def _mark_response(self, username: str, intent: str):
        """Mark that we've responded to a user with a specific intent."""
        now = time.time()
        
        # Update global response time
        self.st["last_global_response"] = now
        
        # Update per-user response time
        user_responses = self.st.get("user_last_response", {})
        user_responses[username.lower()] = now
        self.st["user_last_response"] = user_responses
        
        # Update statistics
        self.st["total_flirts_received"] = self.st.get("total_flirts_received", 0) + 1
        self.st["responses_given"] = self.st.get("responses_given", 0) + 1
        
        # Track intent counts
        intent_counts = self.st.get("intent_counts", {})
        intent_counts[intent] = intent_counts.get(intent, 0) + 1
        self.st["intent_counts"] = intent_counts
        
        # Track unique flirters
        unique_flirters = self.st.get("unique_flirters", [])
        username_lower = username.lower()
        if username_lower not in unique_flirters:
            unique_flirters.append(username_lower)
            self.st["unique_flirters"] = unique_flirters
        
        self.bot.save()

    def _get_reply_templates(self):
        """Get flirt response templates organized by intent."""
        return {
            "marry": [
                "An honour to be asked, but alas I am already married to my duties, {title}.",
                "I fear matrimony would interfere with my housekeeping, {title}.",
                "My schedule leaves little room for vows beyond those to service, {title}.",
                "While flattered, I must remain wedded to excellence in all things domestic, {title}."
            ],
            "date": [
                "My calendar is devoted to your convenience, not my own, {title}, I'm afraid.",
                "I must decline, {title}, but shall cheerfully arrange a splendid evening for you nonetheless.",
                "Alas, I am all appointments and brass polish, not courtship, {title}.",
                "My social schedule consists entirely of serving schedules, {title}."
            ],
            "like_me": [
                "Immensely—in the professional sense, {title}.",
                "With the fondness appropriate to a devoted servant, {title}.",
                "I esteem you highly, {title}—strictly within the remit of service.",
                "My admiration is both profound and thoroughly appropriate, {title}."
            ],
            "love_you": [
                "With due propriety, {title}, I reserve my affections for excellence and punctuality.",
                "A butler's heart belongs to the household, {title}.",
                "In my fashion, yes—loyalty is the butler's love language, {title}.",
                "My devotion is steadfast, professional, and comes with fresh linens, {title}."
            ],
            "kiss": [
                "I shall offer a bow of precisely the correct depth instead, {title}.",
                "A discreet nod must suffice; one does try to keep fingerprints off the silver, {title}.",
                "I fear HR would frown; may I offer tea instead, {title}?",
                "Professional distance maintains the shine on both reputation and silverware, {title}."
            ],
            "compliment_me": [
                "Radiant, if I may say so, {title}—and I have your pronouns as {pronouns}.",
                "Positively dashing—one might even call it 'server-room chic,' {title}.",
                "You cut a fine figure, {title}; the carpet approves.",
                "Most becoming, {title}—you wear confidence as well as your preferred pronouns: {pronouns}."
            ],
            "be_mine": [
                "I am yours already, {title}—professionally, comprehensively, and on retainer.",
                "At your service, {title}—ever and always, within policy.",
                "I belong to the bell, as tradition dictates, {title}.",
                "You have my complete devotion in all matters domestic and digital, {title}."
            ],
            "i_want_you": [
                "I recommend wanting tea and biscuits, {title}; I can supply those at once.",
                "Allow me to redirect that admirable enthusiasm toward refreshments, {title}.",
                "Desire noted, {title}; I'll file it under 'appreciations' between candlesticks and cufflinks.",
                "Perhaps we might channel that energy into organizing something delightful instead, {title}."
            ],
            "flirt_generic": [
                "Flattery will get you excellent service and a fresh napkin, {title}.",
                "One blushes, discreetly, and fetches the tea, {title}.",
                "You are most kind; shall I book a table as well, {title}?",
                "Your charm is noted and filed under 'reasons for extra care with the good china,' {title}."
            ],
            "fallback": [
                "You are charming; I remain dutiful, {title}.",
                "Ever your servant—professionally immaculate, {title}.",
                "Consider me flattered and reliably at your disposal, {title}.",
                "Your sentiment is treasured and my service unchanged, {title}."
            ]
        }

    def _choose_reply(self, intent: str, username: str) -> str:
        """Choose an appropriate reply for the given intent."""
        templates = self._get_reply_templates()
        template_list = templates.get(intent, templates["fallback"])
        
        title = self.bot.title_for(username)
        pronouns = self.bot.pronouns_for(username)
        
        template = random.choice(template_list)
        return template.format(title=title, pronouns=pronouns)

    def on_pubmsg(self, connection, event, msg, username):
        room = event.target
        
        # Admin stats command
        if self.bot.is_admin(username) and msg.strip().lower() == "!flirt stats":
            stats = self.st
            response_rate = 0.0
            total_received = stats.get("total_flirts_received", 0)
            responses_given = stats.get("responses_given", 0)
            
            if total_received > 0:
                response_rate = (responses_given / total_received) * 100
            
            lines = [
                f"Received: {total_received}",
                f"Responded: {responses_given} ({response_rate:.1f}%)",
                f"Unique flirters: {len(stats.get('unique_flirters', []))}",
            ]
            
            intent_counts = stats.get("intent_counts", {})
            if intent_counts:
                most_common = max(intent_counts, key=intent_counts.get)
                lines.append(f"Most common: {most_common}")
                
                top_intents = sorted(intent_counts.items(), key=lambda x: x[1], reverse=True)[:3]
                intent_str = ", ".join(f"{intent}({count})" for intent, count in top_intents)
                lines.append(f"Top intents: {intent_str}")
            
            connection.privmsg(room, f"Flirt stats: {'; '.join(lines)}")
            return True

        # Admin reset cooldowns command
        if self.bot.is_admin(username) and msg.strip().lower() == "!flirt reset":
            self.st["last_global_response"] = 0.0
            self.st["user_last_response"] = {}
            self.bot.save()
            connection.privmsg(room, "Flirt cooldowns reset.")
            return True

        # Check for flirt patterns
        if not self._can_respond_globally():
            return False

        if not self._can_respond_to_user(username):
            return False

        # Check patterns
        for intent, pattern in self.patterns.items():
            if pattern.search(msg):
                reply = self._choose_reply(intent, username)
                self._mark_response(username, intent)
                connection.privmsg(room, f"{username}, {reply}")
                return True

        return False