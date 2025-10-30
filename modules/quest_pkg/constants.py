# modules/quest/constants.py
# Constants for the quest module

from datetime import timezone

UTC = timezone.utc

# Dungeon Items
DUNGEON_ITEMS = [
    {
        "key": "ember_lantern",
        "name": "Ember Lantern",
        "counters": ["shadow_antechamber", "glacier_aquifer"],
        "description": "A lantern that burns with bottled sunrise, perfect for banishing oppressive darkness or frost."
    },
    {
        "key": "tempest_charm",
        "name": "Tempest Charm",
        "counters": ["storm_bridge", "crystal_singularity"],
        "description": "A palm-sized fulgurite charm that drinks lightning and howling winds."
    },
    {
        "key": "spiral_shell",
        "name": "Spiral Siren-Shell",
        "counters": ["echo_archive", "sirens_chorus"],
        "description": "This shell hums with counter-harmony, unraveling echoes and enthralling songs."
    },
    {
        "key": "venom_salve",
        "name": "Venomveil Salve",
        "counters": ["venom_garden", "scarlet_greenhouse"],
        "description": "A shimmering ointment that renders the skin proof against toxins and spores."
    },
    {
        "key": "gravity_boots",
        "name": "Gravity Boots",
        "counters": ["tilting_causeway", "sand_maw"],
        "description": "Boots with rune-studded soles that cling to reality when the floor decides not to."
    },
    {
        "key": "mirror_loom",
        "name": "Mirrorloom Veil",
        "counters": ["mirror_gallery", "chameleon_colonnade"],
        "description": "A shining cloak that reveals impostors and bends false reflections away."
    },
    {
        "key": "gearstone",
        "name": "Gearstone Glyph",
        "counters": ["clockwork_vault", "sealed_lab"],
        "description": "A carved rune that convinces machinery you are cleared for passage."
    }
]

DUNGEON_ITEMS_BY_KEY = {item["key"]: item for item in DUNGEON_ITEMS}

# Dungeon Reward
DUNGEON_REWARD_KEY = "dungeon_relics"
DUNGEON_REWARD_NAME = "Mythic Relic"
DUNGEON_REWARD_EFFECT_TEXT = "Use with !quest use dungeon_relic to guarantee victory in your next five solo fights."
DUNGEON_REWARD_CHARGES = 5

