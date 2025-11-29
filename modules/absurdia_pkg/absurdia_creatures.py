# modules/absurdia_creatures.py
# Creature generation and care logic for Absurdia

import random
from typing import Dict, Any, Tuple, Optional, List
from datetime import datetime, timezone

class CreatureGenerator:
    """Handles creature generation with stat rolling"""

    RARITY_WEIGHTS = {
        'basic': {
            'Common': 0.70,
            'Uncommon': 0.28,
            'Rare': 0.02,
            'Legendary': 0.00
        },
        'standard': {
            'Common': 0.50,
            'Uncommon': 0.35,
            'Rare': 0.14,
            'Legendary': 0.01
        },
        'premium': {
            'Common': 0.30,
            'Uncommon': 0.40,
            'Rare': 0.25,
            'Legendary': 0.05
        },
        'deluxe': {
            'Common': 0.20,
            'Uncommon': 0.40,
            'Rare': 0.30,
            'Legendary': 0.10
        }
    }

    def __init__(self, templates: Dict[str, Dict[str, Any]]):
        self.templates = templates

        # Organize templates by rarity for quick filtering
        self.by_rarity = {
            'Common': [],
            'Uncommon': [],
            'Rare': [],
            'Legendary': []
        }

        for name, template in templates.items():
            rarity = template['rarity']
            if rarity in self.by_rarity:
                self.by_rarity[rarity].append(name)

    def roll_rarity(self, trap_quality: str) -> str:
        """Roll for creature rarity based on trap quality"""
        weights = self.RARITY_WEIGHTS.get(trap_quality, self.RARITY_WEIGHTS['basic'])

        rarities = list(weights.keys())
        probabilities = list(weights.values())

        return random.choices(rarities, weights=probabilities, k=1)[0]

    def roll_stats(self, template: Dict[str, Any]) -> Tuple[int, int, int, int]:
        """Roll stats within template's ranges"""
        hp = random.randint(template['hp'][0], template['hp'][1])
        attack = random.randint(template['attack'][0], template['attack'][1])
        defense = random.randint(template['defense'][0], template['defense'][1])
        speed = random.randint(template['speed'][0], template['speed'][1])

        return hp, attack, defense, speed

    def generate_creature(self, trap_quality: str) -> Tuple[str, str, str, int, int, int, int, Dict[str, Any]]:
        """
        Generate a random creature from trap.
        Returns: (name, rarity, creature_type, hp, attack, defense, speed, template)
        """
        # Roll rarity
        rarity = self.roll_rarity(trap_quality)

        # Get creatures of that rarity
        available = self.by_rarity.get(rarity, [])
        if not available:
            # Fallback to Common if somehow no creatures of rarity exist
            rarity = 'Common'
            available = self.by_rarity.get('Common', [])

        # Pick random creature of that rarity
        creature_name = random.choice(available)
        template = self.templates[creature_name]

        # Roll stats
        hp, attack, defense, speed = self.roll_stats(template)

        creature_type = template['type']

        return creature_name, rarity, creature_type, hp, attack, defense, speed, template

    def hand_catch_attempt(self, success_rate: float, stat_penalty: float) -> Optional[Tuple[str, str, str, int, int, int, int, Dict[str, Any]]]:
        """
        Attempt hand-catching.
        Returns creature data if successful, None if failed.
        """
        # Check success
        if random.random() > success_rate:
            return None

        # Only Common creatures can be hand-caught
        available = self.by_rarity.get('Common', [])
        if not available:
            return None

        # Pick random Common creature
        creature_name = random.choice(available)
        template = self.templates[creature_name]

        # Roll stats with penalty (Feral tier)
        base_hp, base_attack, base_defense, base_speed = self.roll_stats(template)

        # Apply stat penalty
        hp = int(base_hp * stat_penalty)
        attack = int(base_attack * stat_penalty)
        defense = int(base_defense * stat_penalty)
        speed = int(base_speed * stat_penalty)

        # Ensure minimum of 1
        hp = max(1, hp)
        attack = max(1, attack)
        defense = max(1, defense)
        speed = max(1, speed)

        creature_type = template['type']
        rarity = "Feral"  # Special rarity for hand-caught

        return creature_name, rarity, creature_type, hp, attack, defense, speed, template

    def get_catch_flavor(self, template: Dict[str, Any], is_hand_catch: bool = False, success: bool = True) -> str:
        """Get flavor text for catching"""
        if is_hand_catch:
            if success:
                return template.get('hand_catch_success', 'You grab it with your bare hands!')
            else:
                failures = template.get('hand_catch_fail', ['It escapes!'])
                return random.choice(failures)
        else:
            return template.get('catch_text', f'You caught a {template["name"]}!')

    def get_care_flavor(self, template: Dict[str, Any], care_type: str) -> str:
        """Get flavor text for care actions"""
        flavor_map = {
            'feed': template.get('feed_text', 'You feed the creature.'),
            'play': template.get('play_text', 'You play with the creature.'),
            'pet': template.get('pet_text', 'You pet the creature.')
        }
        return flavor_map.get(care_type, 'You care for the creature.')


