# modules/admin.py
# Administrative bot controls with dynamic configuration management.
import re
import time
import sys
import yaml
from pathlib import Path
from .base import SimpleCommandModule, admin_required

def setup(bot, config):
    return Admin(bot, config)

class Admin(SimpleCommandModule):
    name = "admin"
    version = "3.2.0" # Added admin management commands
    description = "Administrative bot controls."
    
    def __init__(self, bot, config):
        super().__init__(bot)
        if not hasattr(self.bot, "joined_channels"):
            self.bot.joined_channels = {self.bot.primary_channel}
        
        self.static_keys = [
            "api_keys", "admins", "module_blacklist", "name_pattern", "connection",
            "monsters", "story_beats", "world_lore", "classes", "boss_monsters",
            "events", "locations", "animals", "item_adjectives", "item_nouns"
        ]

    def _register_commands(self):
        self.register_command(r"^\s*!admin(?:\s+(.*))?$", self._cmd_admin_master,
                              name="admin", admin_only=True, description="Main admin command. Use '!admin help' for subcommands.")
        self.register_command(r"^\s*!reload\s*$", lambda c, e, m, u, ma: self._cmd_reload(c, e, u),
                              name="reload", admin_only=True, description="Alias for '!admin reload'.")
        self.register_command(r"^\s*!say(?:\s+(#\S+))?\s+(.+)$", self._cmd_say_alias,
                              name="say", admin_only=True, description="Alias for '!admin say'.")
        self.register_command(r"^\s*!emergency\s+quit(?:\s+(.+))?\s*$", self._cmd_emergency_quit,
                              name="emergency quit", admin_only=True, description="Emergency shutdown.")

    # --- Master Command Handler ---

    def _cmd_admin_master(self, connection, event, msg, username, match):
        args_str = (match.group(1) or "").strip()
        
        if not args_str:
            self.safe_reply(connection, event, "Please specify an admin command. Use '!admin help' for a list.")
            return True

        args = args_str.split()
        subcommand = args[0].lower()
        
        # --- Route to subcommand handlers ---
        if subcommand == "reload":
            return self._cmd_reload(connection, event, username)
        elif subcommand == "config" and len(args) > 1 and args[1].lower() == "reload":
            return self._cmd_config_reload(connection, event, username)
        elif subcommand == "addadmin" and len(args) > 1:
            return self._cmd_add_admin(connection, event, username, args[1])
        elif subcommand == "deladmin" and len(args) > 1:
            return self._cmd_del_admin(connection, event, username, args[1])
        elif subcommand in ("on", "off"):
            if len(args) < 2: return self._usage(connection, event, "on|off <module> [#channel]")
            module, channel = args[1], args[2] if len(args) > 2 else event.target
            return self._cmd_toggle_module(connection, event, username, module, channel, subcommand == "on")
        elif subcommand == "set":
            if len(args) < 3: return self._usage(connection, event, "set <module.setting.path> <value> [#channel|global]")
            path, value_str = args[1], " ".join(args[2:])
            channel = event.target # Default to current channel
            if value_str.rpartition(' ')[-1].startswith('#') or value_str.rpartition(' ')[-1] == "global":
                 parts = value_str.rpartition(' ')
                 value_str = parts[0]
                 channel = parts[2]
            return self._cmd_set_config(connection, event, username, path, value_str, channel)
        elif subcommand == "get":
            if len(args) < 2: return self._usage(connection, event, "get <module.setting.path> [#channel]")
            path = args[1]
            channel = args[2] if len(args) > 2 and args[2].startswith('#') else event.target
            return self._cmd_get_config(connection, event, username, path, channel)
        elif subcommand == "save":
             return self._cmd_save_config(connection, event, username)
        elif subcommand == "reset":
             return self._cmd_reset_config(connection, event, username)
        elif subcommand == "modules":
             return self._cmd_list_modules(connection, event, username)
        elif subcommand == "join" and len(args) > 1:
            return self._cmd_join(connection, event, username, args[1])
        elif subcommand == "part" and len(args) > 1:
            return self._cmd_part(connection, event, username, args[1], " ".join(args[2:]))
        elif subcommand == "say" and len(args) > 1:
            target = args[1] if args[1].startswith('#') else event.target
            message = " ".join(args[2:]) if args[1].startswith('#') else " ".join(args[1:])
            return self._cmd_say(connection, event, username, target, message)
        elif subcommand == "debug" and len(args) > 1:
            return self._cmd_debug_toggle(connection, event, username, args[1])
        elif subcommand == "help":
            return self._cmd_help(connection, event, username)
        else:
            self.safe_reply(connection, event, f"Unknown admin command. Use '!admin help'.")
            return True

    def _usage(self, connection, event, command_args):
        self.safe_reply(connection, event, f"Usage: !admin {command_args}")
        return True

    # --- Subcommand Logic ---
    
    def _cmd_reload(self, connection, event, username):
        loaded = self.bot.core_reload_plugins()
        self.safe_reply(connection, event, f"Modules reloaded: {', '.join(sorted(loaded))}")
        return True

    def _cmd_config_reload(self, connection, event, username):
        if self.bot.core_reload_config():
            self.safe_reply(connection, event, "Configuration reloaded from state.")
        else:
            self.safe_reply(connection, event, "Error reloading configuration.")
        return True

    def _cmd_add_admin(self, connection, event, username, target_user):
        config_copy = self.bot.get_module_state("config")
        core_cfg = config_copy.setdefault("core", {})
        admin_list = core_cfg.setdefault("admins", [])
        
        if target_user not in admin_list:
            admin_list.append(target_user)
            self.bot.update_module_state("config", config_copy)
            self.bot.core_reload_config()
            self.safe_reply(connection, event, f"Very good. {target_user} has been added to the admin list.")
        else:
            self.safe_reply(connection, event, f"{target_user} is already an administrator.")
        return True

    def _cmd_del_admin(self, connection, event, username, target_user):
        config_copy = self.bot.get_module_state("config")
        core_cfg = config_copy.setdefault("core", {})
        admin_list = core_cfg.setdefault("admins", [])
        
        if target_user in admin_list:
            admin_list.remove(target_user)
            self.bot.update_module_state("config", config_copy)
            self.bot.core_reload_config()
            self.safe_reply(connection, event, f"As you wish. {target_user} has been removed from the admin list.")
        else:
            self.safe_reply(connection, event, f"{target_user} was not on the admin list.")
        return True

    def _cmd_toggle_module(self, connection, event, username, module_name, channel, new_status):
        if module_name not in self.bot.pm.plugins:
            self.safe_reply(connection, event, f"Module '{module_name}' is not loaded.")
            return True
        
        config_copy = self.bot.get_module_state("config")
        module_cfg = config_copy.setdefault(module_name, {})
        channels_cfg = module_cfg.setdefault("channels", {})
        channels_cfg.setdefault(channel, {})["enabled"] = new_status
        
        self.bot.update_module_state("config", config_copy)
        self.bot.core_reload_config()
        
        status_str = "enabled" if new_status else "disabled"
        self.safe_reply(connection, event, f"Module '{module_name}' has been {status_str} for {channel}.")
        return True

    def _cmd_set_config(self, connection, event, username, path, value_str, channel):
        keys = path.split('.')
        module_name = keys[0]

        if module_name not in self.bot.pm.plugins:
            self.safe_reply(connection, event, f"Module '{module_name}' is not loaded.")
            return True

        if any(key in self.static_keys for key in keys):
            self.safe_reply(connection, event, f"My apologies, but '{path}' contains a static key and cannot be changed at runtime.")
            return True

        try:
            if value_str.lower() in ['true', 'on']: value = True
            elif value_str.lower() in ['false', 'off']: value = False
            elif '.' in value_str: value = float(value_str)
            else: value = int(value_str)
        except ValueError:
            value = value_str

        config_copy = self.bot.get_module_state("config")
        
        if channel == "global":
            d = config_copy
        else:
            d = config_copy.setdefault(module_name, {}).setdefault("channels", {}).setdefault(channel, {})
            if keys[0] == module_name: keys.pop(0)

        for key in keys[:-1]:
            d = d.setdefault(key, {})
        d[keys[-1]] = value

        self.bot.update_module_state("config", config_copy)
        self.bot.core_reload_config()
        self.safe_reply(connection, event, f"Config for '{path}' in {channel} set to '{value}'.")
        return True

    def _cmd_get_config(self, connection, event, username, path, channel):
        keys = path.split('.')
        module_name = keys[0]
        
        if module_name not in self.bot.pm.plugins:
            self.safe_reply(connection, event, f"Module '{module_name}' is not loaded.")
            return True
            
        config_copy = self.bot.get_module_state("config")
        
        val = None
        is_channel_override = False
        try:
            d = config_copy.get(module_name, {}).get("channels", {}).get(channel, {})
            val = d
            for key in keys[1:]: val = val[key]
            is_channel_override = True
        except KeyError:
             val = config_copy
             for key in keys: val = val.get(key)
             is_channel_override = False

        self.safe_reply(connection, event, f"Config for '{path}' in {channel} is '{val}' {'(Channel Override)' if is_channel_override else '(Global)'}")
        return True

    def _cmd_save_config(self, connection, event, username):
        saved_path = Path(self.bot.ROOT) / "config" / "config.yaml.saved"
        try:
            with open(saved_path, 'w') as f:
                yaml.dump(self.bot.config, f, default_flow_style=False, sort_keys=False)
            self.safe_reply(connection, event, f"Current running configuration has been saved to {saved_path.name}")
        except Exception as e:
            self.safe_reply(connection, event, f"An error occurred while saving the configuration: {e}")
        return True

    def _cmd_reset_config(self, connection, event, username):
        if self.bot.core_reset_and_reload_config():
             self.safe_reply(connection, event, "Configuration has been reset from config.yaml and all modules have been reloaded.")
        else:
             self.safe_reply(connection, event, "There was an error resetting the configuration. Please check the debug log.")
        return True

    def _cmd_list_modules(self, connection, event, username):
        loaded_modules = sorted(list(self.bot.pm.plugins.keys()))
        self.safe_reply(connection, event, f"Loaded modules ({len(loaded_modules)}): {', '.join(loaded_modules)}")
        return True

    def _cmd_join(self, connection, event, username, room):
        self.bot.connection.join(room)
        return True

    def _cmd_part(self, connection, event, username, room, msg):
        if room in self.bot.joined_channels:
            self.bot.connection.part(room, msg or "Leaving per request.")
        else:
            self.safe_reply(connection, event, f"I am not in {room}.")
        return True

    def _cmd_say(self, connection, event, username, target, message):
        self.bot.connection.privmsg(target, message)
        return True
        
    def _cmd_say_alias(self, connection, event, msg, username, match):
        target, message = match.groups()
        return self._cmd_say(connection, event, username, target or event.target, message)

    def _cmd_debug_toggle(self, connection, event, username, state: str):
        state_bool = state.lower() in ['on', 'true', '1', 'enable']
        self.bot.set_debug_mode(state_bool)
        self.safe_reply(connection, event, f"Debug mode is now {'ON' if state_bool else 'OFF'}.")
        return True
        
    def _cmd_emergency_quit(self, connection, event, msg, username, match):
        self.bot.connection.quit(match.group(1) or "Emergency quit.")
        return True

    def _cmd_help(self, connection, event, username):
        help_lines = [
            "!admin reload - Reload all modules.",
            "!admin config reload - Reload config from state.json.",
            "!admin modules - List all currently loaded modules.",
            "!admin addadmin <user> - Add a user to the admin list.",
            "!admin deladmin <user> - Remove a user from the admin list.",
            "!admin on|off <module> [#channel] - Enable/disable a module in a channel.",
            "!admin get <module.setting.path> [#channel] - View a config value.",
            "!admin set <module.setting.path> <value> [#channel|global] - Set a config value.",
            "!admin save - Save the current running config to config.yaml.saved.",
            "!admin reset - DANGEROUS: Reloads config from the original config.yaml.",
            "!admin join|part <#channel> [message] - Join or leave a channel.",
            "!say [#channel] <message> - Make the bot speak.",
            "!admin debug <on|off> - Toggle verbose file logging.",
            "!emergency quit [message] - Emergency shutdown."
        ]
        
        self.safe_reply(connection, event, "I have sent you the admin command list privately.")
        for line in help_lines:
            self.safe_privmsg(username, line)
        return True