# Dungeon Rooms (ordered easiest to hardest)
DUNGEON_ROOMS = [
    {
        "id": "mirror_gallery",
        "name": "Mirror Gallery",
        "intro": "Mirrors bloom from the walls, each reflection stepping forward with a hungry grin.",
        "bypass_text": "The Mirrorloom Veil ripples and the impostors collapse back into glass.",
        "counter_items": ["mirror_loom"],
        "monster": {
            "name": "Glass Doppel",
            "level_offset": 1,
            "win_chance_adjust": 0.0,
            "xp_reward": 110
        }
    },
    {
        "id": "tilting_causeway",
        "name": "Tilting Causeway",
        "intro": "Floor plates pivot and yaw, threatening to fling you into endless abyss below.",
        "bypass_text": "Your Gravity Boots lock onto the stone, anchoring each step until the shifting slows.",
        "counter_items": ["gravity_boots"],
        "monster": {
            "name": "Abyssal Skitterer",
            "level_offset": 1,
            "win_chance_adjust": -0.02,
            "xp_reward": 115
        }
    },
    {
        "id": "storm_bridge",
        "name": "Storm Bridge",
        "intro": "A suspended bridge crackles with wild lightning as hurricane gusts slam the rails.",
        "bypass_text": "The Tempest Charm drinks the storm. You cross as the winds bow respectfully.",
        "counter_items": ["tempest_charm"],
        "monster": {
            "name": "Thunderbound Sentinel",
            "level_offset": 2,
            "win_chance_adjust": -0.03,
            "xp_reward": 130
        }
    },
    {
        "id": "shadow_antechamber",
        "name": "Shadow Antechamber",
        "intro": "A tenebrous hallway swallows torchlight as whispers coil around you.",
        "bypass_text": "Your Ember Lantern flares, painting the shadows in molten gold as hidden glyphs reveal a safe path.",
        "counter_items": ["ember_lantern"],
        "monster": {
            "name": "Gloom Siphon",
            "level_offset": 1,
            "win_chance_adjust": -0.05,
            "xp_reward": 120
        }
    },
    {
        "id": "crystal_singularity",
        "name": "Crystal Singularity",
        "intro": "Floating shards spin, screaming with psionic static that tugs at your bones.",
        "bypass_text": "The Tempest Charm hums with resonance, harmonizing the shards until they drift aside.",
        "counter_items": ["tempest_charm"],
        "monster": {
            "name": "Shardstorm Elemental",
            "level_offset": 2,
            "win_chance_adjust": -0.05,
            "xp_reward": 150
        }
    },
    {
        "id": "scarlet_greenhouse",
        "name": "Scarlet Greenhouse",
        "intro": "Thick mist rolls over fungal beds, each spore pulsing with draining hunger.",
        "bypass_text": "Another layer of Venomveil Salve seals your lungs; the spores fade to harmless motes.",
        "counter_items": ["venom_salve"],
        "monster": {
            "name": "Spore Matriarch",
            "level_offset": 2,
            "win_chance_adjust": -0.06,
            "xp_reward": 150
        }
    },
    {
        "id": "clockwork_vault",
        "name": "Clockwork Vault",
        "intro": "Interlocking gears rotate walls into deadly configurations, sealing off exits.",
        "bypass_text": "You press the Gearstone Glyph into a socket; the mechanisms freeze, accepting you as an ally.",
        "counter_items": ["gearstone"],
        "monster": {
            "name": "Colossal Gear-Guard",
            "level_offset": 3,
            "win_chance_adjust": -0.07,
            "xp_reward": 170
        }
    },
    {
        "id": "venom_garden",
        "name": "Garden of Venom",
        "intro": "Carnivorous blooms hiss, spraying arcs of glittering toxin across the path.",
        "bypass_text": "You smear Venomveil Salve across your armor; the toxins bead harmlessly and you slip past.",
        "counter_items": ["venom_salve"],
        "monster": {
            "name": "Bloom Tyrant",
            "level_offset": 2,
            "win_chance_adjust": -0.08,
            "xp_reward": 140
        }
    },
    {
        "id": "echo_archive",
        "name": "Echo Archive",
        "intro": "A vaulted archive hums with looping echoes that gnaw at your sense of self.",
        "bypass_text": "The Spiral Siren-Shell thrums counterpoint, untangling the echoes and letting you stride through.",
        "counter_items": ["spiral_shell"],
        "monster": {
            "name": "Mnemonic Lich",
            "level_offset": 3,
            "win_chance_adjust": -0.1,
            "xp_reward": 160
        }
    },
    {
        "id": "heart_of_the_abyss",
        "name": "Heart of the Abyss",
        "intro": "An ancient throne pulses with voidlight. The dungeon's architect unfurls their wings.",
        "bypass_text": None,
        "counter_items": [],
        "monster": {
            "name": "Voidbound Sovereign",
            "level_offset": 4,
            "win_chance_adjust": -0.12,
            "xp_reward": 250
        }
    }
]

TOTAL_DUNGEON_ROOMS = len(DUNGEON_ROOMS)
DUNGEON_ROOMS_BY_ID = {room["id"]: room for room in DUNGEON_ROOMS}

# Dungeon Configuration
DUNGEON_EQUIPPED_ITEMS = 4  # Number of items player can equip
DUNGEON_SAFE_HAVENS = [3, 6, 9]  # Room numbers where safe havens appear
DUNGEON_MOMENTUM_BONUS = 0.02  # Win chance bonus per consecutive victory

# Dungeon Partial Rewards (for early exits/failures)
# Format: (min_room, max_room, xp_reward, relic_charges)
DUNGEON_PARTIAL_REWARDS = [
    (1, 2, 100, 0),   # Rooms 1-2: minimal XP, no relics
    (3, 5, 250, 1),   # Rooms 3-5: decent XP, 1 relic charge
    (6, 8, 500, 2),   # Rooms 6-8: good XP, 2 relic charges
    (9, 9, 800, 3),   # Room 9: great XP, 3 relic charges
]
