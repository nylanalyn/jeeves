# modules/achievement_hooks.py
# Helper functions for recording achievement progress from other modules

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
        except Exception:
            # Silently fail if achievements module has issues
            pass


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
    record_achievement(bot, username, "prestige", prestige - record_achievement(bot, username, "prestige", 0))


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