class CreatureCare:
    """Handles creature care operations"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def can_care_for(self, creature: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Check if creature can be cared for (not in arena)"""
        if creature['submitted_to_arena']:
            return False, "Cannot care for creatures in the arena queue. Use !withdraw first."
        return True, None

    def check_care_cooldown(self, creature: Dict[str, Any], care_type: str) -> Tuple[bool, Optional[str]]:
        """Check if care action is off cooldown"""
        field_map = {
            'feed': 'last_fed',
            'play': 'last_played',
            'pet': 'last_petted'
        }

        cooldowns = self.config.get('care_cooldowns', {})
        cooldown_seconds = cooldowns.get(care_type, 3600)

        field = field_map.get(care_type)
        if not field:
            return False, "Invalid care type"

        last_time_str = creature.get(field)
        if not last_time_str:
            # Never done before, always allowed
            return True, None

        # Parse timestamp
        try:
            last_time = datetime.fromisoformat(last_time_str.replace('Z', '+00:00'))
        except:
            # Invalid timestamp, allow
            return True, None

        now = datetime.now(timezone.utc)
        elapsed = (now - last_time).total_seconds()

        if elapsed < cooldown_seconds:
            remaining = int(cooldown_seconds - elapsed)
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60

            if hours > 0:
                time_str = f"{hours}h {minutes}m"
            else:
                time_str = f"{minutes}m"

            return False, f"You must wait {time_str} before {care_type}ing again."

        return True, None

    def calculate_care_reward(self, care_type: str) -> Tuple[int, int, int]:
        """
        Calculate rewards for care action.
        Returns: (coins_earned, happiness_gained, stat_bonus)
        """
        care_costs = self.config.get('care_costs', {})
        cost = care_costs.get(care_type, 0)

        if care_type == 'feed':
            coins = random.randint(5, 10)
            happiness = 5
            stat = random.randint(1, 3)
        elif care_type == 'play':
            coins = random.randint(3, 7)
            happiness = 3
            stat = random.randint(1, 2)
        elif care_type == 'pet':
            coins = random.randint(2, 4)
            happiness = 2
            stat = 0
        else:
            coins = 0
            happiness = 0
            stat = 0

        # Net coins (after cost)
        net_coins = coins - cost

        return net_coins, happiness, stat

    def apply_happiness_decay(self, creature: Dict[str, Any], is_in_arena: bool = False) -> int:
        """
        Calculate and return current happiness after decay.
        Does NOT modify database.
        """
        current_happiness = creature['happiness']

        # Determine decay rate
        decay_config = self.config.get('happiness_decay', {})

        if is_in_arena:
            decay_hours = decay_config.get('arena_hours', 3)
        else:
            decay_hours = decay_config.get('normal_hours', 6)

        decay_seconds = decay_hours * 3600

        # Find most recent care action
        care_times = []
        for field in ['last_fed', 'last_played', 'last_petted']:
            time_str = creature.get(field)
            if time_str:
                try:
                    care_times.append(datetime.fromisoformat(time_str.replace('Z', '+00:00')))
                except:
                    pass

        if not care_times:
            # No care history, use caught_at
            try:
                last_care = datetime.fromisoformat(creature['caught_at'].replace('Z', '+00:00'))
            except:
                last_care = datetime.now(timezone.utc)
        else:
            last_care = max(care_times)

        # Calculate decay
        now = datetime.now(timezone.utc)
        elapsed = (now - last_care).total_seconds()

        decay_amount = int(elapsed // decay_seconds)

        new_happiness = max(0, current_happiness - decay_amount)

        return new_happiness
