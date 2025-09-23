import json
from pathlib import Path
import shutil

# This script is designed to be run from the same directory as jeeves.py
ROOT = Path(__file__).resolve().parent
CONFIG_DIR = Path.home() / ".config" / "jeeves"
STATE_PATH = CONFIG_DIR / "state.json"

# --- Mappings from old/bad keys to the new canonical keys ---
# This is where we define all the known misspellings and variations.
SCORE_MAP = {
    # Hugged Variations
    "cat huged": "cat_hugged",
    "cat hugged": "cat_hugged",
    "duck hugged": "duck_hugged",
    "puppie hugged": "puppy_hugged",
    "puppy hugged": "puppy_hugged",

    # Hunted Variations
    "cat hunted": "cat_hunted",
    "duck hunted": "duck_hunted",
    "puppie hunted": "puppy_hunted",
    "puppy hunted": "puppy_hunted",
    "puppies hunted": "puppy_hunted", # Plural fix
}

def normalize_key(old_key: str) -> str:
    """Converts a messy key like 'Cat huged' to a canonical key like 'cat_hugged'."""
    # Convert to lowercase and remove underscores for consistent matching
    clean_key = old_key.lower().replace('_', ' ')
    return SCORE_MAP.get(clean_key, old_key) # Return the original if no match is found

def main():
    """Main function to run the cleanup process."""
    if not STATE_PATH.exists():
        print(f"Error: Could not find state file at {STATE_PATH}")
        return

    # 1. Create a backup for safety
    backup_path = STATE_PATH.with_suffix(".json.bak")
    print(f"Backing up current state to {backup_path}...")
    shutil.copy(STATE_PATH, backup_path)

    # 2. Load the state data
    try:
        with open(STATE_PATH, "r") as f:
            state = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Could not read state file. It may be corrupt. {e}")
        return

    # Navigate to the hunt scores
    hunt_scores = state.get("modules", {}).get("hunt", {}).get("scores", {})
    if not hunt_scores:
        print("No hunt scores found to clean up.")
        return

    print("\nStarting score cleanup...")
    users_fixed = 0

    # 3. Iterate through each user and clean their scores
    for username, old_scores in hunt_scores.items():
        if not isinstance(old_scores, dict):
            continue

        new_scores = {}
        fixed_this_user = False

        for old_key, count in old_scores.items():
            canonical_key = normalize_key(old_key)
            
            if old_key != canonical_key:
                print(f"  - User '{username}': Normalizing '{old_key}' -> '{canonical_key}'")
                fixed_this_user = True

            # Add the count to the new, clean key
            new_scores[canonical_key] = new_scores.get(canonical_key, 0) + count

        if fixed_this_user:
            hunt_scores[username] = new_scores
            users_fixed += 1

    if users_fixed > 0:
        print(f"\nCleanup complete. Fixed scores for {users_fixed} user(s).")
        # 4. Write the cleaned data back to the state file
        try:
            with open(STATE_PATH, "w") as f:
                json.dump(state, f, indent=4)
            print(f"Successfully saved cleaned state to {STATE_PATH}")
        except Exception as e:
            print(f"Error: Could not write cleaned state file. {e}")
    else:
        print("\nNo scores needed fixing.")

if __name__ == "__main__":
    main()
