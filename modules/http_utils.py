"""
Centralized HTTP client utilities for API requests.
Eliminates duplicate HTTP request patterns across modules.
"""

import requests
import logging
from typing import Optional, Dict, Any, Union
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .exception_utils import (
    ExternalAPIException,
    safe_api_call_decorator,
    log_module_event,
    log_security_event
)


# Sensitive parameter keys that should be redacted in logs
SENSITIVE_KEYS = {
    "api_key", "apikey", "token", "access_token", "password",
    "secret", "auth", "authorization", "client_secret",
    "private_key", "session", "sessionid", "cookie"
}


def sanitize_params(params: Any) -> Any:
    """Sanitize parameters by redacting sensitive values.

    Recursively processes dictionaries and lists to replace sensitive
    parameter values with "<REDACTED>" to prevent logging secrets.

    Args:
        params: Parameters to sanitize (dict, list, or primitive)

    Returns:
        Sanitized copy of parameters with sensitive values redacted
    """
    if params is None:
        return None

    if isinstance(params, dict):
        sanitized = {}
        for key, value in params.items():
            # Check if key matches any sensitive pattern (case-insensitive)
            if key.lower() in SENSITIVE_KEYS:
                sanitized[key] = "<REDACTED>"
            else:
                # Recursively sanitize nested structures
                sanitized[key] = sanitize_params(value)
        return sanitized

    elif isinstance(params, list):
        return [sanitize_params(item) for item in params]

    else:
        # Primitive types returned as-is
        return params


class HTTPClient:
    """Centralized HTTP client with standardized error handling and retry logic."""
    
    def __init__(self, timeout: int = 30, max_retries: int = 3):
        """Initialize HTTP client with configuration.
        
        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for failed requests
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = self._create_session()
    
    def _create_session(self) -> requests.Session:
        """Create a requests session with retry strategy."""
        session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=self.max_retries,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"],
            backoff_factor=1
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # Set default headers
        session.headers.update({
            'User-Agent': 'JeevesBot/1.0',
            'Accept': 'application/json'
        })
        
        return session
    
    @safe_api_call_decorator()
    def get_json(self, url: str, params: Optional[Dict] = None,
                headers: Optional[Dict] = None) -> Dict[str, Any]:
        """Make GET request and return JSON response.
        
        Args:
            url: Target URL
            params: Query parameters
            headers: Additional headers
            
        Returns:
            JSON response as dictionary
            
        Raises:
            ExternalAPIException: On API errors
        """
        log_module_event("http_client", "api_request", {
            "url": url,
            "method": "GET",
            "params": sanitize_params(params)
        })
        
        response = self.session.get(
            url, 
            params=params, 
            headers=headers, 
            timeout=self.timeout
        )
        response.raise_for_status()
        
        return response.json()
    
    @safe_api_call_decorator()
    def get_text(self, url: str, params: Optional[Dict] = None,
                headers: Optional[Dict] = None) -> str:
        """Make GET request and return text response.
        
        Args:
            url: Target URL
            params: Query parameters
            headers: Additional headers
            
        Returns:
            Response text
            
        Raises:
            ExternalAPIException: On API errors
        """
        log_module_event("http_client", "api_request", {
            "url": url,
            "method": "GET",
            "params": sanitize_params(params)
        })
        
        response = self.session.get(
            url,
            params=params,
            headers=headers,
            timeout=self.timeout
        )
        response.raise_for_status()
        
        return response.text
    
    def close(self):
        """Close the HTTP session."""
        if self.session:
            self.session.close()


# Global HTTP client instance for shared use
_http_client = HTTPClient()


def get_http_client() -> HTTPClient:
    """Get the shared HTTP client instance."""
    return _http_client


def create_http_client(timeout: int = 30, max_retries: int = 3) -> HTTPClient:
    """Create a new HTTP client with custom configuration."""
    return HTTPClient(timeout=timeout, max_retries=max_retries)