"""
Centralized admin validation utilities.
Eliminates duplicate admin permission checks across modules.
"""

from typing import List, Optional, Union

from .exception_utils import (
    PermissionException,
    log_security_event,
    log_module_event
)


class AdminValidator:
    """Centralized admin validation with standardized permission checks."""
    
    def __init__(self, admin_users: Optional[List[str]] = None):
        """Initialize admin validator.
        
        Args:
            admin_users: List of admin usernames
        """
        self.admin_users = admin_users or []
    
    def is_admin(self, username: str) -> bool:
        """Check if user is an admin.
        
        Args:
            username: Username to check
            
        Returns:
            True if user is admin, False otherwise
        """
        is_admin = username.lower() in [user.lower() for user in self.admin_users]
        
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


def create_admin_validator(admin_users: List[str]) -> AdminValidator:
    """Create an admin validator with the specified admin users."""
    return AdminValidator(admin_users=admin_users)