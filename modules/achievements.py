# modules/achievements.py
# Achievement tracking system for Jeeves IRC bot

import time
from typing import Dict, Any, List, Optional, Set
from datetime import datetime
from .base import SimpleCommandModule

# Achievement definitions
ACHIEVEMENTS = {
    # Quest Achievements
    "quest_novice": {
        "name": "Quest Novice",
        "description": "Complete 10 quests",
        "category": "quest",
        "requirement": {"quests_completed": 10},
        "secret": False,
        "tier": 1
    },
    "quest_adept": {
        "name": "Quest Adept",
        "description": "Complete 50 quests",
        "category": "quest",
        "requirement": {"quests_completed": 50},
        "secret": False,
        "tier": 2
    },
    "quest_master": {
        "name": "Quest Master",
        "description": "Complete 100 quests",
        "category": "quest",
        "requirement": {"quests_completed": 100},
        "secret": False,
        "tier": 3
    },
    "quest_legend": {
        "name": "Quest Legend",
        "description": "Complete 500 quests",
        "category": "quest",
        "requirement": {"quests_completed": 500},
        "secret": False,
        "tier": 4
    },
    "quest_mythic": {
        "name": "Quest Mythic",
        "description": "Complete 1000 quests",
        "category": "quest",
        "requirement": {"quests_completed": 1000},
        "secret": False,
        "tier": 5
    },
    "prestige_1": {
        "name": "First Prestige",
        "description": "Reach Prestige 1",
        "category": "quest",
        "requirement": {"prestige": 1},
        "secret": False
    },
    "prestige_5": {
        "name": "Prestige Elite",
        "description": "Reach Prestige 5",
        "category": "quest",
        "requirement": {"prestige": 5},
        "secret": False
    },
    "prestige_10": {
        "name": "Prestige Master",
        "description": "Reach Prestige 10",
        "category": "quest",
        "requirement": {"prestige": 10},
        "secret": False
    },
    "win_streak_5": {
        "name": "On a Roll",
        "description": "Win 5 quests in a row",
        "category": "quest",
        "requirement": {"win_streak": 5},
        "secret": False
    },
    "win_streak_10": {
        "name": "Unstoppable",
        "description": "Win 10 quests in a row",
        "category": "quest",
        "requirement": {"win_streak": 10},
        "secret": False
    },
    "win_streak_25": {
        "name": "Legendary Streak",
        "description": "Win 25 quests in a row",
        "category": "quest",
        "requirement": {"win_streak": 25},
        "secret": False
    },
    "unlucky": {
        "name": "Unlucky",
        "description": "Lose 10 quests in a row",
        "category": "quest",
        "requirement": {"loss_streak": 10},
        "secret": True
    },

    # Creature/Animal Achievements
    "hunter_1": {
        "name": "Hunter",
        "description": "Hunt 10 creatures",
        "category": "creatures",
        "requirement": {"animals_hunted": 10},
        "secret": False,
        "tier": 1
    },
    "hunter_2": {
        "name": "Hunter II",
        "description": "Hunt 50 creatures",
        "category": "creatures",
        "requirement": {"animals_hunted": 50},
        "secret": False,
        "tier": 2
    },
    "hunter_3": {
        "name": "Hunter III",
        "description": "Hunt 100 creatures",
        "category": "creatures",
        "requirement": {"animals_hunted": 100},
        "secret": False,
        "tier": 3
    },
    "apex_predator": {
        "name": "Apex Predator",
        "description": "Hunt 250 creatures",
        "category": "creatures",
        "requirement": {"animals_hunted": 250},
        "secret": False,
        "tier": 4
    },
    "lover_1": {
        "name": "Animal Lover",
        "description": "Hug 10 creatures",
        "category": "creatures",
        "requirement": {"animals_hugged": 10},
        "secret": False,
        "tier": 1
    },
    "lover_2": {
        "name": "Animal Lover II",
        "description": "Hug 50 creatures",
        "category": "creatures",
        "requirement": {"animals_hugged": 50},
        "secret": False,
        "tier": 2
    },
    "lover_3": {
        "name": "Animal Lover III",
        "description": "Hug 100 creatures",
        "category": "creatures",
        "requirement": {"animals_hugged": 100},
        "secret": False,
        "tier": 3
    },
    "pacifist": {
        "name": "Pacifist",
        "description": "Hug 100 creatures without hunting any",
        "category": "creatures",
        "requirement": {"animals_hugged": 100, "animals_hunted": 0},
        "secret": True
    },
    "bloodthirsty": {
        "name": "Bloodthirsty",
        "description": "Hunt 100 creatures without hugging any",
        "category": "creatures",
        "requirement": {"animals_hunted": 100, "animals_hugged": 0},
        "secret": True
    },

    # Coffee Achievements
    "coffee_drinker": {
        "name": "Coffee Drinker",
        "description": "Order 25 coffees",
        "category": "social",
        "requirement": {"coffees_ordered": 25},
        "secret": False,
        "tier": 1
    },
    "coffee_addict": {
        "name": "Coffee Addict",
        "description": "Order 100 coffees",
        "category": "social",
        "requirement": {"coffees_ordered": 100},
        "secret": False,
        "tier": 2
    },
    "caffeine_overload": {
        "name": "Caffeine Overload",
        "description": "Order 500 coffees",
        "category": "social",
        "requirement": {"coffees_ordered": 500},
        "secret": False,
        "tier": 3
    },

    # Social/Usage Achievements
    "weatherwatcher": {
        "name": "Weatherwatcher",
        "description": "Check weather 50 times",
        "category": "social",
        "requirement": {"weather_checks": 50},
        "secret": False
    },
    "meteorologist": {
        "name": "Meteorologist",
        "description": "Check weather 200 times",
        "category": "social",
        "requirement": {"weather_checks": 200},
        "secret": False
    },
    "polite": {
        "name": "Polite",
        "description": "Send 50 courtesy messages",
        "category": "social",
        "requirement": {"courtesy_messages": 50},
        "secret": False
    },
    "karma_farmer": {
        "name": "Karma Farmer",
        "description": "Give 100 karma points",
        "category": "social",
        "requirement": {"karma_given": 100},
        "secret": False
    },
    "translator": {
        "name": "Translator",
        "description": "Use translation 25 times",
        "category": "social",
        "requirement": {"translations_used": 25},
        "secret": False
    },
    "scare_tactics": {
        "name": "Scare Tactics",
        "description": "Scare 25 people",
        "category": "fun",
        "requirement": {"scares_sent": 25},
        "secret": False
    },
    "gif_master": {
        "name": "GIF Master",
        "description": "Post 50 GIFs",
        "category": "fun",
        "requirement": {"gifs_posted": 50},
        "secret": False
    },

    # Meta Achievements
    "achievement_hunter": {
        "name": "Achievement Hunter",
        "description": "Unlock 5 achievements",
        "category": "meta",
        "requirement": {"achievements_unlocked": 5},
        "secret": False,
        "tier": 1
    },
    "achievement_master": {
        "name": "Achievement Master",
        "description": "Unlock 15 achievements",
        "category": "meta",
        "requirement": {"achievements_unlocked": 15},
        "secret": False,
        "tier": 2
    },
    "completionist": {
        "name": "Completionist",
        "description": "Unlock 30 achievements",
        "category": "meta",
        "requirement": {"achievements_unlocked": 30},
        "secret": True,
        "tier": 3
    },
    "first_blood": {
        "name": "First!",
        "description": "Be the first to unlock any achievement globally",
        "category": "meta",
        "requirement": "special",
        "secret": True
    },
    "trendsetter": {
        "name": "Trendsetter",
        "description": "Be the first to unlock 5 different achievements globally",
        "category": "meta",
        "requirement": "special",
        "secret": True
    },
}


