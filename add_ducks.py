import json
from pathlib import Path
import shutil

# This script is designed to be run from the same directory as jeeves.py
ROOT = Path(__file__).resolve().parent
CONFIG_DIR = ROOT / "config"
STATE_PATH = CONFIG_DIR / "state.json"

# --- Configuration ---
TARGET_USER_NICK = "nullveil"
DUCKS_TO_ADD = 200
SCORE_KEY = "duck_hunted"

def main():
    """Main function to add test ducks to the state file for a specific user."""
    if not STATE_PATH.exists():
        print(f"Error: Could not find state file at {STATE_PATH}")
        return

    backup_path = STATE_PATH.with_suffix(".json.bak_ducks_uuid")
    print(f"Backing up current state to {backup_path}...")
    shutil.copy(STATE_PATH, backup_path)

    try:
        with open(STATE_PATH, "r") as f:
            state = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Could not read state file. It may be corrupt. {e}")
        return

    # --- New UUID-aware logic ---
    users_module_state = state.get("modules", {}).get("users", {})
    nick_map = users_module_state.get("nick_map", {})
    
    target_user_id = nick_map.get(TARGET_USER_NICK.lower())
    if not target_user_id:
        print(f"Error: Could not find a persistent user ID for the nickname '{TARGET_USER_NICK}'.")
        print("Please ensure this user has spoken in the channel at least once since the UUID migration.")
        return
    # --- End new logic ---

    print(f"Adding {DUCKS_TO_ADD} '{SCORE_KEY}' to user '{TARGET_USER_NICK}' (ID: {target_user_id})...")

    modules_state = state.setdefault("modules", {})
    hunt_state = modules_state.setdefault("hunt", {})
    scores_state = hunt_state.setdefault("scores", {})
    user_scores = scores_state.setdefault(target_user_id, {}) # Use the UUID as the key

    user_scores[SCORE_KEY] = user_scores.get(SCORE_KEY, 0) + DUCKS_TO_ADD

    try:
        with open(STATE_PATH, "w") as f:
            json.dump(state, f, indent=4)
        print(f"Successfully saved updated state to {STATE_PATH}")
    except Exception as e:
        print(f"Error: Could not write updated state file. {e}")

if __name__ == "__main__":
    main()

