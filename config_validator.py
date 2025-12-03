#!/usr/bin/env python3
"""
Configuration validation and management system for Jeeves IRC bot.

This module provides comprehensive configuration validation, environment variable support,
and error handling to prevent runtime failures and improve security.
"""

import os
import re
import sys
import yaml
import logging
from typing import Dict, Any, List, Optional, Tuple, Union
from pathlib import Path
from dataclasses import dataclass
from enum import Enum


class ValidationSeverity(Enum):
    """Severity levels for validation issues."""
    ERROR = "error"      # Critical issue that prevents startup
    WARNING = "warning"  # Issue that should be fixed but won't prevent startup
    INFO = "info"        # Informational message


@dataclass
class ValidationIssue:
    """Represents a configuration validation issue."""
    severity: ValidationSeverity
    path: str            # Configuration path (e.g., "connection.port")
    message: str         # Human-readable error message
    current_value: Any   # Current invalid value
    expected: str        # Expected value/range description


class ConfigValidator:
    """Comprehensive configuration validator for Jeeves bot."""

    def __init__(self, config_path: Path, logger: Optional[logging.Logger] = None):
        self.config_path = config_path
        self.logger = logger or logging.getLogger(__name__)
        self.issues: List[ValidationIssue] = []

    def validate_and_load(self) -> Tuple[Optional[Dict[str, Any]], List[ValidationIssue]]:
        """
        Validate and load configuration with environment variable substitution.

        Returns:
            Tuple of (config_dict, validation_issues)
            config_dict is None if critical errors are found
        """
        self.issues = []

        # Load raw configuration
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
        except FileNotFoundError:
            self.issues.append(ValidationIssue(
                ValidationSeverity.ERROR,
                "config_file",
                f"Configuration file not found: {self.config_path}",
                None,
                "Create config.yaml from config.yaml.default"
            ))
            return None, self.issues
        except yaml.YAMLError as e:
            self.issues.append(ValidationIssue(
                ValidationSeverity.ERROR,
                "config_file",
                f"Invalid YAML syntax: {e}",
                None,
                "Fix YAML syntax errors"
            ))
            return None, self.issues
        except Exception as e:
            self.issues.append(ValidationIssue(
                ValidationSeverity.ERROR,
                "config_file",
                f"Error reading config file: {e}",
                None,
                "Check file permissions and format"
            ))
            return None, self.issues

        # Apply environment variable substitution
        config = self._substitute_env_vars(config)

        # Validate all sections
        self._validate_core_config(config)
        self._validate_connection_config(config)
        self._validate_api_keys(config)
        self._validate_module_configs(config)

        # Check for critical errors
        critical_errors = [issue for issue in self.issues if issue.severity == ValidationSeverity.ERROR]
        if critical_errors:
            self.logger.error("Critical configuration errors found:")
            for issue in critical_errors:
                self.logger.error(f"  {issue.path}: {issue.message}")
            return None, self.issues

        return config, self.issues

    def _substitute_env_vars(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Substitute environment variables in configuration values."""
        def substitute_recursive(obj, path=""):
            if isinstance(obj, dict):
                return {k: substitute_recursive(v, f"{path}.{k}" if path else k) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [substitute_recursive(item, f"{path}[]") for item in obj]
            elif isinstance(obj, str):
                return self._substitute_env_string(obj, path)
            else:
                return obj

        return substitute_recursive(config)

    def _substitute_env_string(self, value: str, path: str) -> str:
        """Substitute environment variables in a string value."""
        # Skip substitution for bcrypt hashes (they contain $ signs)
        if path == "core.super_admin_password_hash":
            return value

        # Pattern for ${VAR_NAME} or $VAR_NAME
        pattern = r'\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)'

        def replace_var(match):
            var_name = match.group(1) or match.group(2)
            env_value = os.getenv(var_name)

            if env_value is None:
                # Check if this looks like a sensitive field that should use env vars
                if any(keyword in path.lower() for keyword in ['key', 'pass', 'secret', 'token']):
                    self.issues.append(ValidationIssue(
                        ValidationSeverity.WARNING,
                        path,
                        f"Environment variable ${var_name} not set",
                        match.group(0),
                        f"Set environment variable {var_name}"
                    ))
                else:
                    self.issues.append(ValidationIssue(
                        ValidationSeverity.INFO,
                        path,
                        f"Environment variable ${var_name} not set, using empty string",
                        match.group(0),
                        f"Set environment variable {var_name} or use static value"
                    ))
                return ""

            return env_value

        return re.sub(pattern, replace_var, value)

    def _validate_core_config(self, config: Dict[str, Any]) -> None:
        """Validate core configuration section."""
        core = config.get("core", {})

        # Validate admins
        admins = core.get("admins", [])
        if not isinstance(admins, list):
            self.issues.append(ValidationIssue(
                ValidationSeverity.ERROR,
                "core.admins",
                "Admins must be a list",
                admins,
                "admins: ['YourNick']"
            ))
        elif not admins:
            self.issues.append(ValidationIssue(
                ValidationSeverity.WARNING,
                "core.admins",
                "No administrators configured",
                admins,
                "Add at least one admin nickname"
            ))
        else:
            for i, admin in enumerate(admins):
                if not isinstance(admin, str) or not admin.strip():
                    self.issues.append(ValidationIssue(
                        ValidationSeverity.ERROR,
                        f"core.admins[{i}]",
                        "Admin names must be non-empty strings",
                        admin,
                        "Use valid IRC nicknames"
                    ))

        # Validate module blacklist
        blacklist = core.get("module_blacklist", [])
        if not isinstance(blacklist, list):
            self.issues.append(ValidationIssue(
                ValidationSeverity.ERROR,
                "core.module_blacklist",
                "Module blacklist must be a list",
                blacklist,
                "module_blacklist: ['module.py']"
            ))

        # Validate name pattern
        name_pattern = core.get("name_pattern")
        if name_pattern:
            try:
                re.compile(name_pattern)
            except re.error as e:
                self.issues.append(ValidationIssue(
                    ValidationSeverity.ERROR,
                    "core.name_pattern",
                    f"Invalid regex pattern: {e}",
                    name_pattern,
                    "Use valid Python regex"
                ))

        # Validate debug settings
        debug_mode = core.get("debug_mode_on_startup", False)
        if not isinstance(debug_mode, bool):
            self.issues.append(ValidationIssue(
                ValidationSeverity.ERROR,
                "core.debug_mode_on_startup",
                "Debug mode must be boolean",
                debug_mode,
                "debug_mode_on_startup: true/false"
            ))

        debug_log_file = core.get("debug_log_file", "debug.log")
        if not isinstance(debug_log_file, str) or not debug_log_file.strip():
            self.issues.append(ValidationIssue(
                ValidationSeverity.ERROR,
                "core.debug_log_file",
                "Debug log file must be a non-empty string",
                debug_log_file,
                "debug_log_file: 'debug.log'"
            ))

    def _validate_connection_config(self, config: Dict[str, Any]) -> None:
        """Validate IRC connection configuration."""
        conn = config.get("connection", {})

        # Validate server
        server = conn.get("server")
        if not server or not isinstance(server, str) or not server.strip():
            self.issues.append(ValidationIssue(
                ValidationSeverity.ERROR,
                "connection.server",
                "Server must be a non-empty string",
                server,
                "server: 'irc.libera.chat'"
            ))

        # Validate port
        port = conn.get("port")
        if not isinstance(port, int) or not (1 <= port <= 65535):
            self.issues.append(ValidationIssue(
                ValidationSeverity.ERROR,
                "connection.port",
                "Port must be an integer between 1 and 65535",
                port,
                "port: 6697"
            ))

        # Validate nick
        nick = conn.get("nick")
        if not nick or not isinstance(nick, str) or not nick.strip():
            self.issues.append(ValidationIssue(
                ValidationSeverity.ERROR,
                "connection.nick",
                "Nick must be a non-empty string",
                nick,
                "nick: 'YourBotName'"
            ))
        else:
            # Check nick validity (basic IRC nick validation)
            if not re.match(r'^[a-zA-Z\[\]\\`_^{|}][a-zA-Z0-9\[\]\\`_^{|}]*$', nick):
                self.issues.append(ValidationIssue(
                    ValidationSeverity.WARNING,
                    "connection.nick",
                    "Nick may contain invalid IRC characters",
                    nick,
                    "Use valid IRC nickname (letters, numbers, and []\\`_^{|})"
                ))
            if len(nick) > 30:  # IRC nick limit
                self.issues.append(ValidationIssue(
                    ValidationSeverity.ERROR,
                    "connection.nick",
                    "Nick too long (max 30 characters)",
                    nick,
                    "Use shorter nickname"
                ))

        # Validate channel (support both old 'channel' and new 'main_channel' formats)
        main_channel = conn.get("main_channel") or conn.get("channel")
        if not main_channel or not isinstance(main_channel, str) or not main_channel.strip():
            self.issues.append(ValidationIssue(
                ValidationSeverity.ERROR,
                "connection.main_channel",
                "Main channel must be a non-empty string",
                main_channel,
                "main_channel: '#your-channel' (or use legacy 'channel' key)"
            ))
        elif not main_channel.startswith('#'):
            self.issues.append(ValidationIssue(
                ValidationSeverity.WARNING,
                "connection.main_channel",
                "Channel should start with #",
                main_channel,
                "Use '#channelname' format"
            ))

        # Validate additional channels (if present)
        additional_channels = conn.get("additional_channels", [])
        if additional_channels:
            if not isinstance(additional_channels, list):
                self.issues.append(ValidationIssue(
                    ValidationSeverity.ERROR,
                    "connection.additional_channels",
                    "Additional channels must be a list",
                    type(additional_channels).__name__,
                    "additional_channels: ['#channel1', '#channel2']"
                ))
            else:
                for i, channel in enumerate(additional_channels):
                    if not isinstance(channel, str) or not channel.strip():
                        self.issues.append(ValidationIssue(
                            ValidationSeverity.ERROR,
                            f"connection.additional_channels[{i}]",
                            "Channel must be a non-empty string",
                            channel,
                            "Use '#channelname' format"
                        ))
                    elif not channel.startswith('#'):
                        self.issues.append(ValidationIssue(
                            ValidationSeverity.WARNING,
                            f"connection.additional_channels[{i}]",
                            "Channel should start with #",
                            channel,
                            "Use '#channelname' format"
                        ))

        # Validate nickserv password (can be empty)
        nickserv_pass = conn.get("nickserv_pass", "")
        if nickserv_pass and not isinstance(nickserv_pass, str):
            self.issues.append(ValidationIssue(
                ValidationSeverity.ERROR,
                "connection.nickserv_pass",
                "NickServ password must be a string",
                type(nickserv_pass).__name__,
                "nickserv_pass: 'your_password' or ''"
            ))

    def _validate_api_keys(self, config: Dict[str, Any]) -> None:
        """Validate API keys configuration."""
        api_keys = config.get("api_keys", {})
        if not isinstance(api_keys, dict):
            self.issues.append(ValidationIssue(
                ValidationSeverity.ERROR,
                "api_keys",
                "API keys must be a dictionary",
                type(api_keys).__name__,
                "api_keys: { key: 'value' }"
            ))
            return

        # Define expected API key formats
        key_formats = {
            "giphy": r"^[a-zA-Z0-9_-]{32}$",  # Giphy API keys are 32 chars
            "youtube": r"^AIza[0-9A-Za-z_-]{35}$",  # YouTube API keys start with AIza
            "openai_api_key": r"^sk-[a-zA-Z0-9]{48}$",  # OpenAI API keys format
            "shlink_key": r"^[a-zA-Z0-9_-]{20,}$",  # Shlink keys vary in length
            "pirateweather": r"^[a-zA-Z0-9_-]{32}$",  # PirateWeather API keys
            "deepl_api_key": r"^[a-zA-Z0-9_-]{36}$",  # DeepL API keys are 36 chars
        }

        for key_name, key_value in api_keys.items():
            if not isinstance(key_value, str):
                self.issues.append(ValidationIssue(
                    ValidationSeverity.ERROR,
                    f"api_keys.{key_name}",
                    f"API key must be a string",
                    type(key_value).__name__,
                    f"{key_name}: 'your_api_key'"
                ))
                continue

            # Check if it looks like a placeholder/default value
            placeholder_patterns = [
                r"your.*key.*",
                r"example.*",
                r"test.*",
                r"placeholder.*",
                r"xxx+",
                r"---+"
            ]

            for pattern in placeholder_patterns:
                if re.search(pattern, key_value, re.IGNORECASE):
                    self.issues.append(ValidationIssue(
                        ValidationSeverity.WARNING,
                        f"api_keys.{key_name}",
                        f"API key appears to be a placeholder",
                        key_value[:10] + "...",
                        f"Replace with actual {key_name} API key or use environment variable"
                    ))
                    break
            else:
                # Validate key format if we have a pattern
                if key_name in key_formats:
                    pattern = key_formats[key_name]
                    if not re.match(pattern, key_value):
                        self.issues.append(ValidationIssue(
                            ValidationSeverity.WARNING,
                            f"api_keys.{key_name}",
                            f"API key format may be invalid",
                            key_value[:10] + "...",
                            f"Check {key_name} API key format"
                        ))

    def _validate_module_configs(self, config: Dict[str, Any]) -> None:
        """Validate module-specific configurations."""
        # Get list of available modules for validation
        modules_dir = Path(__file__).parent / "modules"
        if not modules_dir.exists():
            return

        # Common validation patterns
        numeric_validations = {
            "cooldown_seconds": (0, 86400),      # 0 to 24 hours
            "vote_window_seconds": (1, 3600),    # 1 second to 1 hour
            "response_window_seconds": (1, 300), # 1 second to 5 minutes
            "min_hours_between_rings": (0, 168), # 0 to 1 week
            "max_hours_between_rings": (1, 168), # 1 hour to 1 week
        }

        probability_validations = {
            "response_rate": (0.0, 1.0),
            "item_find_chance": (0.0, 1.0),
            "reliability_percent": (0, 100),
        }

        # Validate each module section
        for section_name, section_config in config.items():
            if section_name in ["core", "connection", "api_keys"]:
                continue  # Already validated

            if not isinstance(section_config, dict):
                self.issues.append(ValidationIssue(
                    ValidationSeverity.WARNING,
                    section_name,
                    "Module configuration must be a dictionary",
                    type(section_config).__name__,
                    f"{section_name}: {{ setting: value }}"
                ))
                continue

            # Validate numeric values
            for key, (min_val, max_val) in numeric_validations.items():
                if key in section_config:
                    value = section_config[key]
                    if not isinstance(value, (int, float)):
                        self.issues.append(ValidationIssue(
                            ValidationSeverity.ERROR,
                            f"{section_name}.{key}",
                            f"Must be a number",
                            value,
                            f"{key}: {min_val}-{max_val}"
                        ))
                    elif not (min_val <= value <= max_val):
                        self.issues.append(ValidationIssue(
                            ValidationSeverity.ERROR,
                            f"{section_name}.{key}",
                            f"Must be between {min_val} and {max_val}",
                            value,
                            f"{key}: {min_val}-{max_val}"
                        ))

            # Validate probability values
            for key, (min_val, max_val) in probability_validations.items():
                if key in section_config:
                    value = section_config[key]
                    if not isinstance(value, (int, float)):
                        self.issues.append(ValidationIssue(
                            ValidationSeverity.ERROR,
                            f"{section_name}.{key}",
                            f"Must be a number",
                            value,
                            f"{key}: {min_val}-{max_val}"
                        ))
                    elif not (min_val <= value <= max_val):
                        self.issues.append(ValidationIssue(
                            ValidationSeverity.ERROR,
                            f"{section_name}.{key}",
                            f"Must be between {min_val} and {max_val}",
                            value,
                            f"{key}: {min_val}-{max_val}"
                        ))

            # Validate channel lists
            for channel_key in ["allowed_channels", "blocked_channels"]:
                if channel_key in section_config:
                    channels = section_config[channel_key]
                    if not isinstance(channels, list):
                        self.issues.append(ValidationIssue(
                            ValidationSeverity.ERROR,
                            f"{section_name}.{channel_key}",
                            "Must be a list of channel names",
                            type(channels).__name__,
                            f"{channel_key}: ['#channel1', '#channel2']"
                        ))
                    else:
                        for i, channel in enumerate(channels):
                            if not isinstance(channel, str) or not channel.startswith('#'):
                                self.issues.append(ValidationIssue(
                                    ValidationSeverity.WARNING,
                                    f"{section_name}.{channel_key}[{i}]",
                                    "Channel names should start with #",
                                    channel,
                                    "Use '#channelname' format"
                                ))

    def print_validation_report(self) -> None:
        """Print a human-readable validation report."""
        if not self.issues:
            print("✅ Configuration validation passed with no issues!")
            return

        # Group issues by severity
        errors = [i for i in self.issues if i.severity == ValidationSeverity.ERROR]
        warnings = [i for i in self.issues if i.severity == ValidationSeverity.WARNING]
        infos = [i for i in self.issues if i.severity == ValidationSeverity.INFO]

        print(f"\n🔍 **Configuration Validation Report**")
        print("=" * 50)

        if errors:
            print(f"\n❌ **CRITICAL ERRORS ({len(errors)})**:")
            print("These issues must be fixed before the bot can start:")
            for issue in errors:
                print(f"  • {issue.path}: {issue.message}")
                print(f"    Current: {issue.current_value}")
                print(f"    Expected: {issue.expected}")

        if warnings:
            print(f"\n⚠️ **WARNINGS ({len(warnings)})**:")
            print("These issues should be fixed but won't prevent startup:")
            for issue in warnings:
                print(f"  • {issue.path}: {issue.message}")
                if issue.current_value is not None:
                    print(f"    Current: {issue.current_value}")
                print(f"    Expected: {issue.expected}")

        if infos:
            print(f"\nℹ️ **INFO ({len(infos)})**:")
            print("Informational messages:")
            for issue in infos:
                print(f"  • {issue.path}: {issue.message}")

        print("\n" + "=" * 50)


def load_and_validate_config(config_path: Path, logger: Optional[logging.Logger] = None) -> Tuple[Optional[Dict[str, Any]], bool]:
    """
    Convenience function to load and validate configuration.

    Returns:
        Tuple of (config_dict, success)
        success is False if critical errors were found
    """
    validator = ConfigValidator(config_path, logger)
    config, issues = validator.validate_and_load()

    # Always print the validation report
    validator.print_validation_report()

    success = config is not None
    return config, success


if __name__ == "__main__":
    # Command line interface for configuration validation
    import argparse

    parser = argparse.ArgumentParser(description="Validate Jeeves bot configuration")
    parser.add_argument("config", nargs="?", default="config/config.yaml",
                       help="Path to configuration file (default: config/config.yaml)")
    parser.add_argument("-v", "--verbose", action="store_true",
                       help="Enable verbose logging")

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format='%(levelname)s: %(message)s')

    # Validate configuration
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = Path(__file__).parent / config_path

    config, success = load_and_validate_config(config_path)

    if not success:
        sys.exit(1)
    else:
        print("\n🎉 Configuration is valid and ready to use!")