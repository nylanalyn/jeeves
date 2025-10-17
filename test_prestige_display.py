#!/usr/bin/env python3
"""Test prestige bonus display logic."""

def calculate_prestige_bonuses(prestige: int) -> dict:
    """Calculate all accumulated prestige bonuses for display."""
    if prestige == 0:
        return {}

    # Win chance bonus
    if prestige <= 3:
        win_bonus = 5
    elif prestige <= 6:
        win_bonus = 10
    elif prestige <= 9:
        win_bonus = 15
    else:
        win_bonus = 20

    # XP multiplier bonus
    if prestige < 2:
        xp_mult = 0
    elif prestige < 5:
        xp_mult = 25
    elif prestige < 8:
        xp_mult = 50
    elif prestige < 10:
        xp_mult = 75
    else:
        xp_mult = 100

    # Energy bonus
    if prestige < 3:
        energy_bonus = 0
    elif prestige < 6:
        energy_bonus = 1
    elif prestige < 9:
        energy_bonus = 2
    else:
        energy_bonus = 3

    return {
        "win_chance": win_bonus,
        "xp_multiplier": xp_mult,
        "energy": energy_bonus
    }

# Test all prestige levels
print("Prestige Bonus Display Test:")
print("=" * 60)

for prestige in range(11):
    bonuses = calculate_prestige_bonuses(prestige)
    if not bonuses:
        print(f"Prestige {prestige}: No bonuses")
    else:
        bonus_parts = []
        if bonuses.get("win_chance", 0) > 0:
            bonus_parts.append(f"+{bonuses['win_chance']}% win chance")
        if bonuses.get("xp_multiplier", 0) > 0:
            bonus_parts.append(f"+{bonuses['xp_multiplier']}% XP")
        if bonuses.get("energy", 0) > 0:
            bonus_parts.append(f"+{bonuses['energy']} max energy")

        bonus_text = ", ".join(bonus_parts)
        print(f"Prestige {prestige}: {bonus_text}")

print("\n" + "=" * 60)
print("\nTest for jelly (prestige 3):")
jelly_bonuses = calculate_prestige_bonuses(3)
jelly_parts = []
if jelly_bonuses.get("win_chance", 0) > 0:
    jelly_parts.append(f"+{jelly_bonuses['win_chance']}% win chance")
if jelly_bonuses.get("xp_multiplier", 0) > 0:
    jelly_parts.append(f"+{jelly_bonuses['xp_multiplier']}% XP")
if jelly_bonuses.get("energy", 0) > 0:
    jelly_parts.append(f"+{jelly_bonuses['energy']} max energy")
print(", ".join(jelly_parts))
