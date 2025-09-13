# modules/base.py
# Enhanced base class for all Jeeves modules with common utilities and patterns

import re
import time
import threading
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Callable, Union
from datetime import datetime, timezone
import functools

class ModuleBase(ABC):
    """
    Enhanced base class for Jeeves modules with common functionality,
    state management, command registration, and utility methods.
    """
    
    # Module metadata - override in subclasses
    name = "base"
    version = "1.0.0"
    description = "Base module class"
    dependencies: List[str] = []  # List of required module names
    
    # Command registration system
    _commands: Dict[str, Dict[str, Any]] = {}
    _scheduled_tasks: List[Callable] = []
    
    def __init__(self, bot):
        self.bot = bot
        self._state_cache = {}
        self._state_dirty = False
        self._state_lock = threading.RLock()
        
        # Performance tracking
        self._call_stats = {
            "messages_processed": 0,
            "commands_executed": 0,
            "errors": 0,
            "last_activity": None,
            "average_response_time": 0.0,
            "total_response_time": 0.0
        }
        
        # Rate limiting
        self._rate_limits = {}
        self._user_cooldowns = {}
        
        # Initialize state
        self._load_state()

    # ---- State Management ----
    def _load_state(self):
        """Load module state with caching."""
        with self._state_lock:
            self._state_cache = self.bot.get_module_state(self.name).copy()
            self._state_dirty = False

    def get_state(self, key: Optional[str] = None, default: Any = None) -> Any:
        """Get state value(s) with optional key access."""
        with self._state_lock:
            if key is None:
                return self._state_cache.copy()
            return self._state_cache.get(key, default)

    def set_state(self, key: str, value: Any) -> None:
        """Set a single state value."""
        with self._state_lock:
            self._state_cache[key] = value
            self._state_dirty = True

    def update_state(self, updates: Dict[str, Any]) -> None:
        """Update multiple state values at once."""
        with self._state_lock:
            self._state_cache.update(updates)
            self._state_dirty = True

    def save_state(self, force: bool = False) -> None:
        """Save state to persistent storage if dirty."""
        with self._state_lock:
            if self._state_dirty or force:
                self.bot.update_module_state(self.name, self._state_cache)
                self._state_dirty = False

    # ---- Command Registration System ----
    def register_command(self, pattern: Union[str, re.Pattern], 
                        handler: Callable, 
                        admin_only: bool = False,
                        cooldown: float = 0.0,
                        description: str = "") -> None:
        """
        Register a command pattern with its handler.
        
        Args:
            pattern: Regex pattern (string or compiled) to match
            handler: Function to call when pattern matches
            admin_only: Whether command requires admin privileges
            cooldown: Cooldown in seconds between uses per user
            description: Help text for the command
        """
        if isinstance(pattern, str):
            pattern = re.compile(pattern, re.IGNORECASE)
        
        command_id = f"{self.name}_{len(self._commands)}"
        self._commands[command_id] = {
            "pattern": pattern,
            "handler": handler,
            "admin_only": admin_only,
            "cooldown": cooldown,
            "description": description,
            "uses": 0,
            "last_used": None
        }

    def unregister_all_commands(self) -> None:
        """Remove all registered commands."""
        self._commands.clear()

    # ---- Rate Limiting ----
    def check_rate_limit(self, key: str, limit: float) -> bool:
        """Check if rate limit allows action."""
        now = time.time()
        last_time = self._rate_limits.get(key, 0)
        
        if now - last_time >= limit:
            self._rate_limits[key] = now
            return True
        return False

    def check_user_cooldown(self, username: str, command: str, cooldown: float) -> bool:
        """Check if user is on cooldown for a specific command."""
        if cooldown <= 0:
            return True
            
        key = f"{username}:{command}"
        now = time.time()
        last_use = self._user_cooldowns.get(key, 0)
        
        if now - last_use >= cooldown:
            self._user_cooldowns[key] = now
            return True
        return False

    # ---- Utility Methods ----
    def is_mentioned(self, msg: str) -> bool:
        """Check if the bot is mentioned in the message."""
        pattern = re.compile(self.bot.JEEVES_NAME_RE, re.IGNORECASE)
        return bool(pattern.search(msg))

    def strip_mention(self, msg: str) -> str:
        """Remove bot mentions from message."""
        pattern = re.compile(self.bot.JEEVES_NAME_RE + r'[,:]\s*', re.IGNORECASE)
        return pattern.sub('', msg).strip()

    def format_time_elapsed(self, start_time: float) -> str:
        """Format elapsed time in human readable format."""
        elapsed = time.time() - start_time
        if elapsed < 60:
            return f"{elapsed:.1f}s"
        elif elapsed < 3600:
            return f"{int(elapsed // 60)}m {int(elapsed % 60)}s"
        else:
            hours = int(elapsed // 3600)
            minutes = int((elapsed % 3600) // 60)
            return f"{hours}h {minutes}m"

    def safe_say(self, text: str, target: Optional[str] = None) -> bool:
        """Safely send message with error handling."""
        try:
            if target:
                self.bot.say_to(target, text)
            else:
                self.bot.say(text)
            return True
        except Exception as e:
            self._record_error(f"Failed to send message: {e}")
            return False

    def safe_privmsg(self, username: str, text: str) -> bool:
        """Safely send private message with error handling."""
        try:
            self.bot.privmsg(username, text)
            return True
        except Exception as e:
            self._record_error(f"Failed to send privmsg to {username}: {e}")
            return False

    # ---- Performance Tracking ----
    def _record_error(self, error_msg: str) -> None:
        """Record an error for debugging."""
        self._call_stats["errors"] += 1
        print(f"[{self.name}] ERROR: {error_msg}")

    def _update_performance_stats(self, response_time: float) -> None:
        """Update performance statistics."""
        stats = self._call_stats
        stats["total_response_time"] += response_time
        if stats["messages_processed"] > 0:
            stats["average_response_time"] = stats["total_response_time"] / stats["messages_processed"]
        stats["last_activity"] = time.time()

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get module performance statistics."""
        return self._call_stats.copy()

    # ---- Decorators ----
    @staticmethod
    def admin_required(func):
        """Decorator to require admin privileges for a command."""
        @functools.wraps(func)
        def wrapper(self, connection, event, msg, username, *args, **kwargs):
            if not self.bot.is_admin(username):
                return False  # Silent denial
            return func(self, connection, event, msg, username, *args, **kwargs)
        return wrapper

    @staticmethod
    def rate_limited(rate: float):
        """Decorator to add rate limiting to a command."""
        def decorator(func):
            @functools.wraps(func)
            def wrapper(self, connection, event, msg, username, *args, **kwargs):
                key = f"{self.name}:{func.__name__}:{username}"
                if not self.check_rate_limit(key, rate):
                    return False  # Rate limited
                return func(self, connection, event, msg, username, *args, **kwargs)
            return wrapper
        return decorator

    # ---- Lifecycle Methods ----
    def on_load(self) -> None:
        """Called when module is loaded. Override in subclasses."""
        self.save_state()  # Ensure state is initialized

    def on_unload(self) -> None:
        """Called when module is unloaded. Override in subclasses."""
        self.save_state(force=True)  # Save any pending state
        self.unregister_all_commands()
        
        # Clean up scheduled tasks
        self._scheduled_tasks.clear()
        
        # Clean up rate limiting data
        self._rate_limits.clear()
        self._user_cooldowns.clear()

    def on_pubmsg(self, connection, event, msg: str, username: str) -> bool:
        """
        Enhanced message handler with command dispatch and performance tracking.
        Override this method OR use the command registration system.
        """
        start_time = time.time()
        
        try:
            self._call_stats["messages_processed"] += 1
            
            # Try registered commands first
            handled = self._dispatch_commands(connection, event, msg, username)
            if handled:
                self._call_stats["commands_executed"] += 1
                return True
            
            # Call custom handler if implemented
            if hasattr(self, '_handle_message'):
                handled = self._handle_message(connection, event, msg, username)
                if handled:
                    self._call_stats["commands_executed"] += 1
                return handled
            
            return False
            
        except Exception as e:
            self._record_error(f"Error in on_pubmsg: {e}")
            return False
        finally:
            response_time = time.time() - start_time
            self._update_performance_stats(response_time)

    def _dispatch_commands(self, connection, event, msg: str, username: str) -> bool:
        """Dispatch message to registered command handlers."""
        for cmd_id, cmd_info in self._commands.items():
            pattern = cmd_info["pattern"]
            match = pattern.match(msg)
            
            if not match:
                continue
            
            # Check admin requirements
            if cmd_info["admin_only"] and not self.bot.is_admin(username):
                continue
            
            # Check cooldown
            if not self.check_user_cooldown(username, cmd_id, cmd_info["cooldown"]):
                continue
            
            try:
                # Call handler with match groups
                result = cmd_info["handler"](connection, event, msg, username, match)
                
                # Update command statistics
                cmd_info["uses"] += 1
                cmd_info["last_used"] = time.time()
                
                if result:
                    return True
                    
            except Exception as e:
                self._record_error(f"Error in command {cmd_id}: {e}")
                continue
        
        return False

    # ---- Helper Methods for Common Patterns ----
    def schedule_delayed_action(self, delay: float, action: Callable, *args, **kwargs) -> threading.Timer:
        """Schedule an action to run after a delay."""
        def wrapper():
            try:
                action(*args, **kwargs)
            except Exception as e:
                self._record_error(f"Error in scheduled action: {e}")
        
        timer = threading.Timer(delay, wrapper)
        timer.start()
        self._scheduled_tasks.append(timer)
        return timer

    def get_user_profile(self, username: str) -> Dict[str, Any]:
        """Get user profile information."""
        return {
            "title": self.bot.title_for(username),
            "pronouns": self.bot.pronouns_for(username),
            "is_admin": self.bot.is_admin(username)
        }

    def format_user_address(self, username: str) -> str:
        """Format a polite address for a user."""
        title = self.bot.title_for(username)
        return f"{title} {username}" if title != "Mx." else username

# ---- Specialized Base Classes ----

class SimpleCommandModule(ModuleBase):
    """
    Base class for modules that primarily respond to simple commands.
    Provides convenient command registration in __init__.
    """
    
    def __init__(self, bot):
        super().__init__(bot)
        self._register_commands()
    
    @abstractmethod
    def _register_commands(self) -> None:
        """Override this to register your commands."""
        pass

class ResponseModule(ModuleBase):
    """
    Base class for modules that react to keywords or patterns in messages.
    Provides convenient pattern matching utilities.
    """
    
    def __init__(self, bot):
        super().__init__(bot)
        self._response_patterns = []
    
    def add_response_pattern(self, pattern: Union[str, re.Pattern], 
                           response: Union[str, Callable], 
                           probability: float = 1.0) -> None:
        """Add a pattern that triggers a response."""
        if isinstance(pattern, str):
            pattern = re.compile(pattern, re.IGNORECASE)
        
        self._response_patterns.append({
            "pattern": pattern,
            "response": response,
            "probability": probability
        })
    
    def _handle_message(self, connection, event, msg: str, username: str) -> bool:
        """Check message against response patterns."""
        import random
        
        for item in self._response_patterns:
            if item["pattern"].search(msg):
                if random.random() <= item["probability"]:
                    response = item["response"]
                    if callable(response):
                        response = response(msg, username)
                    if response:
                        self.safe_say(response)
                        return True
        return False