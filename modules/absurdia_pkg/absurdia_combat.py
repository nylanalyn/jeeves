# modules/absurdia_pkg/absurdia_combat.py
# Combat engine for Absurdia creature battles

import random
from typing import Dict, Any, List, Tuple


class CombatEngine:
    """Handles turn-based combat between creatures"""

    # Type advantage mapping
    TYPE_ADVANTAGES = {
        'Sturdy Nonsense': 'Sharp Weird',
        'Sharp Weird': 'Flimsy Chaos',
        'Flimsy Chaos': 'Sturdy Nonsense'
    }

    def __init__(self):
        """Initialize combat engine"""
        pass

    def calculate_effective_stats(self, creature: Dict[str, Any]) -> Dict[str, int]:
        """
        Calculate effective stats including happiness bonuses.

        Formula:
        - Effective HP = Base HP + Bonus HP + (Happiness/10)
        - Effective Attack = Base Attack + Bonus Attack + (Happiness/20)
        - Effective Defense = Base Defense + Bonus Defense + (Happiness/20)
        - Effective Speed = Base Speed + Bonus Speed

        Args:
            creature: Creature dict from database

        Returns:
            Dict with effective stats
        """
        happiness = creature['happiness']

        return {
            'hp': creature['base_hp'] + creature['bonus_hp'] + (happiness // 10),
            'attack': creature['base_attack'] + creature['bonus_attack'] + (happiness // 20),
            'defense': creature['base_defense'] + creature['bonus_defense'] + (happiness // 20),
            'speed': creature['base_speed'] + creature['bonus_speed']
        }

    def get_type_multiplier(self, attacker_type: str, defender_type: str) -> float:
        """
        Calculate type advantage multiplier.

        Args:
            attacker_type: Type of attacking creature
            defender_type: Type of defending creature

        Returns:
            1.3 if attacker has advantage, else 1.0
        """
        if self.TYPE_ADVANTAGES.get(attacker_type) == defender_type:
            return 1.3
        return 1.0

    def calculate_damage(self, attacker_stats: Dict[str, int], defender_stats: Dict[str, int],
                        type_multiplier: float) -> int:
        """
        Calculate damage for one attack.

        Formula: Damage = (Attacker_ATK / Defender_DEF) * BASE_MULTIPLIER * type_multiplier * random(0.95, 1.05)

        BASE_MULTIPLIER = 8 to scale damage to reasonable levels (5-10 round battles)

        Args:
            attacker_stats: Effective stats of attacker
            defender_stats: Effective stats of defender
            type_multiplier: 1.3 if type advantage, else 1.0

        Returns:
            Final damage (rounded to int)
        """
        # Prevent division by zero
        defender_def = max(1, defender_stats['defense'])

        # Base damage calculation with scaling multiplier
        BASE_MULTIPLIER = 8
        base_damage = (attacker_stats['attack'] / defender_def) * BASE_MULTIPLIER * type_multiplier

        # Apply random variance (95% to 105%)
        variance = random.uniform(0.95, 1.05)
        final_damage = base_damage * variance

        # Round and ensure at least 1 damage
        return max(1, round(final_damage))

    def simulate_battle(self, creature1: Dict[str, Any], creature2: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simulate a complete battle between two creatures.

        Args:
            creature1: First creature dict from database
            creature2: Second creature dict from database

        Returns:
            Dict with battle results:
            {
                'winner': creature_dict,
                'loser': creature_dict,
                'rounds': int,
                'battle_log': List[str],
                'final_hp': {creature1_id: hp, creature2_id: hp}
            }
        """
        # Calculate effective stats
        stats1 = self.calculate_effective_stats(creature1)
        stats2 = self.calculate_effective_stats(creature2)

        # Determine type advantages
        type_mult_1_vs_2 = self.get_type_multiplier(creature1['creature_type'], creature2['creature_type'])
        type_mult_2_vs_1 = self.get_type_multiplier(creature2['creature_type'], creature1['creature_type'])

        # Track current HP
        hp1 = stats1['hp']
        hp2 = stats2['hp']

        # Battle log
        battle_log = []

        # Setup battle info
        name1 = creature1['nickname'] if creature1['nickname'] else creature1['name']
        name2 = creature2['nickname'] if creature2['nickname'] else creature2['name']

        battle_log.append("=== BATTLE START ===")
        battle_log.append(f"{name1} ({creature1['creature_type']}) vs {name2} ({creature2['creature_type']})")
        battle_log.append(f"{name1}: HP={hp1} ATK={stats1['attack']} DEF={stats1['defense']} SPD={stats1['speed']}")
        battle_log.append(f"{name2}: HP={hp2} ATK={stats2['attack']} DEF={stats2['defense']} SPD={stats2['speed']}")

        # Determine turn order (higher speed goes first)
        if stats1['speed'] > stats2['speed']:
            first = (creature1, stats1, 1)
            second = (creature2, stats2, 2)
            battle_log.append(f"{name1} moves first! (Speed: {stats1['speed']} vs {stats2['speed']})")
        elif stats2['speed'] > stats1['speed']:
            first = (creature2, stats2, 2)
            second = (creature1, stats1, 1)
            battle_log.append(f"{name2} moves first! (Speed: {stats2['speed']} vs {stats1['speed']})")
        else:
            # Tie - random
            if random.random() < 0.5:
                first = (creature1, stats1, 1)
                second = (creature2, stats2, 2)
                battle_log.append(f"{name1} moves first! (Speed tied, random)")
            else:
                first = (creature2, stats2, 2)
                second = (creature1, stats1, 1)
                battle_log.append(f"{name2} moves first! (Speed tied, random)")

        battle_log.append("")

        # Battle loop
        round_num = 0
        max_rounds = 100  # Safety limit

        while hp1 > 0 and hp2 > 0 and round_num < max_rounds:
            round_num += 1
            battle_log.append(f"--- Round {round_num} ---")

            # First attacker's turn
            if first[2] == 1:  # creature1 attacks
                damage = self.calculate_damage(stats1, stats2, type_mult_1_vs_2)
                hp2 -= damage
                advantage_text = " [TYPE ADVANTAGE]" if type_mult_1_vs_2 > 1.0 else ""
                battle_log.append(f"{name1} attacks {name2} for {damage} damage!{advantage_text}")
                battle_log.append(f"{name2}: {max(0, hp2)}/{stats2['hp']} HP")

                if hp2 <= 0:
                    break
            else:  # creature2 attacks
                damage = self.calculate_damage(stats2, stats1, type_mult_2_vs_1)
                hp1 -= damage
                advantage_text = " [TYPE ADVANTAGE]" if type_mult_2_vs_1 > 1.0 else ""
                battle_log.append(f"{name2} attacks {name1} for {damage} damage!{advantage_text}")
                battle_log.append(f"{name1}: {max(0, hp1)}/{stats1['hp']} HP")

                if hp1 <= 0:
                    break

            # Second attacker's turn
            if second[2] == 1:  # creature1 attacks
                damage = self.calculate_damage(stats1, stats2, type_mult_1_vs_2)
                hp2 -= damage
                advantage_text = " [TYPE ADVANTAGE]" if type_mult_1_vs_2 > 1.0 else ""
                battle_log.append(f"{name1} attacks {name2} for {damage} damage!{advantage_text}")
                battle_log.append(f"{name2}: {max(0, hp2)}/{stats2['hp']} HP")

                if hp2 <= 0:
                    break
            else:  # creature2 attacks
                damage = self.calculate_damage(stats2, stats1, type_mult_2_vs_1)
                hp1 -= damage
                advantage_text = " [TYPE ADVANTAGE]" if type_mult_2_vs_1 > 1.0 else ""
                battle_log.append(f"{name2} attacks {name1} for {damage} damage!{advantage_text}")
                battle_log.append(f"{name1}: {max(0, hp1)}/{stats1['hp']} HP")

                if hp1 <= 0:
                    break

            battle_log.append("")

        # Determine winner
        if hp1 > 0:
            winner = creature1
            loser = creature2
            battle_log.append(f"=== {name1} WINS! ===")
        else:
            winner = creature2
            loser = creature1
            battle_log.append(f"=== {name2} WINS! ===")

        battle_log.append(f"Battle lasted {round_num} round(s)")

        return {
            'winner': winner,
            'loser': loser,
            'rounds': round_num,
            'battle_log': battle_log,
            'final_hp': {
                creature1['id']: max(0, hp1),
                creature2['id']: max(0, hp2)
            }
        }

    def format_battle_summary(self, battle_result: Dict[str, Any], include_full_log: bool = False) -> str:
        """
        Format battle results for IRC display.

        Args:
            battle_result: Result dict from simulate_battle
            include_full_log: If True, include full battle log. If False, just summary.

        Returns:
            Formatted string for IRC
        """
        winner = battle_result['winner']
        loser = battle_result['loser']
        rounds = battle_result['rounds']

        winner_name = winner['nickname'] if winner['nickname'] else winner['name']
        loser_name = loser['nickname'] if loser['nickname'] else loser['name']

        if include_full_log:
            return "\n".join(battle_result['battle_log'])
        else:
            # Short summary
            return (f"{winner_name} defeats {loser_name} in {rounds} round(s)! "
                   f"(Final HP: {battle_result['final_hp'][winner['id']]})")
