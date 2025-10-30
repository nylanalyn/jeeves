#!/usr/bin/env python3
"""
migrate_quest_state.py

Migrates quest module state from Jeeves to QuestBot.
Copies the modules.quest section from ../config/games.json to ./config/games.json
"""

import json
import sys
from pathlib import Path

def migrate_quest_state():
    # Paths
    jeeves_games = Path("../config/games.json")
    questbot_games = Path("./config/games.json")

    # Check if Jeeves games.json exists
    if not jeeves_games.exists():
        print(f"Error: Jeeves games.json not found at {jeeves_games}")
        print("Make sure you're running this from the questbot/ directory")
        return False

    # Load Jeeves state
    try:
        with open(jeeves_games, 'r') as f:
            jeeves_state = json.load(f)
        print(f"Loaded Jeeves state from {jeeves_games}")
    except Exception as e:
        print(f"Error loading Jeeves games.json: {e}")
        return False

    # Extract quest module state
    quest_state = jeeves_state.get('modules', {}).get('quest', {})
    if not quest_state:
        print("Warning: No quest state found in Jeeves games.json")
        print("This is normal if quest hasn't been used yet")
        quest_state = {}
    else:
        print(f"Found quest state with {len(quest_state)} top-level keys")

    # Create QuestBot state structure
    questbot_state = {
        'modules': {
            'quest': quest_state
        }
    }

    # Check if QuestBot games.json already exists
    if questbot_games.exists():
        print(f"\nWarning: {questbot_games} already exists")
        response = input("Overwrite? (yes/no): ").strip().lower()
        if response != 'yes':
            print("Migration cancelled")
            return False

    # Save to QuestBot
    try:
        questbot_games.parent.mkdir(parents=True, exist_ok=True)
        with open(questbot_games, 'w') as f:
            json.dump(questbot_state, f, indent=2)
        print(f"\nSuccessfully migrated quest state to {questbot_games}")
        return True
    except Exception as e:
        print(f"Error saving QuestBot games.json: {e}")
        return False

def show_stats(state):
    """Show some stats about the quest state"""
    quest = state.get('modules', {}).get('quest', {})
    if not quest:
        print("No quest data to show")
        return

    players = quest.get('players', {})
    active_bosses = quest.get('active_bosses', {})
    dungeon_parties = quest.get('dungeon_parties', {})

    print("\nQuest State Summary:")
    print(f"  Players: {len(players)}")
    print(f"  Active bosses: {len(active_bosses)}")
    print(f"  Dungeon parties: {len(dungeon_parties)}")

    if players:
        max_level = max((p.get('level', 0) for p in players.values()), default=0)
        print(f"  Highest level: {max_level}")

if __name__ == "__main__":
    print("QuestBot State Migration Tool")
    print("=" * 50)

    success = migrate_quest_state()

    if success:
        # Show stats
        try:
            with open("./config/games.json", 'r') as f:
                questbot_state = json.load(f)
            show_stats(questbot_state)
        except:
            pass

        print("\nMigration complete!")
        print("\nNext steps:")
        print("1. Edit config/config.yaml with your IRC settings")
        print("2. Start QuestBot: python3 questbot.py")
        print("3. Consider adding 'quest' to Jeeves module_blacklist")
    else:
        print("\nMigration failed")
        sys.exit(1)
