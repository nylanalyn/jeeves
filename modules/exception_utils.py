"""
Standardized exception handling utilities for Jeeves modules.

This module provides consistent exception handling patterns, logging,
and user-friendly error messages across all modules.
"""

import sys
import traceback
import logging
from typing import Optional, Callable, Any, Type, Tuple, Union
from functools import wraps


class JeevesException(Exception):
    """Base exception class for Jeeves-specific errors."""
    def __init__(self, message: str, user_message: Optional[str] = None):
        super().__init__(message)
        self.user_message = user_message or "An unexpected error occurred."


class ModuleException(JeevesException):
    """Exception raised by module operations."""
    pass


class ConfigurationException(JeevesException):
    """Exception raised for configuration errors."""
    pass


class ExternalAPIException(JeevesException):
    """Exception raised for external API failures."""
    pass


class UserInputException(JeevesException):
    """Exception raised for invalid user input."""
    pass


class StateException(JeevesException):
    """Exception raised for state management errors."""
    pass


class PermissionException(JeevesException):
    """Exception raised for permission/authorization errors."""
    pass


class NetworkException(JeevesException):
    """Exception raised for network-related failures."""
    pass


def safe_execute(
    func: Callable,
    *args,
    error_message: str = "An error occurred",
    user_message: Optional[str] = None,
    log_exception: bool = True,
    reraise: bool = False,
    exception_types: Tuple[Type[Exception], ...] = (Exception,),
    **kwargs
) -> Tuple[Any, Optional[str]]:
    """
    Safely execute a function with standardized exception handling.
    
    Args:
        func: Function to execute
        error_message: Internal error message for logging
        user_message: User-friendly error message to return on failure
        log_exception: Whether to log the exception
        reraise: Whether to re-raise the exception after handling
        exception_types: Tuple of exception types to catch
        *args, **kwargs: Arguments to pass to the function
        
    Returns:
        Tuple of (result, user_message) on success or (None, user_message) on handled failure.
        On success, user_message is None. On failure, user_message contains the error message.
    """
    try:
        return func(*args, **kwargs), None
    except exception_types as e:
        if log_exception:
            # Get the calling module name from the stack
            frame = sys._getframe(1)
            module_name = frame.f_globals.get('__name__', 'unknown')
            
            # Log with appropriate level based on exception type
            if isinstance(e, (UserInputException, ConfigurationException)):
                logging.warning(f"[{module_name}] {error_message}: {e}")
            else:
                logging.error(f"[{module_name}] {error_message}: {e}")
                logging.debug(f"[{module_name}] Exception details:\n{traceback.format_exc()}")
        
        if reraise:
            raise
        return None, user_message or error_message


def handle_exceptions(
    error_message: str = "An error occurred",
    log_exception: bool = True,
    reraise: bool = False,
    exception_types: Tuple[Type[Exception], ...] = (Exception,)
):
    """
    Decorator for standardized exception handling in module methods.
    
    Args:
        error_message: Internal error message for logging
        user_message: User-friendly error message
        log_exception: Whether to log the exception
        reraise: Whether to re-raise the exception after handling
        exception_types: Tuple of exception types to catch
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # First argument is typically 'self' for instance methods
            self_obj = args[0] if args else None
            
            try:
                return func(*args, **kwargs)
            except exception_types as e:
                # Try to get bot instance for logging if available
                bot = getattr(self_obj, 'bot', None) if self_obj else None
                module_name = getattr(self_obj, 'name', func.__module__) if self_obj else func.__module__
                
                if log_exception:
                    # Use bot's log_debug if available, otherwise use standard logging
                    if bot and hasattr(bot, 'log_debug'):
                        if isinstance(e, (UserInputException, ConfigurationException)):
                            bot.log_debug(f"[{module_name}] {error_message}: {e}")
                        else:
                            bot.log_debug(f"[{module_name}] {error_message}: {e}")
                            # Log full traceback for non-user errors
                            bot.log_debug(f"[{module_name}] Exception details:\n{traceback.format_exc()}")
                    else:
                        # Fallback to standard logging
                        if isinstance(e, (UserInputException, ConfigurationException)):
                            logging.warning(f"[{module_name}] {error_message}: {e}")
                        else:
                            logging.error(f"[{module_name}] {error_message}: {e}")
                            logging.debug(f"[{module_name}] Exception details:\n{traceback.format_exc()}")
                
                if reraise:
                    raise
                
                # Return appropriate value based on function signature
                # For command handlers, return False to indicate failure
                if func.__name__.startswith('_cmd_'):
                    return False
                return None
        return wrapper
    return decorator


def safe_api_call(
    api_name: str = "external API",
    user_message: str = "The service is temporarily unavailable. Please try again later."
):
    """
    Decorator for safely calling external APIs with standardized error handling.
    
    Args:
        api_name: Name of the API for logging
        user_message: User-friendly error message
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Tuple[Any, Optional[str]]:
            return safe_execute(
                func,
                *args,
                error_message=f"{api_name} call failed",
                user_message=user_message,
                exception_types=(ExternalAPIException, ConnectionError, TimeoutError, ValueError),
                **kwargs
            )
        return wrapper
    return decorator


def safe_file_operation(
    operation: str = "file operation",
    user_message: str = "Unable to process the request due to a system error."
):
    """
    Decorator for safely performing file operations with standardized error handling.
    
    Args:
        operation: Description of the operation for logging
        user_message: User-friendly error message
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Tuple[Any, Optional[str]]:
            return safe_execute(
                func,
                *args,
                error_message=f"{operation} failed",
                user_message=user_message,
                exception_types=(IOError, OSError, PermissionError, FileNotFoundError),
                **kwargs
            )
        return wrapper
    return decorator


def validate_user_input(
    value: Any,
    validation_func: Callable[[Any], bool],
    error_message: str = "Invalid input provided",
    user_message: str = "The provided input is invalid. Please check your input and try again."
) -> bool:
    """
    Validate user input with standardized error handling.
    
    Args:
        value: Input value to validate
        validation_func: Function that returns True if input is valid
        error_message: Internal error message
        user_message: User-friendly error message
        
    Returns:
        True if input is valid, False otherwise
    """
    try:
        if not validation_func(value):
            raise UserInputException(error_message, user_message)
        return True
    except UserInputException as e:
        # Log the validation failure
        frame = sys._getframe(1)
        module_name = frame.f_globals.get('__name__', 'unknown')
        logging.warning(f"[{module_name}] {error_message}: {value}")
        return False


def log_module_event(module_name: str, event: str, details: Optional[dict] = None):
    """
    Standardized logging for module events.
    
    Args:
        module_name: Name of the module
        event: Description of the event
        details: Additional event details
    """
    details_str = f" - {details}" if details else ""
    logging.info(f"[{module_name}] {event}{details_str}")


def log_security_event(module_name: str, event: str, user: Optional[str] = None, details: Optional[dict] = None):
    """
    Standardized logging for security-related events.
    
    Args:
        module_name: Name of the module
        event: Description of the security event
        user: User involved in the event (if applicable)
        details: Additional event details
    """
    user_str = f" by {user}" if user else ""
    details_str = f" - {details}" if details else ""
    logging.warning(f"[SECURITY][{module_name}] {event}{user_str}{details_str}")