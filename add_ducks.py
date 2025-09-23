import json
from pathlib import Path
import shutil

# This script is designed to be run from the same directory as jeeves.py
ROOT = Path(__file__).resolve().parent
CONFIG_DIR = Path.home() / ".config" / "jeeves"
STATE_PATH = CONFIG_DIR / "state.json"

# --- Configuration ---
# Easily change these values to test with different users or amounts.
TARGET_USER = "nullveil"
DUCKS_TO_ADD = 200
SCORE_KEY = "duck_hunted"  # This is the canonical, correct key

def main():
    """Main function to add test ducks to the state file."""
    if not STATE_PATH.exists():
        print(f"Error: Could not find state file at {STATE_PATH}")
        return

    # 1. Create a backup for safety
    backup_path = STATE_PATH.with_suffix(".json.bak_ducks")
    print(f"Backing up current state to {backup_path}...")
    shutil.copy(STATE_PATH, backup_path)

    # 2. Load the state data
    try:
        with open(STATE_PATH, "r") as f:
            state = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Could not read state file. It may be corrupt. {e}")
        return

    print(f"Adding {DUCKS_TO_ADD} '{SCORE_KEY}' to user '{TARGET_USER}'...")

    # 3. Navigate and update the scores
    # Use .get() with default values to safely create nested dictionaries if they don't exist
    modules_state = state.setdefault("modules", {})
    hunt_state = modules_state.setdefault("hunt", {})
    scores_state = hunt_state.setdefault("scores", {})
    user_scores = scores_state.setdefault(TARGET_USER.lower(), {})

    # Set or overwrite the duck count for the user
    user_scores[SCORE_KEY] = DUCKS_TO_ADD

    # 4. Write the modified data back to the state file
    try:
        with open(STATE_PATH, "w") as f:
            json.dump(state, f, indent=4)
        print(f"Successfully saved updated state to {STATE_PATH}")
    except Exception as e:
        print(f"Error: Could not write updated state file. {e}")

if __name__ == "__main__":
    main()
