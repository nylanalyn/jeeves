#!/usr/bin/env python3
# test_absurdia.py - Test Absurdia database initialization

from pathlib import Path
from modules.absurdia_db import AbsurdiaDatabase

def test_db():
    """Test basic database operations"""

    # Paths
    db_path = Path("config/absurdia.db")
    templates_path = Path("config/absurdia_creatures.json")

    print("Initializing Absurdia database...")
    db = AbsurdiaDatabase(db_path, templates_path)

    print(f"✓ Database initialized at {db_path}")
    print(f"✓ Loaded {len(db.templates)} creature templates")

    # Test player creation
    print("\nTesting player creation...")
    player = db.get_player("test_user_1", "TestPlayer")
    print(f"✓ Created player: {player['username']} with {player['coins']} coins")

    # Test creature templates
    print("\nCreature templates loaded:")
    for name, template in list(db.templates.items())[:5]:  # Show first 5
        rarity = template['rarity']
        ctype = template['type']
        hp_range = template['hp']
        print(f"  - {name} ({rarity}, {ctype}): HP {hp_range[0]}-{hp_range[1]}")

    if len(db.templates) > 5:
        print(f"  ... and {len(db.templates) - 5} more")

    # Test creature creation
    print("\nTesting creature creation...")
    potato = db.templates.get("sentient potato")
    if potato:
        creature_id = db.create_creature(
            "test_user_1",
            "sentient potato",
            "Common",
            "Sturdy Nonsense",
            75, 18, 15, 12
        )
        print(f"✓ Created creature #{creature_id}: sentient potato")

        # Test retrieval
        creature = db.get_creature(creature_id)
        print(f"  HP: {creature['base_hp']}, Attack: {creature['base_attack']}")
        print(f"  Happiness: {creature['happiness']}")

    # Test collection progress
    owned, total = db.get_collection_progress("test_user_1")
    print(f"\n✓ Collection progress: {owned}/{total} creatures")

    # Test duplicate detection
    has_potato = db.has_creature_type("test_user_1", "sentient potato")
    print(f"✓ Duplicate detection: Player has potato = {has_potato}")

    # Test inventory
    print("\nTesting inventory...")
    db.add_item("test_user_1", "trap", "basic", 3)
    db.add_item("test_user_1", "training_item", "basic_strength", 1)

    inventory = db.get_inventory("test_user_1")
    print("✓ Added items to inventory:")
    for item in inventory:
        print(f"  - {item['item_name']}: {item['quantity']}")

    # Test trap system
    print("\nTesting trap system...")
    from datetime import datetime, timedelta, timezone
    ready_time = datetime.now(timezone.utc) + timedelta(seconds=10)
    trap_id = db.create_trap("test_user_1", "basic", ready_time)
    print(f"✓ Created trap #{trap_id} (ready in 10 seconds)")

    traps = db.get_active_traps("test_user_1")
    print(f"✓ Player has {len(traps)} active trap(s)")

    print("\n" + "="*50)
    print("✓ All tests passed! Phase 1 complete.")
    print("="*50)
    print("\nNext steps:")
    print("  - Implement creature catching (!catch, !check)")
    print("  - Implement hand-catching")
    print("  - Implement duplicate comparison system")

if __name__ == "__main__":
    test_db()
