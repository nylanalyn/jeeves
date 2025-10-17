#!/usr/bin/env python3
"""
Script to merge duplicate quest accounts in games.json.
Keeps the higher level account for each user and removes the lower level one.
"""

import json
from pathlib import Path

# Define the duplicates to merge
MERGES = [
    {
        "name": "RadFred",
        "keep": "0ab49193-fda9-4082-a7d0-b10137b42b1c",  # Level 12
        "remove": "5071a8e7-f494-4240-baa3-d7811cbe8a06"   # Level 5
    },
    {
        "name": "coily",
        "keep": "71553443-7db6-4038-ae2a-284354410e4b",  # Level 3 (canonical)
        "remove": "83f6cfda-a774-4970-991c-e4cb682d1598"  # Level 1
    }
]

def main():
    games_json_path = Path(__file__).parent / "config" / "games.json"

    # Load the data
    with open(games_json_path, 'r') as f:
        data = json.load(f)

    quest_data = data["modules"]["quest"]
    players = quest_data["players"]

    print("Before merge:")
    for merge in MERGES:
        print(f"\n{merge['name']}:")
        if merge['keep'] in players:
            keep_player = players[merge['keep']]
            print(f"  Keeping {merge['keep']}: Level {keep_player['level']}, XP {keep_player['xp']}")
        if merge['remove'] in players:
            remove_player = players[merge['remove']]
            print(f"  Removing {merge['remove']}: Level {remove_player['level']}, XP {remove_player['xp']}")

    # Perform the merges
    for merge in MERGES:
        if merge['remove'] in players:
            print(f"\nRemoving duplicate account for {merge['name']}: {merge['remove']}")
            del players[merge['remove']]

        # Also remove from player_classes if present
        if merge['remove'] in quest_data.get('player_classes', {}):
            print(f"  Also removing from player_classes")
            del quest_data['player_classes'][merge['remove']]

    # Save the modified data
    backup_path = games_json_path.with_suffix('.json.backup')
    print(f"\nCreating backup at {backup_path}")
    with open(backup_path, 'w') as f:
        json.dump(data, f, indent=4)

    print(f"Writing merged data to {games_json_path}")
    with open(games_json_path, 'w') as f:
        json.dump(data, f, indent=4)

    print("\nMerge complete!")
    print(f"\nAfter merge:")
    for merge in MERGES:
        print(f"\n{merge['name']}:")
        if merge['keep'] in players:
            keep_player = players[merge['keep']]
            print(f"  {merge['keep']}: Level {keep_player['level']}, XP {keep_player['xp']}")
        else:
            print(f"  {merge['keep']}: NOT FOUND")

if __name__ == "__main__":
    main()
