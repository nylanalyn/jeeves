# modules/chatter.py
# Enhanced daily/weekly scheduled messages + contextual responses - FIXED room targeting
import random
import re
import schedule
import time
import threading
from datetime import datetime, timezone, timedelta

UTC = timezone.utc

def setup(bot): 
    return Chatter(bot)

class Chatter:
    name = "chatter"
    version = "2.0.1"
    
    # Enhanced pattern matching for better detection
    ANIMAL_WORDS = re.compile(r"\b(?:duck|ducks|cat|cats|kitten|kittens|puppy|puppies|dog|dogs|rabbit|rabbits|bird|birds|fish|hamster|guinea\s+pig)\b", re.IGNORECASE)
    WEATHER_WORDS = re.compile(r"\b(?:rain|raining|sunny|cloudy|storm|snow|snowing|hot|cold|weather|forecast)\b", re.IGNORECASE)
    TECH_WORDS = re.compile(r"\b(?:bug|bugs|crash|crashed|error|broken|fix|deploy|deployment|server|database|code|coding|programming)\b", re.IGNORECASE)
    FOOD_WORDS = re.compile(r"\b(?:tea|coffee|lunch|dinner|breakfast|hungry|food|eat|eating|cake|biscuit|sandwich)\b", re.IGNORECASE)
    GREETING_WORDS = re.compile(r"\b(?:hello|hi|hey|good\s+morning|good\s+afternoon|good\s+evening|greetings)\b", re.IGNORECASE)
    
    # Expanded response collections with more variety
    DAILY_LINES = [
        "If I might venture, {title}: turning it off and on again remains the sovereign remedy.",
        "Very good, {title}. I've queued the chaos for after tea.",
        "Might I suggest, {title}, that the cloud be treated as weather—admired, not trusted.",
        "Indeed, {title}: one cannot argue with results, though results frequently try.",
        "A most illuminating day, if I may observe. The servers appear to be in particularly cooperative spirits.",
        "The morning brings fresh opportunities for elegant solutions, {title}.",
        "I trust the digital realm is treating you kindly today, {title}.",
        "Another day dawns with infinite possibilities and finitely reliable networks.",
        "If I may note: today's challenges appear surmountable with the proper application of caffeine and logic.",
    ]
    
    WEEKLY_LINES = [
        "If I may, {title}: a well-timed hint often accomplishes what a thousand words cannot.",
        "The subtext appears to be applying for a promotion to text, {title}.",
        "One observes that between the lines, there lies an entire novel of implication.",
        "The art of diplomatic suggestion remains undiminished by the digital age, {title}.",
        "I detect undertones that could benefit from a more forthright expression.",
        "The week's patterns suggest certain... unspoken considerations merit attention.",
    ]
    
    # Contextual responses for different topics
    ANIMAL_RESPONSES = [
        "If I may, there seems to be a veritable menagerie about. One risks tripping over a tail at every turn.",
        "The animal kingdom appears well-represented in today's discourse. Most charming.",
        "I do hope the creatures in question are receiving proper attention and care.",
        "A delightful menagerie of references, if I may observe.",
        "One cannot help but appreciate the diversity of our four-legged friends in conversation.",
    ]
    
    WEATHER_RESPONSES = [
        "The weather does have a way of influencing both mood and server performance, I've observed.",
        "Nature's temperament appears as unpredictable as network connectivity, {title}.",
        "One must dress appropriately for both the weather and the possibility of server room visits.",
        "The meteorological conditions do seem to correlate with system stability in mysterious ways.",
    ]
    
    TECH_RESPONSES = [
        "Ah, the eternal dance of human and machine. Most enlightening.",
        "I find that technical difficulties often resolve themselves with patience and proper documentation.",
        "The art of troubleshooting remains one of life's more philosophical pursuits.",
        "Technology, like a well-trained butler, performs best when properly maintained.",
    ]
    
    FOOD_RESPONSES = [
        "A well-timed refreshment often provides clarity that hours of debugging cannot.",
        "The correlation between proper nutrition and code quality is well-established, {title}.",
        "I've observed that the best solutions often emerge during tea breaks.",
        "Sustenance for both body and mind remains essential for peak performance.",
    ]
    
    GREETING_RESPONSES = [
        "Good {time_of_day}, {title}. I trust you're well?",
        "A pleasure to see you, {title}. The day progresses admirably.",
        "Greetings, {title}. I hope the day finds you in good spirits.",
        "Welcome, {title}. How may I be of assistance today?",
    ]

    def __init__(self, bot):
        self.bot = bot
        self.st = bot.get_module_state(self.name)
        
        # Initialize state with defaults
        self.st.setdefault("last_daily", None)
        self.st.setdefault("last_weekly", None)
        self.st.setdefault("last_animals", None)
        self.st.setdefault("daily_count", 0)
        self.st.setdefault("weekly_count", 0)
        self.st.setdefault("response_counts", {})
        self.st.setdefault("schedule_times", {})
        self.st.setdefault("user_interactions", {})
        
        # Response tracking for anti-spam
        self._last_responses = {}
        self._response_cooldowns = {
            "animal": 3600,      # 1 hour between animal responses
            "weather": 1800,     # 30 minutes between weather responses  
            "tech": 900,         # 15 minutes between tech responses
            "food": 1200,        # 20 minutes between food responses
            "greeting": 300,     # 5 minutes between greetings
        }
        
        bot.save()

    def on_load(self):
        """Set up schedules when module loads."""
        # Clear any existing schedules for this module
        schedule.clear(self.name)
        
        # Set up new schedules
        self._schedule_daily_message()
        self._schedule_weekly_message()

    def on_unload(self):
        """Clean up when module unloads."""
        # Clear schedules
        schedule.clear(self.name)
        
        # Clean up response tracking
        self._last_responses.clear()

    def _get_time_of_day(self) -> str:
        """Get appropriate time of day greeting."""
        hour = datetime.now(UTC).hour
        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 22:
            return "evening"
        else:
            return "evening"  # Late night treated as evening

    def _format_line(self, line: str, username: str = "nobody") -> str:
        """Enhanced line formatting with more context."""
        return line.format(
            title=self.bot.title_for(username),
            pronouns=self.bot.pronouns_for(username),
            time_of_day=self._get_time_of_day()
        )

    def _random_time(self) -> str:
        """Generate random time with business hour bias for daily messages."""
        # Bias toward business hours (9-17) for daily messages
        if random.random() < 0.7:  # 70% chance of business hours
            hour = random.randint(9, 17)
        else:
            hour = random.randint(0, 23)
        minute = random.randint(0, 59)
        return f"{hour:02d}:{minute:02d}"

    def _can_respond(self, response_type: str) -> bool:
        """Check if enough time has passed since last response of this type."""
        now = time.time()
        last_time = self._last_responses.get(response_type, 0)
        cooldown = self._response_cooldowns.get(response_type, 300)
        
        return now - last_time >= cooldown

    def _mark_response(self, response_type: str):
        """Mark that we've responded with this type."""
        self._last_responses[response_type] = time.time()
        
        # Update statistics
        counts = self.st.get("response_counts", {})
        counts[response_type] = counts.get(response_type, 0) + 1
        self.st["response_counts"] = counts
        self.bot.save()

    # ---- Scheduled Message System ----
    def _schedule_daily_message(self):
        """Schedule the next daily message with jitter."""
        schedule.clear("daily")
        next_time = self._random_time()
        schedule.every().day.at(next_time).do(self._say_daily).tag(self.name, "daily")
        
        # Store schedule info for debugging
        schedule_times = self.st.get("schedule_times", {})
        schedule_times["next_daily"] = next_time
        self.st["schedule_times"] = schedule_times
        self.bot.save()

    def _schedule_weekly_message(self):
        """Schedule the next weekly message with random day/time."""
        schedule.clear("weekly")
        weekday = random.choice(["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"])
        next_time = self._random_time()
        
        getattr(schedule.every(), weekday).at(next_time).do(self._say_weekly).tag(self.name, "weekly")
        
        # Store schedule info for debugging
        schedule_times = self.st.get("schedule_times", {})
        schedule_times["next_weekly"] = f"{weekday} at {next_time}"
        self.st["schedule_times"] = schedule_times
        self.bot.save()

    def _say_daily(self):
        """Send daily message if not already sent today."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        last_daily = self.st.get("last_daily")
        
        if last_daily == today:
            return  # Already sent today
        
        # Select and send message
        message = self._format_line(random.choice(self.DAILY_LINES))
        try:
            # FIXED: Send to primary channel only (scheduled messages are global)
            self.bot.say(message)
        except Exception as e:
            print(f"[chatter] error sending daily message: {e}", file=sys.stderr)
        
        # Update state
        self.st["last_daily"] = today
        count = self.st.get("daily_count", 0) + 1
        self.st["daily_count"] = count
        self.bot.save()
        
        # Schedule next day's message
        self._schedule_daily_message()

    def _say_weekly(self):
        """Send weekly message if not already sent this week."""
        year, week, _ = datetime.now(UTC).isocalendar()
        week_key = f"{year}-{week:02d}"
        last_weekly = self.st.get("last_weekly")
        
        if last_weekly == week_key:
            return  # Already sent this week
        
        # Select and send message
        message = self._format_line(random.choice(self.WEEKLY_LINES))
        try:
            # FIXED: Send to primary channel only (scheduled messages are global)
            self.bot.say(message)
        except Exception as e:
            print(f"[chatter] error sending weekly message: {e}", file=sys.stderr)
        
        # Update state
        self.st["last_weekly"] = week_key
        count = self.st.get("weekly_count", 0) + 1
        self.st["weekly_count"] = count
        self.bot.save()
        
        # Schedule next week's message
        self._schedule_weekly_message()

    # ---- Contextual Response Handlers ----
    def _handle_animal_mention(self, connection, event, msg: str, username: str) -> bool:
        """Handle animal mentions with monthly cooldown per room."""
        month_key = datetime.now(UTC).strftime("%Y-%m")
        last_animal_month = self.st.get("last_animals")
        
        if last_animal_month != month_key and self._can_respond("animal"):
            self.st["last_animals"] = month_key
            self._mark_response("animal")
            
            response = random.choice(self.ANIMAL_RESPONSES)
            try:
                # FIXED: Reply to the room where the message came from
                connection.privmsg(event.target, response)
            except Exception as e:
                print(f"[chatter] error sending animal response: {e}", file=sys.stderr)
            return True
        return False

    def _handle_contextual_response(self, connection, event, pattern, responses, response_type, username, msg):
        """Handle contextual responses with cooldown checking."""
        if pattern.search(msg) and self._can_respond(response_type):
            self._mark_response(response_type)
            response = self._format_line(random.choice(responses), username)
            try:
                # FIXED: Reply to the room where the message came from
                connection.privmsg(event.target, response)
            except Exception as e:
                print(f"[chatter] error sending {response_type} response: {e}", file=sys.stderr)
            return True
        return False

    def on_pubmsg(self, connection, event, msg, username):
        """Handle public messages with contextual responses and admin commands."""
        
        # Admin debugging commands
        if self.bot.is_admin(username):
            if msg.strip().lower() == "!chatter stats":
                stats = self.st
                response_counts = stats.get("response_counts", {})
                schedule_times = stats.get("schedule_times", {})
                
                lines = [
                    f"Daily messages sent: {stats.get('daily_count', 0)}",
                    f"Weekly messages sent: {stats.get('weekly_count', 0)}",
                    f"Last daily: {stats.get('last_daily', 'Never')}",
                    f"Last weekly: {stats.get('last_weekly', 'Never')}",
                    f"Response counts: {dict(response_counts)}",
                    f"Next schedules: {dict(schedule_times)}"
                ]
                
                connection.privmsg(event.target, f"Chatter statistics: {'; '.join(lines)}")
                return True
                
            elif msg.strip().lower() == "!chatter test daily":
                self._say_daily()
                return True
                
            elif msg.strip().lower() == "!chatter test weekly":
                self._say_weekly()
                return True

        # Handle animal mentions (special case with monthly cooldown)
        if self.ANIMAL_WORDS.search(msg):
            return self._handle_animal_mention(connection, event, msg, username)

        # Handle other contextual responses - FIXED: all now pass connection and event
#        if self._handle_contextual_response(connection, event, self.WEATHER_WORDS, self.WEATHER_RESPONSES, "weather", username, msg):
#            return True
            
#        if self._handle_contextual_response(connection, event, self.TECH_WORDS, self.TECH_RESPONSES, "tech", username, msg):
#            return True
            
#        if self._handle_contextual_response(connection, event, self.FOOD_WORDS, self.FOOD_RESPONSES, "food", username, msg):
#            return True
            
#        if self._handle_contextual_response(connection, event, self.GREETING_WORDS, self.GREETING_RESPONSES, "greeting", username, msg):
#            return True

        return False
