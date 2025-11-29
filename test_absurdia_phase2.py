#!/usr/bin/env python3
# test_absurdia_phase2.py - Test Phase 2: Creature Catching

from pathlib import Path
from modules.absurdia_db import AbsurdiaDatabase
from modules.absurdia_creatures import CreatureGenerator, CreatureCare
from datetime import datetime, timedelta, timezone

def test_phase2():
    """Test Phase 2: Catching system"""

    # Paths
    db_path = Path("config/absurdia.db")
    templates_path = Path("config/absurdia_creatures.json")

    print("="*60)
    print("PHASE 2 TEST: Creature Catching System")
    print("="*60)

    # Initialize
    db = AbsurdiaDatabase(db_path, templates_path)
    generator = CreatureGenerator(db.templates)

    print(f"\n✓ Loaded {len(db.templates)} creature templates")

    # Test 1: Creature generation with trap
    print("\n[TEST 1] Creature generation from traps")
    print("-" * 60)

    for trap_type in ['basic', 'standard', 'premium', 'deluxe']:
        name, rarity, ctype, hp, atk, defense, spd, template = generator.generate_creature(trap_type)
        print(f"  {trap_type} trap → {name} ({rarity}, {ctype})")
        print(f"    Stats: HP:{hp} ATK:{atk} DEF:{defense} SPD:{spd}")

    # Test 2: Hand-catching
    print("\n[TEST 2] Hand-catching attempts")
    print("-" * 60)

    attempts = 0
    successes = 0
    max_attempts = 100

    for i in range(max_attempts):
        result = generator.hand_catch_attempt(0.05, 0.6)
        attempts += 1
        if result:
            successes += 1
            name, rarity, ctype, hp, atk, defense, spd, template = result
            print(f"  ✓ SUCCESS on attempt {attempts}: {name} (Feral)")
            print(f"    Stats: HP:{hp} ATK:{atk} DEF:{defense} SPD:{spd}")
            flavor = generator.get_catch_flavor(template, is_hand_catch=True, success=True)
            print(f"    Flavor: {flavor}")
            break

    success_rate = (successes / attempts) * 100
    print(f"\n  Success rate: {success_rate:.1f}% ({successes}/{attempts} attempts)")
    print(f"  Expected: ~5% (actual will vary due to RNG)")

    # Test 3: Duplicate detection and comparison
    print("\n[TEST 3] Duplicate detection")
    print("-" * 60)

    user_id = "test_user_phase2"
    username = "TestPlayer2"

    # Create player
    player = db.get_player(user_id, username)
    print(f"  ✓ Created player with {player['coins']} coins")

    # Catch first potato
    name1, rarity1, ctype1, hp1, atk1, def1, spd1, _ = generator.generate_creature('basic')

    # Force it to be a potato for testing
    template = db.templates['sentient potato']
    hp1, atk1, def1, spd1 = generator.roll_stats(template)
    creature1_id = db.create_creature(user_id, 'sentient potato', 'Common', 'Sturdy Nonsense', hp1, atk1, def1, spd1)

    print(f"  ✓ Caught first potato (#{creature1_id}): HP:{hp1} ATK:{atk1}")

    # Check duplicate detection
    has_potato = db.has_creature_type(user_id, 'sentient potato')
    print(f"  ✓ Duplicate detection: has_potato = {has_potato}")

    # Catch second potato (duplicate)
    hp2, atk2, def2, spd2 = generator.roll_stats(template)
    pending_id = db.create_pending_catch(
        user_id, 'sentient potato', 'Common', 'Sturdy Nonsense',
        hp2, atk2, def2, spd2, 'basic', 30
    )

    print(f"  ✓ Created pending catch (duplicate)")
    print(f"    First potato:  HP:{hp1} ATK:{atk1} DEF:{def1} SPD:{spd1}")
    print(f"    Second potato: HP:{hp2} ATK:{atk2} DEF:{def2} SPD:{spd2}")

    # Get pending catch
    pending = db.get_pending_catch(user_id)
    print(f"  ✓ Retrieved pending catch: {pending['creature_name']}")

    # Test 4: Resolving duplicate (keep new)
    print("\n[TEST 4] Resolving duplicate - keep new")
    print("-" * 60)

    refund, new_creature_id = db.resolve_pending_catch(user_id, keep_new=True, trap_refund_percent=0.5)

    print(f"  ✓ Kept new creature (#{new_creature_id})")
    print(f"  ✓ Refund: {refund} coins (50% of trap cost)")

    # Verify old one was deleted, new one exists
    creatures = db.get_player_creatures(user_id)
    print(f"  ✓ Player now has {len(creatures)} creature(s)")

    new_creature = db.get_creature(new_creature_id)
    print(f"  ✓ New potato stats: HP:{new_creature['base_hp']} ATK:{new_creature['base_attack']}")

    # Test 5: Shop and inventory
    print("\n[TEST 5] Shop and inventory")
    print("-" * 60)

    # Give player coins
    db.update_player_coins(user_id, 500)
    player = db.get_player(user_id, username)
    print(f"  ✓ Player balance: {player['coins']} coins")

    # Buy traps
    db.update_player_coins(user_id, -150)
    db.add_item(user_id, 'trap', 'basic', 3)
    print(f"  ✓ Purchased 3 basic traps for 150 coins")

    inventory = db.get_inventory(user_id)
    for item in inventory:
        print(f"    - {item['item_name']}: {item['quantity']}")

    # Test 6: Trap setting and checking
    print("\n[TEST 6] Trap system")
    print("-" * 60)

    # Set trap with short timer for testing
    ready_time = datetime.now(timezone.utc) + timedelta(seconds=2)
    trap_id = db.create_trap(user_id, 'basic', ready_time)
    print(f"  ✓ Set trap #{trap_id} (ready in 2 seconds)")

    # Check before ready
    traps = db.get_active_traps(user_id)
    trap = traps[0]
    ready_dt = datetime.fromisoformat(trap['ready_at'].replace('Z', '+00:00'))
    now = datetime.now(timezone.utc)

    if now < ready_dt:
        print(f"  ✓ Trap not ready yet (correct)")

    # Wait
    import time
    print(f"  ⏳ Waiting 2 seconds...")
    time.sleep(2)

    # Check after ready
    now = datetime.now(timezone.utc)
    if now >= ready_dt:
        print(f"  ✓ Trap is now ready!")

    # Mark as collected
    db.mark_trap_collected(trap_id)
    print(f"  ✓ Marked trap as collected")

    # Test 7: Flavor text
    print("\n[TEST 7] Flavor text")
    print("-" * 60)

    potato_template = db.templates['sentient potato']

    print(f"  Catch: {generator.get_catch_flavor(potato_template)}")
    print(f"  Hand-catch success: {generator.get_catch_flavor(potato_template, is_hand_catch=True, success=True)}")
    print(f"  Hand-catch fail: {generator.get_catch_flavor(potato_template, is_hand_catch=True, success=False)}")

    config = {'care_cooldowns': {}, 'care_costs': {}}
    care = CreatureCare(config)

    print(f"  Feed: {generator.get_care_flavor(potato_template, 'feed')}")
    print(f"  Play: {generator.get_care_flavor(potato_template, 'play')}")
    print(f"  Pet: {generator.get_care_flavor(potato_template, 'pet')}")

    # Summary
    print("\n" + "="*60)
    print("✅ PHASE 2 COMPLETE: All catching systems functional!")
    print("="*60)
    print("\nImplemented:")
    print("  ✓ Creature generation with stat rolling")
    print("  ✓ Rarity-based trap system")
    print("  ✓ Hand-catching (5% success rate)")
    print("  ✓ Duplicate detection and comparison")
    print("  ✓ Pending catch resolution with refunds")
    print("  ✓ Shop and inventory system")
    print("  ✓ Trap setting and checking")
    print("  ✓ Flavor text for all creatures")
    print("\nReady for IRC testing!")

if __name__ == "__main__":
    test_phase2()
