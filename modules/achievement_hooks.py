# modules/achievement_hooks.py
# Helper functions for recording achievement progress from other modules

import logging

logger = logging.getLogger(__name__)

def record_achievement(bot, username: str, metric: str, amount: int = 1):
    """
    Record progress toward an achievement for a user.

    Args:
        bot: The Jeeves bot instance
        username: Username to record progress for
        metric: The metric to track (e.g., 'quests_completed', 'coffees_ordered')
        amount: Amount to increment (default: 1)
    """
    achievements_module = bot.pm.plugins.get("achievements")
    if achievements_module and hasattr(achievements_module, "record_progress"):
        try:
            achievements_module.record_progress(username, metric, amount)
        except Exception as exc:
            # Avoid breaking callers if achievements are unavailable.
            if hasattr(bot, "log_debug"):
                bot.log_debug(f"[achievements] record_progress failed for {username}/{metric}: {exc}")
            else:
                logger.exception("record_progress failed for %s/%s", username, metric)


# Convenience functions for common achievements

def record_quest_completion(bot, username: str):
    """Record a quest completion."""
    record_achievement(bot, username, "quests_completed", 1)


def record_quest_win(bot, username: str):
    """Record a quest win."""
    record_achievement(bot, username, "quest_wins", 1)


def record_quest_loss(bot, username: str):
    """Record a quest loss."""
    record_achievement(bot, username, "quest_losses", 1)


def record_animal_hunt(bot, username: str):
    """Record an animal hunt."""
    record_achievement(bot, username, "animals_hunted", 1)


def record_animal_hug(bot, username: str):
    """Record an animal hug."""
    record_achievement(bot, username, "animals_hugged", 1)


def record_coffee_order(bot, username: str):
    """Record a coffee order."""
    record_achievement(bot, username, "coffees_ordered", 1)


def record_weather_check(bot, username: str):
    """Record a weather check."""
    record_achievement(bot, username, "weather_checks", 1)


def record_courtesy_message(bot, username: str):
    """Record a courtesy message sent."""
    record_achievement(bot, username, "courtesy_messages", 1)


def record_karma_given(bot, username: str, amount: int = 1):
    """Record karma given to others."""
    record_achievement(bot, username, "karma_given", amount)


def record_translation(bot, username: str):
    """Record a translation used."""
    record_achievement(bot, username, "translations_used", 1)


def record_scare(bot, username: str):
    """Record a scare sent."""
    record_achievement(bot, username, "scares_sent", 1)


def record_gif_posted(bot, username: str):
    """Record a GIF posted."""
    record_achievement(bot, username, "gifs_posted", 1)


def record_prestige_level(bot, username: str, prestige: int):
    """Record prestige level reached."""
    achievements_module = bot.pm.plugins.get("achievements")
    if not achievements_module:
        return

    user_id = bot.get_user_id(username)
    user_achievements = achievements_module.get_state("user_achievements", {})
    user_data = user_achievements.get(user_id, {})
    progress = user_data.get("progress", {})

    current_best = progress.get("prestige", 0)
    if prestige > current_best:
        record_achievement(bot, username, "prestige", prestige - current_best)


def record_win_streak(bot, username: str, streak: int):
    """Record current win streak (only updates if higher)."""
    achievements_module = bot.pm.plugins.get("achievements")
    if not achievements_module:
        return

    user_id = bot.get_user_id(username)
    user_achievements = achievements_module.get_state("user_achievements", {})
    user_data = user_achievements.get(user_id, {})
    progress = user_data.get("progress", {})

    current_best = progress.get("win_streak", 0)
    if streak > current_best:
        record_achievement(bot, username, "win_streak", streak - current_best)


def record_loss_streak(bot, username: str, streak: int):
    """Record current loss streak (only updates if higher)."""
    achievements_module = bot.pm.plugins.get("achievements")
    if not achievements_module:
        return

    user_id = bot.get_user_id(username)
    user_achievements = achievements_module.get_state("user_achievements", {})
    user_data = user_achievements.get(user_id, {})
    progress = user_data.get("progress", {})

    current_best = progress.get("loss_streak", 0)
    if streak > current_best:
        record_achievement(bot, username, "loss_streak", streak - current_best)


# Fishing achievements

def record_fish_caught(bot, username: str, rarity: str = "common"):
    """Record a fish catch with rarity tracking."""
    record_achievement(bot, username, "fish_caught", 1)
    if rarity == "rare":
        record_achievement(bot, username, "rare_fish_caught", 1)
    elif rarity == "legendary":
        record_achievement(bot, username, "legendary_fish_caught", 1)


def record_fishing_level(bot, username: str, level: int):
    """Record fishing level reached (only updates if higher)."""
    achievements_module = bot.pm.plugins.get("achievements")
    if not achievements_module:
        return

    user_id = bot.get_user_id(username)
    user_achievements = achievements_module.get_state("user_achievements", {})
    user_data = user_achievements.get(user_id, {})
    progress = user_data.get("progress", {})

    current = progress.get("fishing_level", 0)
    if level > current:
        record_achievement(bot, username, "fishing_level", level - current)


def record_line_broken(bot, username: str):
    """Record a broken fishing line."""
    record_achievement(bot, username, "lines_broken", 1)


def record_junk_collected(bot, username: str):
    """Record junk collected while fishing."""
    record_achievement(bot, username, "junk_collected", 1)


def record_perfect_fishing_wait(bot, username: str):
    """Record a perfect wait time (18-24 hours)."""
    record_achievement(bot, username, "perfect_waits", 1)
