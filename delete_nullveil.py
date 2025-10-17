#!/usr/bin/env python3
"""
Script to delete the nullveil test account from games.json.
"""

import json
from pathlib import Path

NULLVEIL_ID = "485d5e99-4123-4246-af0a-6bc8a37cc84b"

def main():
    games_json_path = Path(__file__).parent / "config" / "games.json"

    # Load the data
    with open(games_json_path, 'r') as f:
        data = json.load(f)

    modules = data["modules"]

    # Track what we're removing
    removed_from = []

    # Remove from hunt scores
    if NULLVEIL_ID in modules.get("hunt", {}).get("scores", {}):
        hunt_data = modules["hunt"]["scores"][NULLVEIL_ID]
        print(f"Removing from hunt scores: {hunt_data}")
        del modules["hunt"]["scores"][NULLVEIL_ID]
        removed_from.append("hunt.scores")

    # Remove from quest players
    if NULLVEIL_ID in modules.get("quest", {}).get("players", {}):
        player_data = modules["quest"]["players"][NULLVEIL_ID]
        print(f"Removing from quest players: Level {player_data['level']}, {player_data['xp']} XP")
        del modules["quest"]["players"][NULLVEIL_ID]
        removed_from.append("quest.players")

    # Remove from quest player_classes
    if NULLVEIL_ID in modules.get("quest", {}).get("player_classes", {}):
        print(f"Removing from quest player_classes")
        del modules["quest"]["player_classes"][NULLVEIL_ID]
        removed_from.append("quest.player_classes")

    # Check other modules for this user ID
    for module_name, module_data in modules.items():
        if module_name in ["hunt", "quest"]:
            continue

        # Check for user ID in any nested structures
        data_str = json.dumps(module_data)
        if NULLVEIL_ID in data_str:
            print(f"WARNING: nullveil ID found in module '{module_name}' - may need manual cleanup")

    if not removed_from:
        print("nullveil account not found in games.json")
        return

    # Save the modified data
    backup_path = games_json_path.with_suffix('.json.backup2')
    print(f"\nCreating backup at {backup_path}")
    with open(backup_path, 'w') as f:
        json.dump(data, f, indent=4)

    print(f"Writing updated data to {games_json_path}")
    with open(games_json_path, 'w') as f:
        json.dump(data, f, indent=4)

    print(f"\nDeletion complete! Removed nullveil from: {', '.join(removed_from)}")

if __name__ == "__main__":
    main()
