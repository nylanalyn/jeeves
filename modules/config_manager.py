"""Centralized configuration helpers for Jeeves' current config layout."""

from typing import Any, Dict, List, Optional

from .exception_utils import (
    ConfigurationException,
    log_module_event
)

# Sentinel value to detect missing configuration keys
_MISSING = object()


class ConfigManager:
    """Centralized configuration management with standardized access patterns."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize configuration manager.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
    
    def get_api_key(self, service: str, required: bool = True) -> Optional[str]:
        """Get API key for a service.
        
        Args:
            service: Service name (e.g., 'youtube', 'weather')
            required: Whether the key is required
            
        Returns:
            API key or None if not found and not required
            
        Raises:
            ConfigurationException: If key is required but not found
        """
        key_path = f"api_keys.{service}"
        key_value = self._get_nested_value(key_path)
        
        if key_value is not None and key_value != "":
            log_module_event("config_manager", "api_key_accessed", {
                "service": service,
                "key_available": True
            })
            return key_value
        
        if required:
            log_module_event("config_manager", "api_key_missing", {
                "service": service,
                "required": True
            })
            raise ConfigurationException(f"API key for {service} is not configured")
        
        log_module_event("config_manager", "api_key_missing", {
            "service": service,
            "required": False
        })
        return None
    
    def get_service_config(self, service: str) -> Dict[str, Any]:
        """Get configuration for a specific service.
        
        Args:
            service: Service name
            
        Returns:
            Service configuration dictionary
        """
        service_config = self._get_nested_value(f"services.{service}", {})
        
        log_module_event("config_manager", "service_config_accessed", {
            "service": service,
            "config_keys": len(service_config)
        })
        
        return service_config
    
    def get_module_config(self, module: str) -> Dict[str, Any]:
        """Get configuration for a specific module.
        
        Args:
            module: Module name
            
        Returns:
            Module configuration dictionary
        """
        module_config = self._get_nested_value(module, _MISSING)
        found = module_config is not _MISSING
        if not found:
            # Compatibility with the older nested `modules.<name>` layout.
            module_config = self._get_nested_value(f"modules.{module}", {})
            found = bool(module_config)
        if not isinstance(module_config, dict):
            module_config = {}
        
        log_module_event("config_manager", "module_config_accessed", {
            "module": module,
            "config_keys": len(module_config),
            "found": found,
        })
        
        return module_config
    
    def get_connection_config(self) -> Dict[str, Any]:
        """Get IRC connection configuration from the modern `connection` section."""
        connection_config = self._get_nested_value("connection", {})
        if not isinstance(connection_config, dict):
            connection_config = {}

        log_module_event("config_manager", "connection_config_accessed", {
            "config_keys": len(connection_config)
        })

        return connection_config

    def get_irc_config(self) -> Dict[str, Any]:
        """Get IRC configuration.
        
        Returns:
            IRC configuration dictionary
        """
        irc_config = self.get_connection_config()
        if not irc_config:
            legacy_irc_config = self._get_nested_value("irc", {})
            irc_config = legacy_irc_config if isinstance(legacy_irc_config, dict) else {}
        
        log_module_event("config_manager", "irc_config_accessed", {
            "config_keys": len(irc_config)
        })
        
        return irc_config
    
    def get_core_config(self) -> Dict[str, Any]:
        """Get core bot configuration."""
        core_config = self._get_nested_value("core", {})
        if not isinstance(core_config, dict):
            core_config = {}

        log_module_event("config_manager", "core_config_accessed", {
            "config_keys": len(core_config)
        })

        return core_config

    def get_admin_users(self) -> List[str]:
        """Get list of admin users.
        
        Returns:
            List of admin usernames
        """
        admin_users = self._get_nested_value("core.admins", _MISSING)
        if admin_users is _MISSING:
            admin_users = self._get_nested_value("irc.admins", [])
        if not isinstance(admin_users, list):
            admin_users = []
        
        log_module_event("config_manager", "admin_users_accessed", {
            "count": len(admin_users)
        })
        
        return admin_users
    
    def get_value(self, key_path: str, default: Any = None) -> Any:
        """Get configuration value by dot-separated path.

        Args:
            key_path: Dot-separated path to configuration value
            default: Default value if not found

        Returns:
            Configuration value
        """
        value = self._get_nested_value(key_path, _MISSING)
        found = value is not _MISSING

        if value is _MISSING:
            value = default

        log_module_event("config_manager", "config_value_accessed", {
            "key_path": key_path,
            "found": found
        })

        return value
    
    def _get_nested_value(self, key_path: str, default: Any = None) -> Any:
        """Get nested configuration value using dot notation.
        
        Args:
            key_path: Dot-separated path to configuration value
            default: Default value if not found
            
        Returns:
            Configuration value
        """
        keys = key_path.split('.')
        current = self.config
        
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        
        return current


def create_config_manager(config: Dict[str, Any]) -> ConfigManager:
    """Create a configuration manager with the specified configuration."""
    return ConfigManager(config=config)
