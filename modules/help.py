# modules/help.py
# Compact help system with individual command lookups
import re
import time

def setup(bot):
    return Help(bot)

class Help:
    name = "help"
    version = "1.1.0"
    
    # Cooldown to prevent spam
    COOLDOWN_SECONDS = 10.0
    
    def __init__(self, bot):
        self.bot = bot
        self.st = bot.get_module_state(self.name)
        
        # Initialize state
        self.st.setdefault("help_requests", 0)
        self.st.setdefault("command_lookups", 0)
        self.st.setdefault("users_helped", [])
        self.st.setdefault("last_help_time", {})
        
        # Command patterns
        self.RE_HELP = re.compile(r"^\s*!help\s*$", re.IGNORECASE)
        self.RE_HELP_COMMAND = re.compile(r"^\s*!help\s+(\S+)\s*$", re.IGNORECASE)
        
        # Natural language patterns
        name_pat = getattr(self.bot, "JEEVES_NAME_RE", r"(?:jeeves|jeevesbot)")
        self.RE_NL_HELP = re.compile(
            rf"\b{name_pat}[,!\s]*\s*(?:what\s+(?:can\s+you\s+do|commands)|help\s+me|show\s+me\s+(?:the\s+)?commands)\b",
            re.IGNORECASE
        )
        
        # Command database
        self._build_command_db()
        
        bot.save()
    
    def _build_command_db(self):
        """Build database of all available commands."""
        self.commands = {
            # User commands
            "fortune": "Get a fortune cookie. Use !fortune [spooky|happy|sad|silly] for specific categories",
            "adventure": "Start a choose-your-own-adventure voting session",
            "roadtrip": "Show details of the most recent roadtrip",
            "memo": "Leave a message for someone. Usage: !memo <nick> <message>",
            "memos": "Show your pending messages with !memos mine",
            "whoami": "Show your courtesy preferences (pronouns/title)",
            "gender": "Set your gender/title preference. Usage: !gender <identity>",
            "pronouns": "Set your preferred pronouns. Usage: !pronouns <pronouns>",
            "profile": "Show someone's courtesy profile. Usage: !profile <nick>",
            "forgetme": "Delete your courtesy preferences",
            "help": "Show available commands or get help for specific command",
            
            # Natural language
            "natural": "I also respond to natural language! Try 'Jeeves, I am male', 'my pronouns are they/them', 'Jeeves, should I do this?', or 'Coming Jeeves!' for roadtrips"
        }
        
        # Admin commands (added when user is admin)
        self.admin_commands = {
            "reload": "Reload all bot modules",
            "join": "Join a channel. Usage: !join #channel",
            "part": "Leave a channel. Usage: !part #channel [message]",
            "say": "Say something. Usage: !say [#channel] <message>",
            "channels": "List currently joined channels",
            "nick": "Change bot nickname. Usage: !nick <newnick>",
            "emergency": "Emergency shutdown. Usage: !emergency quit [message]",
            "stats": "Various stats commands: !adventure stats, !roadtrip stats, !courtesy stats, !fortune stats, !flirt stats, !replies stats, !memos stats, !help stats"
        }
    
    def _can_give_help(self, username: str) -> bool:
        """Check if user is off cooldown for help requests."""
        if self.COOLDOWN_SECONDS <= 0:
            return True
        
        now = time.time()
        last_times = self.st.get("last_help_time", {})
        last_time = last_times.get(username.lower(), 0)
        
        return now - last_time >= self.COOLDOWN_SECONDS
    
    def _mark_help_given(self, username: str, is_command_lookup: bool = False):
        """Mark that help was given to this user."""
        # Update cooldown
        last_times = self.st.get("last_help_time", {})
        last_times[username.lower()] = time.time()
        self.st["last_help_time"] = last_times
        
        # Update stats
        if is_command_lookup:
            self.st["command_lookups"] = self.st.get("command_lookups", 0) + 1
        else:
            self.st["help_requests"] = self.st.get("help_requests", 0) + 1
        
        # Track unique users
        users = self.st.get("users_helped", [])
        username_lower = username.lower()
        if username_lower not in users:
            users.append(username_lower)
            self.st["users_helped"] = users
        
        self.bot.save()
    
    def _get_command_list(self, is_admin: bool) -> str:
        """Get compact command list."""
        basic_cmds = list(self.commands.keys())
        if is_admin:
            admin_cmds = list(self.admin_commands.keys())
            all_cmds = basic_cmds + [f"{cmd}*" for cmd in admin_cmds]  # Mark admin commands with *
        else:
            all_cmds = basic_cmds
        
        return ", ".join(sorted(all_cmds))
    
    def _get_command_help(self, command: str, is_admin: bool) -> str:
        """Get help for a specific command."""
        # Remove ! prefix if present
        if command.startswith("!"):
            command = command[1:]
        
        # Remove * suffix if present (admin marker)
        if command.endswith("*"):
            command = command[:-1]
        
        command = command.lower()
        
        # Check basic commands first
        if command in self.commands:
            return self.commands[command]
        
        # Check admin commands
        if is_admin and command in self.admin_commands:
            return self.admin_commands[command]
        
        # Special handling for some command variations
        if command in ["adventures", "adv"]:
            return self.commands["adventure"]
        elif command in ["roadtrips", "trip"]:
            return self.commands["roadtrip"]
        elif command in ["memos"]:
            return self.commands["memos"]
        elif command == "nl":
            return self.commands["natural"]
        
        return None
    
    def on_load(self):
        pass
    
    def on_unload(self):
        pass
    
    def on_privmsg(self, connection, event):
        """Handle private messages for help requests."""
        msg = event.arguments[0] if event.arguments else ""
        username = event.source.split('!')[0]
        is_admin = self.bot.is_admin(username)
        
        # Check cooldown
        if not self._can_give_help(username):
            return False
        
        # Simple patterns for private messages (no ! prefix needed)
        help_simple = re.match(r"^\s*help\s*$", msg, re.IGNORECASE)
        help_command = re.match(r"^\s*help\s+(\S+)\s*$", msg, re.IGNORECASE)
        
        # Help for specific command
        if help_command:
            command = help_command.group(1)
            help_text = self._get_command_help(command, is_admin)
            
            if help_text:
                connection.privmsg(username, f"!{command}: {help_text}")
                self._mark_help_given(username, is_command_lookup=True)
            else:
                available_note = " (admin commands marked with *)" if is_admin else ""
                cmd_list = self._get_command_list(is_admin)
                connection.privmsg(username, f"Unknown command. Available: {cmd_list}{available_note}")
            return True
        
        # General help request
        elif help_simple:
            title = self.bot.title_for(username)
            available_note = " (admin commands marked with *)" if is_admin else ""
            cmd_list = self._get_command_list(is_admin)
            
            connection.privmsg(username, f"Available commands, {title}: {cmd_list}{available_note}")
            connection.privmsg(username, f"Use 'help <command>' for details on any command. I also respond to natural language - just address me by name!")
            self._mark_help_given(username)
            return True
        
        return False
    
    def on_pubmsg(self, connection, event, msg, username):
        room = event.target
        is_admin = self.bot.is_admin(username)
        
        # Admin stats command
        if is_admin and msg.strip().lower() == "!help stats":
            stats = self.st
            help_requests = stats.get("help_requests", 0)
            command_lookups = stats.get("command_lookups", 0)
            unique_users = len(stats.get("users_helped", []))
            
            connection.privmsg(room, f"Help stats: {help_requests} general requests, {command_lookups} command lookups from {unique_users} unique users")
            return True
        
        # Check cooldown
        if not self._can_give_help(username):
            return False
        
        # Help for specific command
        if match := self.RE_HELP_COMMAND.match(msg):
            command = match.group(1)
            help_text = self._get_command_help(command, is_admin)
            
            if help_text:
                # Send specific command help privately to avoid channel clutter
                self.bot.privmsg(username, f"!{command}: {help_text}")
                connection.privmsg(room, f"{username}, command help sent privately.")
                self._mark_help_given(username, is_command_lookup=True)
            else:
                available_note = " (admin commands marked with *)" if is_admin else ""
                cmd_list = self._get_command_list(is_admin)
                connection.privmsg(room, f"{username}, unknown command. Available: {cmd_list}{available_note}")
            return True
        
        # General help request
        if self.RE_HELP.match(msg) or self.RE_NL_HELP.search(msg):
            title = self.bot.title_for(username)
            available_note = " (admin commands marked with *)" if is_admin else ""
            cmd_list = self._get_command_list(is_admin)
            
            self.bot.privmsg(username, f"Available commands, {title}: {cmd_list}{available_note}")
            self.bot.privmsg(username, f"Use !help <command> for details on any command. I also respond to natural language - just address me by name!")
            
            connection.privmsg(room, f"{username}, command list sent privately. Use !help <command> for specific help.")
            self._mark_help_given(username)
            return True
        
        return False