class Achievements(SimpleCommandModule):
    """Achievement tracking system."""
    name = "achievements"
    version = "1.0.0"
    description = "Track and display user achievements across all Jeeves activities"

    def __init__(self, bot):
        super().__init__(bot)

        # Initialize state
        self.set_state("user_achievements", self.get_state("user_achievements", {}))
        self.set_state("opted_in_users", self.get_state("opted_in_users", []))
        self.set_state("global_unlocks", self.get_state("global_unlocks", {}))
        self.save_state()

    def _register_commands(self):
        self.register_command(r"^\s*!achievements?\s*$", self._cmd_achievements_self, name="achievements", description="Show your achievements")
        self.register_command(r"^\s*!achievements?\s+list\s*$", self._cmd_achievements_list, name="achievements list", description="List all available achievements")
        self.register_command(r"^\s*!achievements?\s+stats\s*$", self._cmd_achievements_stats, name="achievements stats", description="Show achievement statistics")
        self.register_command(r"^\s*!achievements?\s+(.+)$", self._cmd_achievements_user, name="achievements user", description="Show another user's achievements")
        self.register_command(r"^\s*!ach\s*$", self._cmd_achievements_self, name="ach", description="Short alias for !achievements")
        self.register_command(r"^\s*!ach\s+list\s*$", self._cmd_achievements_list, name="ach list", description="Short alias for !achievements list")
        self.register_command(r"^\s*!ach\s+stats\s*$", self._cmd_achievements_stats, name="ach stats", description="Short alias for !achievements stats")
        self.register_command(r"^\s*!ach\s+(.+)$", self._cmd_achievements_user, name="ach user", description="Short alias for !achievements <user>")

    def on_join(self, connection, event):
        """Track when users join #achievements channel."""
        channel = event.target
        username = event.source.nick

        if channel.lower() == "#achievements":
            user_id = self.bot.get_user_id(username)
            opted_in = self.get_state("opted_in_users", [])

            if user_id not in opted_in:
                opted_in.append(user_id)
                self.set_state("opted_in_users", opted_in)
                self.save_state()

                # Initialize user achievement data if not exists
                user_achievements = self.get_state("user_achievements", {})
                if user_id not in user_achievements:
                    user_achievements[user_id] = {
                        "unlocked": [],
                        "progress": {},
                        "timestamps": {}
                    }
                    self.set_state("user_achievements", user_achievements)
                    self.save_state()

                self.safe_privmsg(username, "Achievement tracking enabled! Your progress across all Jeeves channels will now be tracked. Achievements will be announced in #achievements when unlocked.")

    def is_tracking(self, username: str) -> bool:
        """Check if user has opted into achievement tracking."""
        user_id = self.bot.get_user_id(username)
        return user_id in self.get_state("opted_in_users", [])

    def record_progress(self, username: str, metric: str, amount: int = 1):
        """Record progress toward achievements for a user."""
        if not self.is_tracking(username):
            return

        user_id = self.bot.get_user_id(username)
        user_achievements = self.get_state("user_achievements", {})

        if user_id not in user_achievements:
            user_achievements[user_id] = {
                "unlocked": [],
                "progress": {},
                "timestamps": {}
            }

        # Update progress
        user_data = user_achievements[user_id]
        current = user_data["progress"].get(metric, 0)
        user_data["progress"][metric] = current + amount

        self.set_state("user_achievements", user_achievements)
        self.save_state()

        # Check for unlocked achievements
        self._check_achievements(username, user_id)

    def _check_achievements(self, username: str, user_id: str):
        """Check if user has unlocked any new achievements."""
        user_achievements = self.get_state("user_achievements", {})
        user_data = user_achievements.get(user_id, {})
        unlocked = user_data.get("unlocked", [])
        progress = user_data.get("progress", {})

        newly_unlocked = []

        for ach_id, ach_def in ACHIEVEMENTS.items():
            if ach_id in unlocked:
                continue  # Already unlocked

            # Check requirements
            requirement = ach_def.get("requirement")
            if isinstance(requirement, dict):
                # All requirements must be met
                if all(progress.get(key, 0) >= value for key, value in requirement.items()):
                    newly_unlocked.append(ach_id)
            elif requirement == "special":
                # Special achievements checked elsewhere
                continue

        # Unlock achievements
        for ach_id in newly_unlocked:
            self._unlock_achievement(username, user_id, ach_id)

    def _unlock_achievement(self, username: str, user_id: str, achievement_id: str):
        """Unlock an achievement for a user."""
        user_achievements = self.get_state("user_achievements", {})
        user_data = user_achievements.get(user_id, {})

        # Add to unlocked list
        user_data["unlocked"].append(achievement_id)
        user_data["timestamps"][achievement_id] = time.time()

        # Update meta achievement progress
        user_data["progress"]["achievements_unlocked"] = len(user_data["unlocked"])

        user_achievements[user_id] = user_data
        self.set_state("user_achievements", user_achievements)

        # Track global first unlock
        global_unlocks = self.get_state("global_unlocks", {})
        if achievement_id not in global_unlocks:
            global_unlocks[achievement_id] = {
                "user_id": user_id,
                "username": username,
                "timestamp": time.time()
            }
            self.set_state("global_unlocks", global_unlocks)

            # Check for "First!" achievement
            first_count = sum(1 for unlock in global_unlocks.values() if unlock["user_id"] == user_id)
            if first_count == 1 and "first_blood" not in user_data["unlocked"]:
                self._unlock_achievement(username, user_id, "first_blood")
            elif first_count >= 5 and "trendsetter" not in user_data["unlocked"]:
                self._unlock_achievement(username, user_id, "trendsetter")

        self.save_state()

        # Announce in #achievements
        ach_def = ACHIEVEMENTS.get(achievement_id, {})
        ach_name = ach_def.get("name", achievement_id)
        self.bot.connection.privmsg("#achievements", f"🏆 {username} unlocked achievement: {ach_name}!")

    def _cmd_achievements_self(self, connection, event, msg, username, match):
        """Show user's own achievement summary."""
        if not self.is_tracking(username):
            self.safe_reply(connection, event, "You're not tracking achievements yet. Join #achievements to start!")
            return True

        user_id = self.bot.get_user_id(username)
        user_achievements = self.get_state("user_achievements", {})
        user_data = user_achievements.get(user_id, {})
        unlocked = user_data.get("unlocked", [])

        total = len(unlocked)
        total_available = len([a for a in ACHIEVEMENTS.values() if not a.get("secret")])

        response = f"You have unlocked {total} achievements! "
        if total > 0:
            response += f"Use !ach list to see them all."
        else:
            response += "Start using Jeeves to unlock achievements!"

        self.safe_reply(connection, event, response)
        return True

    def _cmd_achievements_list(self, connection, event, msg, username, match):
        """List all unlocked achievements for the user."""
        if not self.is_tracking(username):
            self.safe_reply(connection, event, "You're not tracking achievements yet. Join #achievements to start!")
            return True

        user_id = self.bot.get_user_id(username)
        user_achievements = self.get_state("user_achievements", {})
        user_data = user_achievements.get(user_id, {})
        unlocked = user_data.get("unlocked", [])
        timestamps = user_data.get("timestamps", {})

        if not unlocked:
            self.safe_reply(connection, event, "You haven't unlocked any achievements yet. Keep using Jeeves!")
            return True

        # Group by category
        by_category = {}
        for ach_id in unlocked:
            ach_def = ACHIEVEMENTS.get(ach_id, {})
            category = ach_def.get("category", "other")
            if category not in by_category:
                by_category[category] = []
            by_category[category].append(ach_id)

        # Build response
        lines = [f"🏆 {username}'s Achievements ({len(unlocked)} unlocked):"]

        for category, ach_list in sorted(by_category.items()):
            lines.append(f"  [{category.title()}]")
            for ach_id in ach_list:
                ach_def = ACHIEVEMENTS.get(ach_id, {})
                name = ach_def.get("name", ach_id)
                desc = ach_def.get("description", "")
                lines.append(f"    • {name}: {desc}")

        # Send via private message to avoid spam
        for line in lines:
            self.safe_privmsg(username, line)

        self.safe_reply(connection, event, f"Sent your {len(unlocked)} achievements via private message!")
        return True

    def _cmd_achievements_user(self, connection, event, msg, username, match):
        """Show another user's achievements."""
        target = match.group(1).strip()

        # Try to find user
        users_module = self.bot.pm.plugins.get("users")
        if users_module:
            target_id = users_module.get_state("nick_map", {}).get(target.lower())
        else:
            target_id = None

        if not target_id:
            self.safe_reply(connection, event, f"User '{target}' not found.")
            return True

        user_achievements = self.get_state("user_achievements", {})
        user_data = user_achievements.get(target_id, {})
        unlocked = user_data.get("unlocked", [])

        if not unlocked:
            self.safe_reply(connection, event, f"{target} hasn't unlocked any achievements yet.")
            return True

        # Show summary
        total = len(unlocked)
        self.safe_reply(connection, event, f"{target} has unlocked {total} achievements! Use !ach list in private to see your own.")
        return True

    def _cmd_achievements_stats(self, connection, event, msg, username, match):
        """Show global achievement statistics."""
        global_unlocks = self.get_state("global_unlocks", {})
        user_achievements = self.get_state("user_achievements", {})

        total_achievements = len(ACHIEVEMENTS)
        total_unlocked_globally = len(global_unlocks)
        total_users = len([u for u in user_achievements.values() if u.get("unlocked")])

        # Find rarest achievement
        unlock_counts = {}
        for user_data in user_achievements.values():
            for ach_id in user_data.get("unlocked", []):
                unlock_counts[ach_id] = unlock_counts.get(ach_id, 0) + 1

        rarest = None
        if unlock_counts:
            rarest_id = min(unlock_counts, key=unlock_counts.get)
            rarest = ACHIEVEMENTS.get(rarest_id, {}).get("name", rarest_id)
            rarest_count = unlock_counts[rarest_id]

        response = f"📊 Achievement Stats: {total_users} users, {total_unlocked_globally}/{total_achievements} achievements discovered."
        if rarest:
            response += f" Rarest: {rarest} ({rarest_count} unlock{'s' if rarest_count != 1 else ''})."

        self.safe_reply(connection, event, response)
        return True


def setup(bot):
    return Achievements(bot)
