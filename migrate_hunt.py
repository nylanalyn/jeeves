# migrate_hunts.py
# A one-time script to migrate animal scores from Bender's text format
# into Jeeves's state.json file for the hunt module.

import json
import re
from pathlib import Path

# --- Configuration ---
# Assumes this script is in the same directory as jeeves.py
CONFIG_DIR = Path.home() / ".config" / "jeeves"
STATE_PATH = CONFIG_DIR / "state.json"
BENDER_DATA_PATH = Path(__file__).resolve().parent / "animals.txt"
# ---------------------

def parse_bender_data():
    """Parses the animals.txt file and returns a structured dictionary."""
    if not BENDER_DATA_PATH.exists():
        print(f"Error: Bender data file not found at {BENDER_DATA_PATH}")
        return None

    print("Parsing Bender's score file...")
    bender_scores = {}
    
    with open(BENDER_DATA_PATH, 'r') as f:
        content = f.read()

    # Split the file into blocks for each user
    user_blocks = content.strip().split('--------------------')
    
    for block in user_blocks:
        block = block.strip()
        if not block:
            continue

        lines = block.split('\n')
        user_line = lines[0]
        match = re.match(r"User: (\S+)", user_line)
        if not match:
            continue
        
        username = match.group(1).lower()
        user_scores = {}

        for score_line in lines[1:]:
            score_line = score_line.strip()
            if not score_line.startswith('-'):
                continue

            # Example line: "- Ducks Befriended: 1"
            score_match = re.match(r"-\s*(Ducks|Cats|Puppies)\s+(Befriended|Trapped):\s*(\d+)", score_line)
            if not score_match:
                continue

            animal, action, count_str = score_match.groups()
            count = int(count_str)
            
            # Map Bender's format to Jeeves's format
            animal_key = animal.lower().rstrip('s') # "Ducks" -> "duck"
            action_key = "hugged" if action == "Befriended" else "hunted"
            
            jeeves_key = f"{animal_key}_{action_key}"
            user_scores[jeeves_key] = count
        
        if user_scores:
            bender_scores[username] = user_scores
    
    print(f"Successfully parsed data for {len(bender_scores)} users from Bender's file.")
    return bender_scores

def merge_scores():
    """Merges the parsed Bender scores into Jeeves's state file."""
    bender_scores = parse_bender_data()
    if not bender_scores:
        return

    if not STATE_PATH.exists():
        print(f"Warning: Jeeves state file not found at {STATE_PATH}. A new one will be created.")
        jeeves_state = {}
    else:
        try:
            with open(STATE_PATH, 'r') as f:
                jeeves_state = json.load(f)
        except json.JSONDecodeError:
            print(f"Error: Could not parse {STATE_PATH}. Aborting.")
            return

    print("Backing up current state file to state.json.migbak...")
    backup_path = STATE_PATH.with_suffix(".json.migbak")
    with open(backup_path, 'w') as f:
        json.dump(jeeves_state, f, indent=2)

    # Ensure the necessary structure exists in Jeeves's state
    if "modules" not in jeeves_state:
        jeeves_state["modules"] = {}
    if "hunt" not in jeeves_state["modules"]:
        jeeves_state["modules"]["hunt"] = {}
    if "scores" not in jeeves_state["modules"]["hunt"]:
        jeeves_state["modules"]["hunt"]["scores"] = {}
    
    jeeves_hunt_scores = jeeves_state["modules"]["hunt"]["scores"]
    users_updated = 0
    users_created = 0

    print("Merging scores...")
    for user, old_scores in bender_scores.items():
        user_key = user.lower()
        if user_key in jeeves_hunt_scores:
            # User exists, merge scores
            users_updated += 1
            for score_key, value in old_scores.items():
                # Add the old score to the new one
                jeeves_hunt_scores[user_key][score_key] = jeeves_hunt_scores[user_key].get(score_key, 0) + value
        else:
            # New user, just add their data
            users_created += 1
            jeeves_hunt_scores[user_key] = old_scores

    print(f"\nMigration complete.")
    print(f"  - {users_updated} existing users were updated.")
    print(f"  - {users_created} new users were added.")
    
    print(f"Saving merged data to {STATE_PATH}...")
    with open(STATE_PATH, 'w') as f:
        json.dump(jeeves_state, f, indent=2)
    print("Done.")

if __name__ == "__main__":
    merge_scores()

