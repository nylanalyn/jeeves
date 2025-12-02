# modules/absurdia_pkg/absurdia_main.py
# Main module for Absurdia creature battle game

import re
import random
import schedule
from pathlib import Path
from typing import Any, Dict, Optional, List, Tuple
from datetime import datetime, timedelta, timezone

from ..base import SimpleCommandModule
from .absurdia_db import AbsurdiaDatabase
from .absurdia_creatures import CreatureGenerator, CreatureCare
from .absurdia_combat import CombatEngine
from .absurdia_exploration import ExplorationManager

def setup(bot: Any) -> 'Absurdia':
    return Absurdia(bot)

class Absurdia(SimpleCommandModule):
    name = "absurdia"
    version = "1.1.0"
    description = "Creature catching and battling game with absurdist creatures"

    def __init__(self, bot: Any) -> None:
        # Initialize database
        db_path = bot.ROOT / "config" / "absurdia.db"
        templates_path = bot.ROOT / "config" / "absurdia_creatures.json"

        self.db = AbsurdiaDatabase(db_path, templates_path)

        # Initialize creature systems
        self.generator = CreatureGenerator(self.db.templates)
        self.care = CreatureCare(bot.config.get('absurdia', {}))  # Use bot, not self.bot
        self.combat = CombatEngine()
        self.exploration = ExplorationManager()

        super().__init__(bot)

        # Schedule hourly arena tournaments
        schedule.every().hour.at(":00").do(self._run_hourly_arena).tag(self.name)

        self.log_debug("Absurdia initialized successfully")

    def _register_commands(self) -> None:
        """Register all Absurdia commands"""

        # Info commands
        self.register_command(
            r"^\s*!(?:absurdia|abs)\s+help\s*$",
            self._cmd_help,
            name="absurdia help",
            description="Show Absurdia help and commands"
        )

        self.register_command(
            r"^\s*!guide(?:\s+(start|next|reset|1|2|3|4))?\s*$",
            self._cmd_guide,
            name="guide",
            description="Show beginner's guide to playing Absurdia (sent via DM)"
        )

        self.register_command(
            r"^\s*!(?:creatures|menagerie)\s*$",
            self._cmd_creatures,
            name="creatures",
            description="List your creature collection"
        )

        self.register_command(
            r"^\s*!stats\s+(\d+)\s*$",
            self._cmd_stats,
            name="stats",
            description="View detailed stats for a creature"
        )

        self.register_command(
            r"^\s*!coins?\s*$",
            self._cmd_coins,
            name="coins",
            description="Check your coin balance"
        )

        # Shop commands
        self.register_command(
            r"^\s*!shop\s*$",
            self._cmd_shop,
            name="shop",
            description="View available items for purchase"
        )

        self.register_command(
            r"^\s*!buy\s+(\w+)(?:\s+(\d+))?\s*$",
            self._cmd_buy,
            name="buy",
            description="Purchase items from the shop"
        )

        self.register_command(
            r"^\s*!inventory\s*$",
            self._cmd_inventory,
            name="inventory",
            description="View your inventory"
        )

        self.register_command(
            r"^\s*!explore\s*$",
            self._cmd_explore,
            name="explore",
            description="Explore the absurd world (4h cooldown)"
        )

        # Catching commands
        self.register_command(
            r"^\s*!catch(?:\s+(\w+))?\s*$",
            self._cmd_catch,
            name="catch",
            description="Set a trap or attempt hand-catching"
        )

        self.register_command(
            r"^\s*!check\s*$",
            self._cmd_check,
            name="check",
            description="Check trap status and collect creatures"
        )

        # Duplicate resolution commands
        self.register_command(
            r"^\s*!keep\s*$",
            self._cmd_keep,
            name="keep",
            description="Keep newly caught creature (release old one)"
        )

        self.register_command(
            r"^\s*!swap\s*$",
            self._cmd_keep,  # Same handler
            name="swap",
            description="Keep newly caught creature (alias for !keep)"
        )

        # Creature management commands
        self.register_command(
            r"^\s*!nickname\s+(\d+)\s+(.+)$",
            self._cmd_nickname,
            name="nickname",
            description="Set a nickname for your creature"
        )

        # Care commands
        self.register_command(
            r"^\s*!feed\s+(\d+)\s*$",
            self._cmd_feed,
            name="feed",
            description="Feed your creature (4h cooldown)"
        )

        self.register_command(
            r"^\s*!play\s+(\d+)\s*$",
            self._cmd_play,
            name="play",
            description="Play with your creature (2h cooldown)"
        )

        self.register_command(
            r"^\s*!pet\s+(\d+)\s*$",
            self._cmd_pet,
            name="pet",
            description="Pet your creature (1h cooldown)"
        )

        # Arena commands
        self.register_command(
            r"^\s*!submit\s+(\d+)\s*$",
            self._cmd_submit,
            name="submit",
            description="Submit creature to arena queue"
        )

        self.register_command(
            r"^\s*!withdraw\s*$",
            self._cmd_withdraw,
            name="withdraw",
            description="Withdraw creature from arena queue"
        )

        self.register_command(
            r"^\s*!arena\s*$",
            self._cmd_arena,
            name="arena",
            description="View current arena queue"
        )

    # ============= COMMAND HANDLERS =============

    def _cmd_help(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        """Show help information"""
        help_text = """=== ABSURDIA: Creature Battle Game ===
Catch absurdist creatures, care for them, and battle in the arena!

INFO:
  !coins - Check your balance
  !creatures - List your collection
  !stats <id> - View creature details
  !nickname <id> <name> - Rename a creature

CATCHING:
  !shop - View available traps and prices
  !buy <trap_type> [qty] - Purchase traps
  !inventory - View your items
  !catch - Hand-catch attempt (5% success, weak stats)
  !catch <trap_type> - Set a trap (basic/standard/premium/deluxe)
  !check - Check trap status and collect creature

DUPLICATES:
  !keep - Keep new creature (during duplicate catch)
  !swap - Same as !keep

CARE (earn coins & boost stats!):
  !feed <id> - Feed creature (4h cooldown, costs 10, +5 happy, +stats)
  !play <id> - Play with creature (2h cooldown, costs 5, +3 happy)
  !pet <id> - Pet creature (1h cooldown, free, +2 happy)
  Note: Care rewards capped at 10 actions/day (resets at midnight UTC)

ARENA (battle for glory!):
  !submit <id> - Enter creature in hourly arena tournament
  !withdraw - Remove your creature from arena queue
  !arena - View current arena queue
  Hourly tournaments: Win 150 coins, Lose 30 coins

RARITIES: Common, Uncommon, Rare, Legendary, Feral (hand-caught)
TYPES: Sturdy Nonsense > Sharp Weird > Flimsy Chaos > Sturdy Nonsense
"""
        self.safe_reply(connection, event, help_text)
        return True

    def _cmd_guide(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        """Show beginner's guide to playing Absurdia (sent via DM in parts)"""
        user_id = self.bot.get_user_id(username)
        action = match.group(1) if match.group(1) else None

        # Get guide parts
        guide_parts = [
            # Part 1: Introduction and First Steps
            """=== ABSURDIA GUIDE - Part 1/4: Getting Started ===

WHAT IS ABSURDIA?
Absurdia is a creature collecting and battling game featuring bizarre,
absurdist creatures. Catch them, care for them, and battle in the arena!

YOUR FIRST STEPS:

1. CHECK YOUR STARTING COINS
   Type: !coins
   You start with 300 coins to begin your adventure.

2. CATCH YOUR FIRST CREATURE
   Free option: !catch
   - Hand-catch attempt (5% success rate)
   - Creatures have weaker stats (60% of normal)
   - Good for testing but not recommended long-term

   Better option: Buy a trap
   - !buy basic (costs 50 coins)
   - !catch basic (set trap, wait 3 hours)
   - !check (collect your creature when ready)

Type !guide next to continue to Part 2...""",

            # Part 2: Collection Management
            """=== ABSURDIA GUIDE - Part 2/4: Managing Your Collection ===

VIEWING YOUR CREATURES:
- !creatures - See your entire collection
- !stats <id> - Detailed info on a specific creature
- !nickname <id> <name> - Give your creature a custom name

IMPORTANT RULES:
- You can only have ONE of each creature species
- If you catch a duplicate, you'll be asked to choose:
  - !keep - Keep the new one (release old one, get partial refund)
  - Wait 30 seconds - Keep your current one (auto-default)
- Compare stats carefully before deciding!

CREATURE STATS:
- HP: Health points for battles
- Attack: Damage dealt in battles
- Defense: Reduces incoming damage
- Speed: Determines who attacks first
- Happiness: Affects arena performance (0-100)

Type !guide next to continue to Part 3...""",

            # Part 3: Economy and Care
            """=== ABSURDIA GUIDE - Part 3/4: Earning Coins & Care ===

CARE ACTIONS (Boost stats & earn coins!):

!feed <id> - Feed your creature
- Costs: 10 coins
- Earns: 15 coins (net +5)
- Bonus: +5 happiness, +1 random stat
- Cooldown: 4 hours

!play <id> - Play with your creature
- Costs: 5 coins
- Earns: 8 coins (net +3)
- Bonus: +3 happiness, +1 ATK or SPD
- Cooldown: 2 hours

!pet <id> - Pet your creature
- Costs: FREE
- Earns: 3 coins
- Bonus: +2 happiness
- Cooldown: 1 hour

DAILY LIMIT: Coin rewards capped at 10 care actions per day
(resets at midnight UTC). After cap, you only pay costs with no earnings.

Type !guide next to continue to Part 4...""",

            # Part 4: Arena and Strategy
            """=== ABSURDIA GUIDE - Part 4/4: Arena & Strategy ===

ARENA BATTLES (Hourly tournaments!):
- !submit <id> - Enter your creature in the arena queue
- !arena - View current queue
- !withdraw - Remove your creature from queue
- Battles run automatically at the top of every hour
- Win: +150 coins | Lose: +30 coins

CREATURE TYPES (Rock-Paper-Scissors):
- Sturdy Nonsense beats Sharp Weird
- Sharp Weird beats Flimsy Chaos
- Flimsy Chaos beats Sturdy Nonsense

TRAP TIERS (Better traps = Better creatures):
- Basic: 50 coins, 3h wait → Common/Uncommon only
- Standard: 100 coins, 6h wait → Adds Rare chance
- Premium: 200 coins, 12h wait → All rarities
- Deluxe: 400 coins, 24h wait → Best Legendary odds

PRO TIPS:
- Keep happiness at 100 for +10 HP and +5 ATK/DEF in arena
- Feed often for permanent stat boosts
- Hand-catching is free but gives much weaker creatures
- Care actions build stats over time - invest in your favorites!

Ready to play? Type !coins to start your adventure!
For full command list: !absurdia help"""
        ]

        # Get or initialize guide progress
        guide_progress = self.get_state("guide_progress", {})
        current_part = guide_progress.get(user_id, 0)

        # Determine which part to show
        if action in ['start', 'reset', '1']:
            current_part = 0
        elif action == 'next':
            current_part = min(current_part + 1, len(guide_parts) - 1)
        elif action in ['2', '3', '4']:
            current_part = int(action) - 1

        # Ensure part is valid
        current_part = max(0, min(current_part, len(guide_parts) - 1))

        # Send guide part via DM (split into lines for IRC)
        guide_text = guide_parts[current_part]
        for line in guide_text.split('\n'):
            connection.privmsg(username, line)

        # Update progress to next part (for future !guide next calls)
        next_part = current_part + 1
        if next_part < len(guide_parts):
            guide_progress[user_id] = next_part
        else:
            # Reset to beginning after completing all parts
            guide_progress[user_id] = 0

        self.set_state("guide_progress", guide_progress)
        self.save_state()

        # Confirm in channel
        part_num = current_part + 1
        total_parts = len(guide_parts)

        if part_num < total_parts:
            confirmation = f"{self.bot.title_for(username)}, guide part {part_num}/{total_parts} sent via DM! Type !guide next to continue."
        else:
            confirmation = f"{self.bot.title_for(username)}, guide part {part_num}/{total_parts} (final) sent via DM!"

        self.safe_reply(connection, event, confirmation)
        return True

    def _cmd_creatures(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        """List player's creature collection"""
        user_id = self.bot.get_user_id(username)
        player = self.db.get_player(user_id, username)

        creatures = self.db.get_player_creatures(user_id)

        if not creatures:
            owned, total = self.db.get_collection_progress(user_id)
            self.safe_reply(
                connection, event,
                f"{self.bot.title_for(username)}, you have no creatures yet. "
                f"You have {player['coins']} coins to start catching! (0/{total} collected)"
            )
            return True

        owned, total = self.db.get_collection_progress(user_id)

        lines = [f"=== {username}'s Menagerie ({owned}/{total}) ==="]

        for creature in creatures:
            display_name = creature['nickname'] if creature['nickname'] else creature['name']
            status = "in arena" if creature['submitted_to_arena'] else "available"

            line = (f"[{creature['id']}] {display_name} ({creature['name']}) - "
                   f"{creature['creature_type']} - "
                   f"W:{creature['total_wins']} L:{creature['total_losses']} - "
                   f"{status}")
            lines.append(line)

        self.safe_reply(connection, event, "\n".join(lines))
        return True

    def _cmd_stats(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        """Show detailed stats for a creature"""
        user_id = self.bot.get_user_id(username)
        creature_id = int(match.group(1))

        creature = self.db.get_creature(creature_id)

        if not creature:
            self.safe_reply(connection, event, f"Creature #{creature_id} not found.")
            return True

        if creature['owner_id'] != user_id:
            self.safe_reply(connection, event, "That's not your creature!")
            return True

        # Calculate total stats
        total_hp = creature['base_hp'] + creature['bonus_hp']
        total_attack = creature['base_attack'] + creature['bonus_attack']
        total_defense = creature['base_defense'] + creature['bonus_defense']
        total_speed = creature['base_speed'] + creature['bonus_speed']

        display_name = creature['nickname'] if creature['nickname'] else creature['name']

        lines = [
            f"=== {display_name} ===",
            f"Species: {creature['name']} | Rarity: {creature['rarity']}",
            f"Type: {creature['creature_type']} | Happiness: {creature['happiness']}/100",
            f"",
            f"Stats (Base + Bonus = Total):",
            f"  HP:      {creature['base_hp']:3} + {creature['bonus_hp']:2} = {total_hp}",
            f"  Attack:  {creature['base_attack']:3} + {creature['bonus_attack']:2} = {total_attack}",
            f"  Defense: {creature['base_defense']:3} + {creature['bonus_defense']:2} = {total_defense}",
            f"  Speed:   {creature['base_speed']:3} + {creature['bonus_speed']:2} = {total_speed}",
            f"",
            f"Record: {creature['total_wins']} wins, {creature['total_losses']} losses",
        ]

        # Show care status
        if creature['submitted_to_arena']:
            lines.append("Status: Currently in arena queue")
        else:
            lines.append("Status: Available for care and battles")

        self.safe_reply(connection, event, "\n".join(lines))
        return True

    def _cmd_coins(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        """Show player's coin balance"""
        user_id = self.bot.get_user_id(username)
        player = self.db.get_player(user_id, username)

        owned, total = self.db.get_collection_progress(user_id)

        self.safe_reply(
            connection, event,
            f"{self.bot.title_for(username)}, you have {player['coins']} coins. "
            f"Collection: {owned}/{total} creatures."
        )
        return True

    def _cmd_shop(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        """Display shop with available items"""
        user_id = self.bot.get_user_id(username)
        player = self.db.get_player(user_id, username)

        config = self.bot.config.get('absurdia', {})
        trap_prices = config.get('trap_prices', {})
        trap_timers = config.get('trap_timers', {})

        lines = [
            "=== ABSURDIA SHOP ===",
            f"Your coins: {player['coins']}",
            "",
            "TRAPS (usage: !buy <trap_name>):",
        ]

        for trap_type in ['basic', 'standard', 'premium', 'deluxe']:
            price = trap_prices.get(trap_type, 50)
            timer_sec = trap_timers.get(trap_type, 10800)
            timer_hours = timer_sec / 3600

            rarities = {
                'basic': 'Common/Uncommon',
                'standard': 'Common/Uncommon/Rare',
                'premium': 'All rarities',
                'deluxe': 'All rarities (best legendary chance)'
            }

            rarity_info = rarities.get(trap_type, 'Various')
            lines.append(f"  {trap_type}: {price} coins - {timer_hours}h wait - {rarity_info}")

        lines.append("")
        lines.append("TIP: No traps or coins? Try !catch with no arguments for hand-catching!")

        self.safe_reply(connection, event, "\n".join(lines))
        return True

    def _cmd_buy(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        """Purchase items from shop"""
        user_id = self.bot.get_user_id(username)
        player = self.db.get_player(user_id, username)

        item_name = match.group(1).lower()
        quantity_str = match.group(2)
        quantity = int(quantity_str) if quantity_str else 1

        if quantity < 1:
            self.safe_reply(connection, event, "Quantity must be at least 1.")
            return True

        config = self.bot.config.get('absurdia', {})
        trap_prices = config.get('trap_prices', {})

        # Check if it's a trap
        if item_name in trap_prices:
            price = trap_prices[item_name]
            total_cost = price * quantity

            if player['coins'] < total_cost:
                self.safe_reply(
                    connection, event,
                    f"Not enough coins! {item_name} traps cost {price} each. "
                    f"You need {total_cost} but have {player['coins']}."
                )
                return True

            # Purchase traps
            self.db.update_player_coins(user_id, -total_cost)
            self.db.add_item(user_id, 'trap', item_name, quantity)

            trap_word = "trap" if quantity == 1 else "traps"
            new_balance = player['coins'] - total_cost

            self.safe_reply(
                connection, event,
                f"{self.bot.title_for(username)}, you purchased {quantity} {item_name} {trap_word} "
                f"for {total_cost} coins. New balance: {new_balance} coins."
            )
            return True

        # Unknown item
        self.safe_reply(
            connection, event,
            f"'{item_name}' is not available in the shop. Use !shop to see available items."
        )
        return True

    def _cmd_inventory(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        """Show player's inventory"""
        user_id = self.bot.get_user_id(username)

        inventory = self.db.get_inventory(user_id)

        if not inventory:
            self.safe_reply(
                connection, event,
                f"{self.bot.title_for(username)}, your inventory is empty. Visit !shop to buy traps!"
            )
            return True

        lines = [f"=== {username}'s Inventory ==="]

        # Group by type
        by_type = {}
        for item in inventory:
            item_type = item['item_type']
            if item_type not in by_type:
                by_type[item_type] = []
            by_type[item_type].append(item)

        for item_type, items in by_type.items():
            lines.append(f"\\n{item_type.upper()}:")
            for item in items:
                lines.append(f"  {item['item_name']}: {item['quantity']}")

        self.safe_reply(connection, event, "\\n".join(lines))
        return True

    def _cmd_explore(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        """Explore for items and flavor"""
        user_id = self.bot.get_user_id(username)
        player = self.db.get_player(user_id, username)

        # Check cooldown (4 hours)
        last_explored_str = player.get('last_explored')
        if last_explored_str:
            try:
                last_explored = datetime.fromisoformat(last_explored_str.replace('Z', '+00:00'))
                now = datetime.now(timezone.utc)
                elapsed = (now - last_explored).total_seconds()
                cooldown = 4 * 3600 # 4 hours

                if elapsed < cooldown:
                    remaining = int(cooldown - elapsed)
                    hours = remaining // 3600
                    minutes = (remaining % 3600) // 60
                    
                    self.safe_reply(
                        connection, event,
                        f"{self.bot.title_for(username)}, you are too tired to explore. "
                        f"Rest for {hours}h {minutes}m."
                    )
                    return True
            except ValueError:
                pass # Invalid timestamp, allow explore

        # Update timestamp
        self.db.update_player_exploration(user_id)

        # Roll for reward
        reward = self.exploration.roll_exploration_reward()
        flavor = self.exploration.get_exploration_flavor()

        if reward:
            self.db.add_item(user_id, 'trap', reward, 1)
            self.safe_reply(
                connection, event,
                f"{flavor}\\n"
                f"Wait! You found a {reward} trap!"
            )
        else:
            self.safe_reply(
                connection, event,
                f"{flavor}"
            )
        
        return True

    def _cmd_catch(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        """Set a trap or attempt hand-catching"""
        user_id = self.bot.get_user_id(username)
        player = self.db.get_player(user_id, username)

        trap_quality = match.group(1).lower() if match.group(1) else None

        config = self.bot.config.get('absurdia', {})

        # Hand-catching if no trap specified
        if not trap_quality:
            hand_catch_config = config.get('hand_catch', {})

            if not hand_catch_config.get('enabled', True):
                self.safe_reply(connection, event, "Hand-catching is currently disabled.")
                return True

            success_rate = hand_catch_config.get('success_rate', 0.05)
            stat_penalty = hand_catch_config.get('stat_penalty', 0.6)

            result = self.generator.hand_catch_attempt(success_rate, stat_penalty)

            if not result:
                # Failed - get random failure message
                common_templates = [self.db.templates[name] for name in self.generator.by_rarity.get('Common', [])]
                if common_templates:
                    template = random.choice(common_templates)
                    flavor = self.generator.get_catch_flavor(template, is_hand_catch=True, success=False)
                else:
                    flavor = "You lunge desperately but catch only air."

                self.safe_reply(connection, event, f"{self.bot.title_for(username)}, {flavor}")
                return True

            # Success! Check for duplicate
            creature_name, rarity, creature_type, hp, attack, defense, speed, template = result

            if self.db.has_creature_type(user_id, creature_name):
                # Duplicate - create pending catch
                timeout = config.get('duplicate_handling', {}).get('comparison_timeout_seconds', 30)
                self.db.create_pending_catch(
                    user_id, creature_name, rarity, creature_type,
                    hp, attack, defense, speed, 'hand', timeout
                )

                # Show comparison
                return self._show_duplicate_comparison(connection, event, username, user_id, creature_name)

            # Not a duplicate - create creature directly
            creature_id = self.db.create_creature(
                user_id, creature_name, rarity, creature_type,
                hp, attack, defense, speed
            )

            flavor = self.generator.get_catch_flavor(template, is_hand_catch=True, success=True)

            self.safe_reply(
                connection, event,
                f"{flavor}\n"
                f"Caught: {creature_name} (#{creature_id}) - {rarity} {creature_type}\n"
                f"Stats: HP:{hp} ATK:{attack} DEF:{defense} SPD:{speed}"
            )
            return True

        # Trap catching
        trap_prices = config.get('trap_prices', {})
        trap_timers = config.get('trap_timers', {})

        if trap_quality not in trap_prices:
            self.safe_reply(
                connection, event,
                f"'{trap_quality}' is not a valid trap type. Options: basic, standard, premium, deluxe"
            )
            return True

        # Check if player has trap
        has_trap = self.db.get_item_count(user_id, 'trap', trap_quality) > 0

        if not has_trap:
            price = trap_prices[trap_quality]
            self.safe_reply(
                connection, event,
                f"You don't have any {trap_quality} traps. Buy one for {price} coins with: !buy {trap_quality}"
            )
            return True

        # Check if player already has a trap set
        active_traps = self.db.get_active_traps(user_id)
        if active_traps:
            self.safe_reply(
                connection, event,
                f"You already have a trap set! Use !check to see its status."
            )
            return True

        # Set trap
        timer_seconds = trap_timers.get(trap_quality, 10800)
        ready_time = datetime.now(timezone.utc) + timedelta(seconds=timer_seconds)

        self.db.create_trap(user_id, trap_quality, ready_time)
        self.db.remove_item(user_id, 'trap', trap_quality, 1)

        hours = timer_seconds / 3600
        self.safe_reply(
            connection, event,
            f"{self.bot.title_for(username)}, you set a {trap_quality} trap. "
            f"Check back in {hours} hours with !check to collect your creature!"
        )
        return True

    def _cmd_check(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        """Check trap status and collect creatures"""
        user_id = self.bot.get_user_id(username)

        active_traps = self.db.get_active_traps(user_id)

        if not active_traps:
            self.safe_reply(
                connection, event,
                f"{self.bot.title_for(username)}, you have no active traps. Use !catch <trap_type> to set one!"
            )
            return True

        trap = active_traps[0]  # Only one trap at a time

        # Check if ready
        ready_time = datetime.fromisoformat(trap['ready_at'].replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)

        if now < ready_time:
            remaining = (ready_time - now).total_seconds()
            hours = int(remaining // 3600)
            minutes = int((remaining % 3600) // 60)

            self.safe_reply(
                connection, event,
                f"Your {trap['trap_quality']} trap is not ready yet. "
                f"Wait {hours}h {minutes}m more."
            )
            return True

        # Trap is ready! Generate creature
        creature_name, rarity, creature_type, hp, attack, defense, speed, template = \
            self.generator.generate_creature(trap['trap_quality'])

        # Mark trap as collected
        self.db.mark_trap_collected(trap['id'])

        # Check for duplicate
        if self.db.has_creature_type(user_id, creature_name):
            # Duplicate - create pending catch
            config = self.bot.config.get('absurdia', {})
            timeout = config.get('duplicate_handling', {}).get('comparison_timeout_seconds', 30)

            self.db.create_pending_catch(
                user_id, creature_name, rarity, creature_type,
                hp, attack, defense, speed, trap['trap_quality'], timeout
            )

            # Show comparison
            return self._show_duplicate_comparison(connection, event, username, user_id, creature_name)

        # Not a duplicate - create creature
        creature_id = self.db.create_creature(
            user_id, creature_name, rarity, creature_type,
            hp, attack, defense, speed
        )

        flavor = self.generator.get_catch_flavor(template)

        self.safe_reply(
            connection, event,
            f"{flavor}\n"
            f"Caught: {creature_name} (#{creature_id}) - {rarity} {creature_type}\n"
            f"Stats: HP:{hp} ATK:{attack} DEF:{defense} SPD:{speed}"
        )
        return True

    def _show_duplicate_comparison(self, connection: Any, event: Any, username: str, user_id: str, creature_name: str) -> bool:
        """Show comparison UI for duplicate creature"""
        # Get current creature
        creatures = self.db.get_player_creatures(user_id)
        current = None
        for c in creatures:
            if c['name'] == creature_name:
                current = c
                break

        if not current:
            # Shouldn't happen but handle it
            self.safe_reply(connection, event, "Error: Could not find current creature for comparison.")
            return True

        # Get pending catch
        pending = self.db.get_pending_catch(user_id)
        if not pending:
            self.safe_reply(connection, event, "Error: Pending catch not found.")
            return True

        # Build comparison
        current_total_hp = current['base_hp'] + current['bonus_hp']
        current_total_atk = current['base_attack'] + current['bonus_attack']
        current_total_def = current['base_defense'] + current['bonus_defense']
        current_total_spd = current['base_speed'] + current['bonus_speed']

        display_name = current['nickname'] if current['nickname'] else creature_name

        lines = [
            f"You caught a {creature_name}! You already have one.",
            "",
            f"CURRENT (ID: {current['id']}, {display_name}):",
            f"├─ HP: {current_total_hp}, Attack: {current_total_atk}, Defense: {current_total_def}, Speed: {current_total_spd}",
            f"├─ Happiness: {current['happiness']}",
            f"├─ Wins: {current['total_wins']}, Losses: {current['total_losses']}",
            f"└─ Type: {current['creature_type']}",
            "",
            f"NEW CATCH:",
            f"├─ HP: {pending['new_hp']}, Attack: {pending['new_attack']}, Defense: {pending['new_defense']}, Speed: {pending['new_speed']}",
            f"├─ Happiness: 50 (new catch)",
            f"├─ Wins: 0, Losses: 0",
            f"└─ Type: {pending['new_creature_type']}",
            "",
            "Keep new (!keep) or keep current (defaults to current in 30s)?"
        ]

        self.safe_reply(connection, event, "\n".join(lines))
        return True

    def _cmd_keep(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        """Resolve pending catch - keep new creature"""
        user_id = self.bot.get_user_id(username)

        pending = self.db.get_pending_catch(user_id)

        if not pending:
            self.safe_reply(
                connection, event,
                "You have no pending creature catch. This command is only used during duplicate catches."
            )
            return True

        config = self.bot.config.get('absurdia', {})
        refund_percent = config.get('duplicate_handling', {}).get('trap_refund_percent', 0.5)

        # Resolve - keep new
        refund, new_creature_id = self.db.resolve_pending_catch(user_id, keep_new=True, trap_refund_percent=refund_percent)

        if new_creature_id:
            self.safe_reply(
                connection, event,
                f"{self.bot.title_for(username)}, you kept the new {pending['creature_name']} (#{new_creature_id})! "
                f"Your old one was released. Refund: {refund} coins."
            )
        else:
            self.safe_reply(connection, event, "Error resolving catch.")

        return True

    def _cmd_nickname(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        """Set a nickname for a creature"""
        user_id = self.bot.get_user_id(username)
        creature_id = int(match.group(1))
        nickname = match.group(2).strip()

        # Validate nickname length
        if len(nickname) > 30:
            self.safe_reply(connection, event, "Nickname must be 30 characters or less.")
            return True

        creature = self.db.get_creature(creature_id)

        if not creature:
            self.safe_reply(connection, event, f"Creature #{creature_id} not found.")
            return True

        if creature['owner_id'] != user_id:
            self.safe_reply(connection, event, "That's not your creature!")
            return True

        # Set nickname
        self.db.set_creature_nickname(creature_id, nickname)

        self.safe_reply(
            connection, event,
            f"{self.bot.title_for(username)}, you nicknamed your {creature['name']} '{nickname}'"
        )
        return True

    def _cmd_feed(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        """Feed a creature"""
        user_id = self.bot.get_user_id(username)
        creature_id = int(match.group(1))

        creature = self.db.get_creature(creature_id)

        if not creature:
            self.safe_reply(connection, event, f"Creature #{creature_id} not found.")
            return True

        if creature['owner_id'] != user_id:
            self.safe_reply(connection, event, "That's not your creature!")
            return True

        # Check if can care (not in arena)
        can_care, error_msg = self.care.can_care_for(creature)
        if not can_care:
            self.safe_reply(connection, event, error_msg)
            return True

        # Check cooldown
        can_feed, cooldown_msg = self.care.check_care_cooldown(creature, 'feed')
        if not can_feed:
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, {cooldown_msg}")
            return True

        # Check if player has coins
        player = self.db.get_player(user_id, username)
        config = self.bot.config.get('absurdia', {})
        cost = config.get('care_costs', {}).get('feed', 10)

        if player['coins'] < cost:
            self.safe_reply(
                connection, event,
                f"Not enough coins! Feeding costs {cost} coins. You have {player['coins']}."
            )
            return True

        # Check daily care cap
        daily_care_cap = config.get('daily_care_cap', 10)
        current_care_count = self.db.check_and_reset_daily_care(user_id)

        # Perform feeding
        net_coins, happiness_gain, stat_gain = self.care.calculate_care_reward('feed')

        # Apply care cap to coin rewards
        coins_earned = net_coins
        cap_message = ""
        if current_care_count >= daily_care_cap:
            coins_earned = -cost  # Only subtract cost, no earnings
            cap_message = " (daily care cap reached: 0 coins earned)"

        # Update creature
        new_happiness = min(100, creature['happiness'] + happiness_gain)
        self.db.update_creature_happiness(creature_id, new_happiness)
        self.db.update_creature_care_timestamp(creature_id, 'feed')

        # Apply random stat boost
        stat_to_boost = random.choice(['hp', 'attack', 'defense', 'speed'])
        current_bonus = creature[f'bonus_{stat_to_boost}']
        new_bonus = current_bonus + stat_gain

        # Update stat in database
        with self.db._lock:
            conn = self.db._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                f'UPDATE creatures SET bonus_{stat_to_boost} = ? WHERE id = ?',
                (new_bonus, creature_id)
            )
            conn.commit()
            conn.close()

        # Update player coins and care count
        self.db.update_player_coins(user_id, coins_earned)
        if current_care_count < daily_care_cap:
            self.db.increment_daily_care(user_id)

        # Get flavor text
        template = self.db.templates.get(creature['name'])
        flavor = self.generator.get_care_flavor(template, 'feed') if template else "You feed the creature."

        display_name = creature['nickname'] if creature['nickname'] else creature['name']

        self.safe_reply(
            connection, event,
            f"{flavor}\n"
            f"{display_name}: +{happiness_gain} happiness ({new_happiness}/100), "
            f"+{stat_gain} {stat_to_boost.upper()} | "
            f"Coins: {coins_earned:+d}{cap_message}"
        )
        return True

    def _cmd_play(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        """Play with a creature"""
        user_id = self.bot.get_user_id(username)
        creature_id = int(match.group(1))

        creature = self.db.get_creature(creature_id)

        if not creature:
            self.safe_reply(connection, event, f"Creature #{creature_id} not found.")
            return True

        if creature['owner_id'] != user_id:
            self.safe_reply(connection, event, "That's not your creature!")
            return True

        # Check if can care (not in arena)
        can_care, error_msg = self.care.can_care_for(creature)
        if not can_care:
            self.safe_reply(connection, event, error_msg)
            return True

        # Check cooldown
        can_play, cooldown_msg = self.care.check_care_cooldown(creature, 'play')
        if not can_play:
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, {cooldown_msg}")
            return True

        # Check if player has coins
        player = self.db.get_player(user_id, username)
        config = self.bot.config.get('absurdia', {})
        cost = config.get('care_costs', {}).get('play', 5)

        if player['coins'] < cost:
            self.safe_reply(
                connection, event,
                f"Not enough coins! Playing costs {cost} coins. You have {player['coins']}."
            )
            return True

        # Check daily care cap
        daily_care_cap = config.get('daily_care_cap', 10)
        current_care_count = self.db.check_and_reset_daily_care(user_id)

        # Perform playing
        net_coins, happiness_gain, stat_gain = self.care.calculate_care_reward('play')

        # Apply care cap to coin rewards
        coins_earned = net_coins
        cap_message = ""
        if current_care_count >= daily_care_cap:
            coins_earned = -cost  # Only subtract cost, no earnings
            cap_message = " (daily care cap reached: 0 coins earned)"

        # Update creature
        new_happiness = min(100, creature['happiness'] + happiness_gain)
        self.db.update_creature_happiness(creature_id, new_happiness)
        self.db.update_creature_care_timestamp(creature_id, 'play')

        # Boost attack or speed
        stat_to_boost = random.choice(['attack', 'speed'])
        current_bonus = creature[f'bonus_{stat_to_boost}']
        new_bonus = current_bonus + stat_gain

        # Update stat in database
        with self.db._lock:
            conn = self.db._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                f'UPDATE creatures SET bonus_{stat_to_boost} = ? WHERE id = ?',
                (new_bonus, creature_id)
            )
            conn.commit()
            conn.close()

        # Update player coins and care count
        self.db.update_player_coins(user_id, coins_earned)
        if current_care_count < daily_care_cap:
            self.db.increment_daily_care(user_id)

        # Get flavor text
        template = self.db.templates.get(creature['name'])
        flavor = self.generator.get_care_flavor(template, 'play') if template else "You play with the creature."

        display_name = creature['nickname'] if creature['nickname'] else creature['name']

        self.safe_reply(
            connection, event,
            f"{flavor}\n"
            f"{display_name}: +{happiness_gain} happiness ({new_happiness}/100), "
            f"+{stat_gain} {stat_to_boost.upper()} | "
            f"Coins: {coins_earned:+d}{cap_message}"
        )
        return True

    def _cmd_pet(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        """Pet a creature"""
        user_id = self.bot.get_user_id(username)
        creature_id = int(match.group(1))

        creature = self.db.get_creature(creature_id)

        if not creature:
            self.safe_reply(connection, event, f"Creature #{creature_id} not found.")
            return True

        if creature['owner_id'] != user_id:
            self.safe_reply(connection, event, "That's not your creature!")
            return True

        # Check if can care (not in arena)
        can_care, error_msg = self.care.can_care_for(creature)
        if not can_care:
            self.safe_reply(connection, event, error_msg)
            return True

        # Check cooldown
        can_pet, cooldown_msg = self.care.check_care_cooldown(creature, 'pet')
        if not can_pet:
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, {cooldown_msg}")
            return True

        # Check daily care cap
        player = self.db.get_player(user_id, username)
        config = self.bot.config.get('absurdia', {})
        daily_care_cap = config.get('daily_care_cap', 10)
        current_care_count = self.db.check_and_reset_daily_care(user_id)

        # Perform petting
        net_coins, happiness_gain, stat_gain = self.care.calculate_care_reward('pet')

        # Apply care cap to coin rewards
        coins_earned = net_coins
        cap_message = ""
        if current_care_count >= daily_care_cap:
            coins_earned = 0  # No earnings when capped (pet has no cost)
            cap_message = " (daily care cap reached: 0 coins earned)"

        # Update creature
        new_happiness = min(100, creature['happiness'] + happiness_gain)
        self.db.update_creature_happiness(creature_id, new_happiness)
        self.db.update_creature_care_timestamp(creature_id, 'pet')

        # Update player coins and care count
        self.db.update_player_coins(user_id, coins_earned)
        if current_care_count < daily_care_cap:
            self.db.increment_daily_care(user_id)

        # Get flavor text
        template = self.db.templates.get(creature['name'])
        flavor = self.generator.get_care_flavor(template, 'pet') if template else "You pet the creature."

        display_name = creature['nickname'] if creature['nickname'] else creature['name']

        self.safe_reply(
            connection, event,
            f"{flavor}\n"
            f"{display_name}: +{happiness_gain} happiness ({new_happiness}/100) | "
            f"Coins: {coins_earned:+d}{cap_message}"
        )
        return True

    def _cmd_submit(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        """Submit a creature to the arena queue"""
        user_id = self.bot.get_user_id(username)
        creature_id = int(match.group(1))

        creature = self.db.get_creature(creature_id)

        if not creature:
            self.safe_reply(connection, event, f"Creature #{creature_id} not found.")
            return True

        if creature['owner_id'] != user_id:
            self.safe_reply(connection, event, "That's not your creature!")
            return True

        # Check if already submitted
        if creature['submitted_to_arena']:
            self.safe_reply(connection, event, f"That creature is already in the arena queue!")
            return True

        # Check if player already has a creature in arena
        player_creatures = self.db.get_player_creatures(user_id)
        for c in player_creatures:
            if c['submitted_to_arena']:
                other_name = c['nickname'] if c['nickname'] else c['name']
                self.safe_reply(
                    connection, event,
                    f"You already have {other_name} in the arena queue! Use !withdraw first."
                )
                return True

        # Submit to arena
        self.db.submit_creature_to_arena(creature_id, True)

        display_name = creature['nickname'] if creature['nickname'] else creature['name']

        self.safe_reply(
            connection, event,
            f"{self.bot.title_for(username)}, {display_name} has been submitted to the arena queue! "
            f"The next tournament will run at the top of the hour. Use !withdraw to remove them."
        )
        return True

    def _cmd_withdraw(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        """Withdraw creature from arena queue"""
        user_id = self.bot.get_user_id(username)

        # Find submitted creature
        player_creatures = self.db.get_player_creatures(user_id)
        submitted_creature = None
        for c in player_creatures:
            if c['submitted_to_arena']:
                submitted_creature = c
                break

        if not submitted_creature:
            self.safe_reply(
                connection, event,
                f"{self.bot.title_for(username)}, you don't have any creatures in the arena queue."
            )
            return True

        # Withdraw
        self.db.submit_creature_to_arena(submitted_creature['id'], False)

        display_name = submitted_creature['nickname'] if submitted_creature['nickname'] else submitted_creature['name']

        self.safe_reply(
            connection, event,
            f"{self.bot.title_for(username)}, {display_name} has been withdrawn from the arena."
        )
        return True

    def _cmd_arena(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        """View current arena queue"""
        # Get all creatures submitted to arena
        submitted = self.db.get_arena_queue()

        if not submitted:
            self.safe_reply(
                connection, event,
                "The arena queue is currently empty. Use !submit <creature_id> to enter!"
            )
            return True

        lines = [f"=== ARENA QUEUE ({len(submitted)} creature(s)) ==="]

        for creature in submitted:
            owner = self.db.get_player(creature['owner_id'], "Unknown")
            display_name = creature['nickname'] if creature['nickname'] else creature['name']

            # Calculate effective stats for display
            stats = {
                'hp': creature['base_hp'] + creature['bonus_hp'] + (creature['happiness'] // 10),
                'attack': creature['base_attack'] + creature['bonus_attack'] + (creature['happiness'] // 20),
                'defense': creature['base_defense'] + creature['bonus_defense'] + (creature['happiness'] // 20),
                'speed': creature['base_speed'] + creature['bonus_speed']
            }

            line = (f"{owner['username']}'s {display_name} - {creature['creature_type']} - "
                   f"HP:{stats['hp']} ATK:{stats['attack']} DEF:{stats['defense']} SPD:{stats['speed']} - "
                   f"Record: {creature['total_wins']}W/{creature['total_losses']}L")
            lines.append(line)

        lines.append("")
        lines.append("Next tournament runs at the top of the hour!")

        self.safe_reply(connection, event, "\n".join(lines))
        return True

    # ============= ARENA AUTOMATION =============

    def _run_hourly_arena(self) -> None:
        """Run the hourly arena tournament (called by scheduler)"""
        try:
            self.log_debug("Starting hourly arena tournament")

            # --- HAPPINESS DECAY LOOP ---
            all_creatures = self.db.get_all_creatures()
            decay_count = 0
            for creature in all_creatures:
                # Calculate new happiness
                is_in_arena = bool(creature['submitted_to_arena'])
                new_happiness = self.care.apply_happiness_decay(creature, is_in_arena)
                
                if new_happiness != creature['happiness']:
                    self.db.update_creature_happiness(creature['id'], new_happiness)
                    decay_count += 1
            
            if decay_count > 0:
                self.log_debug(f"Applied happiness decay to {decay_count} creatures")
            # ----------------------------

            # Get all creatures in arena queue
            queue = self.db.get_arena_queue()

            if not queue:
                self.log_debug("No creatures in arena queue, skipping tournament")
                return

            # Get arena channel from config
            config = self.bot.config.get('absurdia', {})
            arena_channel = config.get('arena_channel', '#absurdia')

            self.log_debug(f"Arena tournament starting with {len(queue)} creature(s)")

            # Shuffle queue for random pairings
            random.shuffle(queue)

            # Pair creatures
            matches: List[Tuple[Dict, Dict]] = []
            bye_creature = None

            for i in range(0, len(queue), 2):
                if i + 1 < len(queue):
                    matches.append((queue[i], queue[i + 1]))
                else:
                    # Odd number - this creature gets a bye
                    bye_creature = queue[i]

            # Process matches
            results = []

            for creature1, creature2 in matches:
                # Run combat simulation
                battle_result = self.combat.simulate_battle(creature1, creature2)

                winner = battle_result['winner']
                loser = battle_result['loser']

                # Update W/L records
                self.db.update_creature_wins_losses(winner['id'], won=True)
                self.db.update_creature_wins_losses(loser['id'], won=False)

                # Award coins
                winner_coins, loser_coins = self._calculate_arena_rewards(winner, loser)
                self.db.update_player_coins(winner['owner_id'], winner_coins)
                self.db.update_player_coins(loser['owner_id'], loser_coins)

                # Remove from arena
                self.db.submit_creature_to_arena(winner['id'], False)
                self.db.submit_creature_to_arena(loser['id'], False)

                # Create result summary
                winner_name = winner['nickname'] if winner['nickname'] else winner['name']
                loser_name = loser['nickname'] if loser['nickname'] else loser['name']

                winner_owner = self.db.get_player(winner['owner_id'], "Unknown")
                loser_owner = self.db.get_player(loser['owner_id'], "Unknown")

                result_text = (f"{winner_owner['username']}'s {winner_name} defeats "
                             f"{loser_owner['username']}'s {loser_name} "
                             f"in {battle_result['rounds']} rounds! "
                             f"(+{winner_coins} coins)")

                results.append(result_text)

            # Handle bye if exists
            if bye_creature:
                # Bye creature gets auto-win
                self.db.update_creature_wins_losses(bye_creature['id'], won=True)
                bye_coins = config.get('arena_rewards', {}).get('bye', 50)
                self.db.update_player_coins(bye_creature['owner_id'], bye_coins)
                self.db.submit_creature_to_arena(bye_creature['id'], False)

                bye_name = bye_creature['nickname'] if bye_creature['nickname'] else bye_creature['name']
                bye_owner = self.db.get_player(bye_creature['owner_id'], "Unknown")

                results.append(f"{bye_owner['username']}'s {bye_name} gets a bye (free win, +{bye_coins} coins)")

            # Post results to IRC
            if results:
                self._announce_arena_results(arena_channel, results)

            self.log_debug(f"Arena tournament completed: {len(matches)} matches, bye={bye_creature is not None}")

        except Exception as e:
            self.log_debug(f"Error in hourly arena: {e}")
            import traceback
            self.log_debug(traceback.format_exc())

    def _calculate_arena_rewards(self, winner: Dict[str, Any], loser: Dict[str, Any]) -> Tuple[int, int]:
        """
        Calculate coin rewards for arena match.

        Args:
            winner: Winning creature
            loser: Losing creature

        Returns:
            Tuple of (winner_coins, loser_coins)
        """
        config = self.bot.config.get('absurdia', {})
        rewards = config.get('arena_rewards', {})

        # Base rewards
        win_coins = rewards.get('win', 150)
        loss_coins = rewards.get('loss', 30)

        return (win_coins, loss_coins)

    def _announce_arena_results(self, channel: str, results: List[str]) -> None:
        """
        Announce arena results to IRC channel.

        Args:
            channel: Channel to announce in
            results: List of result strings
        """
        try:
            # Send header
            self.bot.connection.privmsg(channel, "=== ARENA TOURNAMENT RESULTS ===")

            # Send each result
            for result in results:
                self.bot.connection.privmsg(channel, result)

            # Send footer
            self.bot.connection.privmsg(channel, f"Next tournament: top of the hour! Use !submit to enter.")

        except Exception as e:
            self.log_debug(f"Error announcing arena results: {e}")
