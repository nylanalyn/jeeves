"""Centralized admin validation utilities."""

from typing import Any, Dict, List, Optional

from .exception_utils import (
    PermissionException,
    log_security_event,
    log_module_event
)


class AdminValidator:
    """Centralized admin validation with standardized permission checks.

    Prefer passing `bot` when available so validation uses the same hostname-aware
    logic as `Jeeves.is_admin()`. Passing a config dict or list still works for
    lightweight tests and non-IRC contexts.
    """
    
    def __init__(
        self,
        admin_users: Optional[List[str]] = None,
        config: Optional[Dict[str, Any]] = None,
        bot: Optional[Any] = None,
    ):
        """Initialize admin validator.
        
        Args:
            admin_users: List of admin usernames
            config: Jeeves config dict using `core.admins`
            bot: Optional Jeeves instance for full admin checks
        """
        self.bot = bot
        if admin_users is None and config:
            admin_users = config.get("core", {}).get("admins", [])
        self.admin_users = [user for user in (admin_users or []) if isinstance(user, str)]

    @staticmethod
    def _nick_from_source(username_or_source: str) -> str:
        return str(username_or_source).split("!", 1)[0].strip()
    
    def is_admin(self, username: str) -> bool:
        """Check if user is an admin.
        
        Args:
            username: Username to check
            
        Returns:
            True if user is admin, False otherwise
        """
        if self.bot is not None and "!" in str(username):
            is_admin = bool(self.bot.is_admin(username))
        else:
            nick = self._nick_from_source(username).lower()
            admin_nicks = {user.strip().lower() for user in self.admin_users}
            is_admin = nick in admin_nicks
        
        if is_admin:
            log_module_event("admin_validator", "admin_check", {
                "username": username,
                "result": "authorized"
            })
        else:
            log_module_event("admin_validator", "admin_check", {
                "username": username,
                "result": "denied"
            })
        
        return is_admin
    
    def require_admin(self, username: str) -> None:
        """Require admin permissions, raise exception if not admin.
        
        Args:
            username: Username to check
            
        Raises:
            PermissionException: If user is not admin
        """
        if not self.is_admin(username):
            log_security_event("admin_validator", "unauthorized_access", {
                "username": username,
                "action": "admin_command"
            })
            raise PermissionException("Insufficient permissions for this command")
    
    def validate_admin_command(self, username: str, command: str) -> None:
        """Validate admin command with logging.
        
        Args:
            username: Username executing command
            command: Command being executed
            
        Raises:
            PermissionException: If user is not admin
        """
        log_module_event("admin_validator", "admin_command_attempt", {
            "username": username,
            "command": command
        })
        
        self.require_admin(username)
        
        log_module_event("admin_validator", "admin_command_executed", {
            "username": username,
            "command": command
        })


def create_admin_validator(
    admin_users: Optional[List[str]] = None,
    config: Optional[Dict[str, Any]] = None,
    bot: Optional[Any] = None,
) -> AdminValidator:
    """Create an admin validator with the specified admin users."""
    return AdminValidator(admin_users=admin_users, config=config, bot=bot)
