#!/usr/bin/env python3
"""
Migration script to split state.json into multiple files.
- state.json: Core config and non-critical module data
- games.json: Game state (quest, hunt, bell, adventure, roadtrip)
- users.json: User profiles, locations, memos
- stats.json: Statistics and tracking data (coffee, courtesy)
"""

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_DIR = ROOT / "config"
STATE_PATH = CONFIG_DIR / "state.json"

# Module categorization
MODULE_MAPPING = {
    # Game modules
    'quest': 'games',
    'hunt': 'games',
    'bell': 'games',
    'adventure': 'games',
    'roadtrip': 'games',
    # User data modules
    'users': 'users',
    'weather': 'users',
    'memos': 'users',
    'profiles': 'users',
    # Stats modules
    'coffee': 'stats',
    'courtesy': 'stats',
    'leveling': 'stats',
}

def migrate():
    print("[migrate] Starting state file migration...")

    # Backup original state.json
    if STATE_PATH.exists():
        backup_path = STATE_PATH.with_name("state.json.pre-migration-backup")
        shutil.copy2(STATE_PATH, backup_path)
        print(f"[migrate] Created backup at: {backup_path}")
    else:
        print("[migrate] No existing state.json found, nothing to migrate")
        return

    # Load original state
    with open(STATE_PATH, 'r') as f:
        original_state = json.load(f)

    # Initialize new state structures
    new_states = {
        'state': {},
        'games': {},
        'users': {},
        'stats': {},
    }

    # Extract top-level state data (joined_channels, etc.)
    for key, value in original_state.items():
        if key != 'modules':
            new_states['state'][key] = value

    # Process modules
    modules = original_state.get('modules', {})

    # Config always goes to state.json
    if 'config' in modules:
        new_states['state'].setdefault('modules', {})['config'] = modules['config']
        print("[migrate] Moved 'config' to state.json")

    # Split other modules by category
    for module_name, module_data in modules.items():
        if module_name == 'config':
            continue  # Already handled

        file_type = MODULE_MAPPING.get(module_name, 'state')
        new_states[file_type].setdefault('modules', {})[module_name] = module_data
        print(f"[migrate] Moved '{module_name}' to {file_type}.json")

    # Write new state files
    for file_type, data in new_states.items():
        output_path = CONFIG_DIR / f"{file_type}.json"
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=4)
        print(f"[migrate] Wrote {output_path}")

    print("[migrate] Migration complete!")
    print("[migrate] Original state.json has been preserved as a backup.")
    print("[migrate] You can now restart the bot with the new multi-file state system.")

if __name__ == "__main__":
    migrate()
