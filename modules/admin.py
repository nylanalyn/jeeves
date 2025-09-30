# modules/admin.py
# Administrative bot controls with dynamic configuration management.
import re
import time
import sys
import yaml
from pathlib import Path
from .base import SimpleCommandModule, admin_required

def setup(bot):
    return Admin(bot)

class Admin(SimpleCommandModule):
    name = "admin"
    version = "3.3.1" # Improved feedback on module load failure
    description = "Administrative bot controls."
    
    def __init__(self, bot):
        super().__init__(bot)
        if not hasattr(self.bot, "joined_channels"):
            self.bot.joined_channels = {self.bot.primary_channel}
        
        self.static_keys = [
            "api_keys", "admins", "module_blacklist", "name_pattern", "connection",
            "monsters", "story_beats", "world_lore", "classes", "boss_monsters",
            "events", "locations", "animals", "item_adjectives", "item_nouns",
            "pending_reminders"
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
        
        if subcommand == "reload":
            return self._cmd_reload(connection, event, username)
        elif subcommand == "load" and len(args) > 1:
            return self._cmd_load(connection, event, username, args[1])
        elif subcommand == "unload" and len(args) > 1:
            return self._cmd_unload(connection, event, username, args[1])
        elif subcommand == "config" and len(args) > 1 and args[1].lower() == "reload":
            return self._cmd_config_reload(connection, event, username)
        elif subcommand == "blacklist" and len(args) > 1:
            return self._cmd_blacklist(connection, event, username, args[1])
        elif subcommand == "unblacklist" and len(args) > 1:
            return self._cmd_unblacklist(connection, event, username, args[1])
        elif subcommand in ("on", "off"):
            if len(args) < 2: return self._usage(connection, event, "on|off <module> [#channel]")
            module, channel = args[1], args[2] if len(args) > 2 else event.target
            return self._cmd_toggle_module(connection, event, username, module, channel, subcommand == "on")
        elif subcommand == "set":
            if len(args) < 3: return self._usage(connection, event, "set <module.setting.path> <value> [#channel|global]")
            path, value_str = args[1], " ".join(args[2:])
            channel = event.target
            if value_str.rpartition(' ')[-1].startswith('#') or value_str.rpartition(' ')[-1] == "global":
                 parts = value_str.rpartition(' ')
                 value_str, channel = parts[0], parts[2]
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
        elif subcommand == "addadmin" and len(args) > 1:
            return self._cmd_add_admin(connection, event, username, args[1])
        elif subcommand == "deladmin" and len(args) > 1:
            return self._cmd_del_admin(connection, event, username, args[1])
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
        
    def _cmd_load(self, connection, event, username, module_name):
        if self.bot.pm.load_module(module_name):
            self.safe_reply(connection, event, f"Module '{module_name}' loaded successfully.")
        else:
            self.safe_reply(connection, event, f"Failed to load module '{module_name}'. Please check the debug.log file for specific errors (e.g., a missing API key or an uninstalled library).")
        return True

    def _cmd_unload(self, connection, event, username, module_name):
        if self.bot.pm.unload_module(module_name):
            self.safe_reply(connection, event, f"Module '{module_name}' unloaded successfully.")
        else:
            self.safe_reply(connection, event, f"Failed to unload module '{module_name}'. It may not be loaded.")
        return True

    def _cmd_config_reload(self, connection, event, username):
        if self.bot.core_reload_config():
            self.safe_reply(connection, event, "Configuration reloaded from state.")
        else:
            self.safe_reply(connection, event, "Error reloading configuration.")
        return True

    def _cmd_blacklist(self, connection, event, username, module_file):
        config_copy = self.bot.get_module_state("config")
        core_cfg = config_copy.setdefault("core", {})
        bl = core_cfg.setdefault("module_blacklist", [])
        if module_file not in bl:
            bl.append(module_file)
            self.bot.update_module_state("config", config_copy)
            self.bot.core_reload_config()
            
            module_name = module_file.replace(".py", "")
            if self.bot.pm.unload_module(module_name):
                self.safe_reply(connection, event, f"Module '{module_name}' has been unloaded and added to the blacklist.")
            else:
                self.safe_reply(connection, event, f"Module '{module_file}' added to the blacklist. It was not currently loaded.")
        else:
            self.safe_reply(connection, event, f"'{module_file}' is already in the blacklist.")
        return True

    def _cmd_unblacklist(self, connection, event, username, module_file):
        config_copy = self.bot.get_module_state("config")
        core_cfg = config_copy.setdefault("core", {})
        bl = core_cfg.setdefault("module_blacklist", [])
        if module_file in bl:
            bl.remove(module_file)
            self.bot.update_module_state("config", config_copy)
            self.bot.core_reload_config()
            self.safe_reply(connection, event, f"Module '{module_file}' removed from the blacklist. Use `!admin load {module_file.replace('.py','')}` to load it.")
        else:
            self.safe_reply(connection, event, f"'{module_file}' is not in the blacklist.")
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

        if module_name == "core" and "admins" in keys:
             self.safe_reply(connection, event, "Please use the '!admin addadmin/deladmin' commands to manage administrators.")
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
        
        d = config_copy
        path_for_nav = keys
        if channel != "global":
            d = d.setdefault(module_name, {}).setdefault("channels", {}).setdefault(channel, {})
            path_for_nav = keys[1:]

        if not path_for_nav:
            self.safe_reply(connection, event, "Cannot set a value on a module directly. Specify a setting, e.g., module.setting")
            return True

        for key in path_for_nav[:-1]:
            d = d.setdefault(key, {})
        d[path_for_nav[-1]] = value

        self.bot.update_module_state("config", config_copy)
        self.bot.core_reload_config()
        self.safe_reply(connection, event, f"Config for '{path}' in {channel} set to '{value}'.")
        return True

    def _cmd_get_config(self, connection, event, username, path, channel):
        keys = path.split('.')
        module_name = keys[0]
        
        module_instance = self.bot.pm.plugins.get(module_name)
        if not module_instance and module_name != "core":
            self.safe_reply(connection, event, f"Module '{module_name}' is not loaded.")
            return True
            
        config_copy = self.bot.get_module_state("config")
        
        try:
            d_chan = config_copy.get(module_name, {}).get("channels", {}).get(channel, {})
            val_chan = d_chan
            for key in keys[1:]: val_chan = val_chan[key]
            self.safe_reply(connection, event, f"Config for '{path}' in {channel} is '{val_chan}' (Channel Override)")
            return True
        except KeyError:
            try:
                val_glob = config_copy
                for key in keys: val_glob = val_glob[key]
                self.safe_reply(connection, event, f"Config for '{path}' in {channel} is '{val_glob}' (Global)")
                return True
            except KeyError:
                self.safe_reply(connection, event, f"Could not find configuration value for '{path}'.")
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
        
    def _cmd_add_admin(self, connection, event, username, new_admin_nick):
        config_copy = self.bot.get_module_state("config")
        core_cfg = config_copy.setdefault("core", {})
        admins = core_cfg.setdefault("admins", [])
        if new_admin_nick not in admins:
            admins.append(new_admin_nick)
            self.bot.update_module_state("config", config_copy)
            self.bot.core_reload_config()
            self.safe_reply(connection, event, f"'{new_admin_nick}' has been added to the administrators list.")
        else:
            self.safe_reply(connection, event, f"'{new_admin_nick}' is already an administrator.")
        return True

    def _cmd_del_admin(self, connection, event, username, admin_to_remove):
        if admin_to_remove.lower() == username.lower():
            self.safe_reply(connection, event, "One cannot remove oneself from the administrators list.")
            return True
            
        config_copy = self.bot.get_module_state("config")
        core_cfg = config_copy.setdefault("core", {})
        admins = core_cfg.setdefault("admins", [])
        
        admin_found = next((admin for admin in admins if admin.lower() == admin_to_remove.lower()), None)
        
        if admin_found:
            admins.remove(admin_found)
            self.bot.update_module_state("config", config_copy)
            self.bot.core_reload_config()
            self.safe_reply(connection, event, f"'{admin_found}' has been removed from the administrators list.")
        else:
            self.safe_reply(connection, event, f"'{admin_to_remove}' is not in the administrators list.")
        return True

    def _cmd_join(self, connection, event, username, room):
        self.bot.connection.join(room)
        self.safe_reply(connection, event, f"Joined {room}.")
        return True

    def _cmd_part(self, connection, event, username, room, msg):
        if room in self.bot.joined_channels:
            self.bot.connection.part(room, msg or "Leaving per request.")
            self.safe_reply(connection, event, f"Left {room}.")
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
            "!admin load <module> - Load a module by name.",
            "!admin unload <module> - Unload a module by name.",
            "!admin modules - List all currently loaded modules.",
            "!admin blacklist <module.py> - Blacklist and unload a module.",
            "!admin unblacklist <module.py> - Unblacklist a module.",
            "!admin on|off <module> [#channel] - Enable/disable a module in a channel.",
            "!admin get <module.setting.path> [#channel] - View a config value.",
            "!admin set <module.setting.path> <value> [#channel|global] - Set a config value.",
            "!admin addadmin|deladmin <nick> - Add or remove an administrator.",
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

