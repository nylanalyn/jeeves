import json
from pathlib import Path
import shutil
import argparse
import random

# --- New Self-Contained Path Configuration ---
ROOT = Path(__file__).resolve().parent
CONFIG_DIR = ROOT / "config"
STATE_PATH = CONFIG_DIR / "state.json"
# --- End New Configuration ---


# --- Mappings for score cleanup ---
SCORE_MAP = {
    "cat huged": "cat_hugged", "cat hugged": "cat_hugged", "duck hugged": "duck_hugged",
    "puppie hugged": "puppy_hugged", "puppy hugged": "puppy_hugged", "cat hunted": "cat_hunted",
    "duck hunted": "duck_hunted", "puppie hunted": "puppy_hunted", "puppy hunted": "puppy_hunted",
    "puppies hunted": "puppy_hunted",
}

def normalize_key(old_key: str) -> str:
    clean_key = old_key.lower().replace('_', ' ')
    return SCORE_MAP.get(clean_key, old_key)

def fix_scores(state: dict):
    """Normalizes all hunt scores in the state object."""
    hunt_scores = state.get("modules", {}).get("hunt", {}).get("scores", {})
    if not hunt_scores:
        print("No hunt scores found to clean up.")
        return

    print("\nStarting score cleanup...")
    users_fixed = 0
    for username, old_scores in hunt_scores.items():
        if not isinstance(old_scores, dict): continue
        new_scores = {}
        fixed_this_user = False
        for old_key, count in old_scores.items():
            canonical_key = normalize_key(old_key)
            if old_key != canonical_key:
                print(f"  - User '{username}': Normalizing '{old_key}' -> '{canonical_key}'")
                fixed_this_user = True
            new_scores[canonical_key] = new_scores.get(canonical_key, 0) + count
        if fixed_this_user:
            hunt_scores[username] = new_scores
            users_fixed += 1
    
    if users_fixed > 0:
        print(f"Cleanup complete. Fixed scores for {users_fixed} user(s).")
    else:
        print("No scores needed fixing.")

def start_duck_event(state: dict, target_user: str):
    """Removes a target user's ducks and creates a channel-wide event."""
    print(f"\nStarting 'Great Duck Migration' event setup for user '{target_user}'...")
    MIN_FLOCK_SIZE = 20
    MAX_FLOCK_SIZE = 50
    
    hunt_module_state = state.get("modules", {}).get("hunt", {})
    hunt_scores = hunt_module_state.get("scores", {})
    user_scores = hunt_scores.get(target_user.lower(), {})

    duck_count = user_scores.pop("duck_hunted", 0)

    if duck_count == 0:
        print(f"User '{target_user}' has no hunted ducks to release. Aborting event setup.")
        return

    print(f"Found {duck_count} hunted ducks for user '{target_user}'. Generating random flocks...")
    
    flocks = []
    remaining_ducks = duck_count
    while remaining_ducks > MIN_FLOCK_SIZE:
        flock_size = random.randint(MIN_FLOCK_SIZE, MAX_FLOCK_SIZE)
        if remaining_ducks - flock_size < MIN_FLOCK_SIZE:
            flocks.append(remaining_ducks)
            remaining_ducks = 0
            break
        flocks.append(flock_size)
        remaining_ducks -= flock_size

    if not flocks:
        print(f"Not enough ducks ({duck_count}) to form any flocks. Aborting.")
        user_scores["duck_hunted"] = duck_count # Put the ducks back
        return

    print(f"Generated {len(flocks)} flocks. Total ducks in event: {sum(flocks)}.")
    
    hunt_scores[target_user.lower()] = user_scores
    
    hunt_module_state["event"] = {
        "active": True,
        "name": "The Great Duck Migration",
        "flocks": flocks,
        "animal_name": "duck"
    }
    
    hunt_module_state["active_animal"] = None
    
    print("Event state has been added. The bot will begin the event on its next startup.")

def main():
    """Main function to parse arguments and run the requested actions."""
    parser = argparse.ArgumentParser(description="Clean up Jeeves's hunt scores and optionally start a special event.")
    parser.add_argument('--fix', action='store_true', help="Run the score normalization process.")
    parser.add_argument('--start-duck-event', type=str, metavar='USERNAME', help="Remove a user's ducks and start the Great Duck Migration event.")
    args = parser.parse_args()

    if not args.fix and not args.start_duck_event:
        parser.print_help()
        print("\nPlease specify an action: --fix or --start-duck-event <username>")
        return

    if not STATE_PATH.exists():
        print(f"Error: Could not find state file at {STATE_PATH}")
        return

    backup_path = STATE_PATH.with_suffix(".json.bak_event_script")
    print(f"Backing up current state to {backup_path}...")
    shutil.copy(STATE_PATH, backup_path)

    try:
        with open(STATE_PATH, "r") as f:
            state = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Could not read state file. It may be corrupt. {e}")
        return

    if args.fix:
        fix_scores(state)
    
    if args.start_duck_event:
        start_duck_event(state, args.start_duck_event)

    try:
        with open(STATE_PATH, "w") as f:
            json.dump(state, f, indent=4)
        print(f"\nSuccessfully saved updated state to {STATE_PATH}")
    except Exception as e:
        print(f"Error: Could not write updated state file. {e}")

if __name__ == "__main__":
    main()

