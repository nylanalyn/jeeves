"""
Centralized state management utilities.
Eliminates duplicate state operations across modules.
"""

import json
import os
from typing import Any, Dict, Optional
from pathlib import Path

from .exception_utils import (
    StateException,
    safe_file_operation,
    log_module_event
)


class StateManager:
    """Centralized state management with standardized file operations."""
    
    def __init__(self, state_dir: str = "config"):
        """Initialize state manager.
        
        Args:
            state_dir: Directory for state files
        """
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(exist_ok=True)
    
    @safe_file_operation()
    def load_state(self, filename: str, default: Optional[Dict] = None) -> Dict[str, Any]:
        """Load state from JSON file.
        
        Args:
            filename: State filename (without .json extension)
            default: Default value if file doesn't exist
            
        Returns:
            Loaded state dictionary
        """
        file_path = self.state_dir / f"{filename}.json"
        
        if not file_path.exists():
            log_module_event("state_manager", "state_file_not_found", {
                "filename": filename,
                "using_default": default is not None
            })
            return default or {}
        
        with open(file_path, 'r', encoding='utf-8') as f:
            state = json.load(f)
        
        log_module_event("state_manager", "state_loaded", {
            "filename": filename,
            "size": len(state)
        })
        
        return state
    
    @safe_file_operation()
    def save_state(self, filename: str, state: Dict[str, Any]) -> None:
        """Save state to JSON file.

        Args:
            filename: State filename (without .json extension)
            state: State dictionary to save
        """
        file_path = self.state_dir / f"{filename}.json"
        temp_path = file_path.with_suffix('.json.tmp')

        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

        # Create backup if file exists, then atomically replace
        if file_path.exists():
            backup_path = file_path.with_suffix('.json.bak')
            file_path.replace(backup_path)
        temp_path.replace(file_path)

        log_module_event("state_manager", "state_saved", {
            "filename": filename,
            "size": len(state)
        })
    
    @safe_file_operation()
    def update_state(self, filename: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update state with new values.
        
        Args:
            filename: State filename
            updates: Dictionary of updates to apply
            
        Returns:
            Updated state
        """
        current_state = self.load_state(filename, {})
        current_state.update(updates)
        self.save_state(filename, current_state)
        
        log_module_event("state_manager", "state_updated", {
            "filename": filename,
            "updates": len(updates)
        })
        
        return current_state
    
    def get_state_value(self, filename: str, key: str, default: Any = None) -> Any:
        """Get a specific value from state.
        
        Args:
            filename: State filename
            key: Key to retrieve
            default: Default value if key doesn't exist
            
        Returns:
            Value for the specified key
        """
        state = self.load_state(filename, {})
        return state.get(key, default)
    
    def set_state_value(self, filename: str, key: str, value: Any) -> None:
        """Set a specific value in state.
        
        Args:
            filename: State filename
            key: Key to set
            value: Value to set
        """
        self.update_state(filename, {key: value})


def create_state_manager(state_dir: str = "config") -> StateManager:
    """Create a state manager with the specified directory."""
    return StateManager(state_dir=state_dir)