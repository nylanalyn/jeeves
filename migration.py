# migrate_to_uuids.py
# A one-time script to migrate from nickname-based state keys to persistent UUIDs.
import json
import uuid
import shutil
from pathlib import Path

# --- Configuration ---
# Ensure this script is in the same directory as jeeves.py
ROOT = Path(__file__).resolve().parent
CONFIG_DIR = ROOT / "config"
STATE_PATH = CONFIG_DIR / "state.json"

# List of modules and their state keys that are dictionaries keyed by lowercase nicks
# The script will convert these to be keyed by UUIDs.
MODULES_TO_MIGRATE = {
    "admin": ["admin_hostnames"],
    "coffee": ["user_beverage_counts"],
    "courtesy": ["profiles", "ignored_users", "admin_hostnames"],
    "fortune": ["last_fortune_time"],
    "help": ["last_help_time"],
    "hunt": ["scores"],
    "intro": ["users_introduced"],
    "memos": ["pending"],
    "quest": ["players"],
    "weather": ["user_locations"],
}

def migrate_state(state: dict):
    """
    Performs the migration from nickname keys to UUID keys.
    This function modifies the state object in-place.
    """
    print("Starting migration to persistent user IDs...")

    # Step 1: Create the new 'users' module state
    users_module_state = state.get("modules", {}).setdefault("users", {})
    user_map = users_module_state.setdefault("user_map", {})
    nick_map = users_module_state.setdefault("nick_map", {})
    
    # This will store a temporary mapping of old_nick -> new_uuid
    legacy_nick_to_uuid = {}

    # Step 2: Find all unique nicknames from all modules and create UUIDs
    all_nicks = set()
    modules = state.get("modules", {})
    for mod_name, keys_to_migrate in MODULES_TO_MIGRATE.items():
        if mod_name in modules:
            for key in keys_to_migrate:
                if key in modules[mod_name]:
                    data = modules[mod_name][key]
                    if isinstance(data, dict):
                        all_nicks.update(data.keys())
                    elif isinstance(data, list):
                         all_nicks.update(data) # For lists like ignored_users

    print(f"Found {len(all_nicks)} unique legacy nicknames to migrate.")

    for nick in sorted(list(all_nicks)):
        user_id = str(uuid.uuid4())
        legacy_nick_to_uuid[nick] = user_id
        
        # Populate the new users module state
        nick_map[nick] = user_id
        user_map[user_id] = {
            "id": user_id,
            "canonical_nick": nick, # We don't know their current nick, so use the legacy one
            "seen_nicks": [nick],
            "first_seen": "migrated"
        }
    
    print("Generated new persistent IDs for all users.")

    # Step 3: Go through each module and rewrite its state
    for mod_name, keys_to_migrate in MODULES_TO_MIGRATE.items():
        if mod_name in modules:
            print(f"  - Migrating module: {mod_name}")
            for key in keys_to_migrate:
                if key in modules[mod_name]:
                    old_data = modules[mod_name][key]
                    new_data = None
                    
                    if isinstance(old_data, dict):
                        new_data = {}
                        for old_nick, value in old_data.items():
                            if old_nick in legacy_nick_to_uuid:
                                new_uuid = legacy_nick_to_uuid[old_nick]
                                new_data[new_uuid] = value
                        print(f"    - Migrated {len(new_data)} records in '{key}'")
                    
                    elif isinstance(old_data, list):
                        new_data = []
                        for old_nick in old_data:
                            if old_nick in legacy_nick_to_uuid:
                                new_uuid = legacy_nick_to_uuid[old_nick]
                                new_data.append(new_uuid)
                        print(f"    - Migrated {len(new_data)} records in '{key}'")
                    
                    if new_data is not None:
                         modules[mod_name][key] = new_data

    # Special migration for courtesy's old nick_aliases
    if "courtesy" in modules and "nick_aliases" in modules["courtesy"]:
        print("  - Migrating legacy nick aliases...")
        old_aliases = modules["courtesy"].pop("nick_aliases")
        for alias, canonical in old_aliases.items():
            if alias in legacy_nick_to_uuid and canonical in legacy_nick_to_uuid:
                alias_uuid = legacy_nick_to_uuid[alias]
                canonical_uuid = legacy_nick_to_uuid[canonical]
                # In the new system, we just need to point the alias nick to the canonical UUID
                if alias_uuid != canonical_uuid:
                    nick_map[alias] = canonical_uuid
                    
    print("Migration complete.")


def main():
    """Main function to load, migrate, and save the state file."""
    if not STATE_PATH.exists():
        print(f"Error: State file not found at {STATE_PATH}. Cannot migrate.")
        return

    # Check if migration has already been run
    try:
        with open(STATE_PATH, "r") as f:
            state = json.load(f)
        if "users" in state.get("modules", {}):
            print("Migration appears to have already been run ('users' module state exists).")
            print("If you need to re-run it, please manually remove the 'users' section from your state.json.")
            return
    except Exception as e:
        print(f"Error reading state file: {e}")
        return

    backup_path = STATE_PATH.with_suffix(".json.bak_uuid_migration")
    print(f"Backing up current state to {backup_path}...")
    shutil.copy(STATE_PATH, backup_path)

    migrate_state(state)

    try:
        with open(STATE_PATH, "w") as f:
            json.dump(state, f, indent=4)
        print(f"Successfully saved migrated state to {STATE_PATH}")
    except Exception as e:
        print(f"Error: Could not write migrated state file. {e}")

if __name__ == "__main__":
    main()
