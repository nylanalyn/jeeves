# modules/ideas.py
# Module for submitting, voting on, and tracking community ideas

import schedule
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from .base import ModuleBase

UTC = timezone.utc

def setup(bot):
    return Ideas(bot)


class Ideas(ModuleBase):
    name = "ideas"
    version = "1.0.0"
    description = "Submit ideas, vote on them, and track winning suggestions."

    def __init__(self, bot):
        super().__init__(bot)
        self._register_commands()
        self._active_poll: Optional[Dict[str, Any]] = None
        self._votes: Dict[str, int] = {}  # username -> option number

    def _register_commands(self):
        self.register_command(r"^\s*!ideas?\s+(.+)$", self._cmd_submit_idea, name="ideas")
        self.register_command(r"^\s*!idea-poll\s*$", self._cmd_start_poll, name="idea-poll", admin_only=True)
        self.register_command(r"^\s*!vote\s+(\d+)\s*$", self._cmd_vote, name="vote")
        self.register_command(r"^\s*!winners?\s*$", self._cmd_list_winners, name="winners")
        self.register_command(r"^\s*!winners?\s+delete\s+(\S+)\s*$", self._cmd_delete_winner, name="winners-delete", admin_only=True)

    def on_load(self):
        # Clear any stale poll jobs on load
        self._clear_poll_jobs()

    def on_unload(self):
        self._clear_poll_jobs()
        super().on_unload()

    def _clear_poll_jobs(self) -> int:
        """Clear all scheduled poll-related jobs."""
        jobs = schedule.get_jobs(f"{self.name}-poll")
        count = len(jobs)
        if count > 0:
            schedule.clear(f"{self.name}-poll")
        return count

    # --- Commands ---

    def _cmd_submit_idea(self, connection, event, msg, username, match):
        """Submit a new idea."""
        idea_text = match.group(1).strip()

        if len(idea_text) < 5:
            self.safe_reply(connection, event, "That idea is a bit too brief. Please elaborate.")
            return True

        if len(idea_text) > 300:
            self.safe_reply(connection, event, "That idea is rather lengthy. Please keep it under 300 characters.")
            return True

        # Check if a poll is active
        if self._active_poll:
            self.safe_reply(connection, event, "A poll is currently in progress. Please wait until it concludes to submit new ideas.")
            return True

        ideas = self.get_state("ideas", [])
        ideas.append({
            "username": username,
            "idea": idea_text,
            "submitted_at": datetime.now(UTC).isoformat()
        })
        self.set_state("ideas", ideas)
        self.save_state()

        has_flavor = self.has_flavor_enabled(username)
        if has_flavor:
            self.safe_reply(connection, event, f"Very good, {self.bot.title_for(username)}. Your idea has been noted. There are now {len(ideas)} idea(s) awaiting consideration.")
        else:
            self.safe_reply(connection, event, f"Idea submitted. {len(ideas)} idea(s) pending.")
        return True

    def _cmd_start_poll(self, connection, event, msg, username, match):
        """Start a poll with all pending ideas (admin only)."""
        if self._active_poll:
            self.safe_reply(connection, event, "A poll is already in progress.")
            return True

        ideas = self.get_state("ideas", [])
        if not ideas:
            self.safe_reply(connection, event, "There are no ideas to vote on.")
            return True

        # Set up the poll
        self._active_poll = {
            "ideas": ideas.copy(),
            "channel": event.target,
            "started_at": datetime.now(UTC).isoformat(),
            "started_by": username
        }
        self._votes = {}

        # Clear the pending ideas
        self.set_state("ideas", [])
        self.save_state()

        # Announce the poll
        poll_duration_minutes = self.get_config_value("poll_duration_minutes", event.target, default=10)
        self.safe_reply(connection, event, f"The idea poll is now open! You have {poll_duration_minutes} minutes to vote.")
        self.safe_reply(connection, event, "Use !vote <number> to cast your vote. Options:")

        for i, idea in enumerate(self._active_poll["ideas"], 1):
            self.safe_reply(connection, event, f"{i}. {idea['username']} said: \"{idea['idea']}\"")

        # Schedule the poll to end
        poll_duration_seconds = poll_duration_minutes * 60
        schedule.every(poll_duration_seconds).seconds.do(self._end_poll).tag(f"{self.name}-poll")

        self.log_debug(f"Poll started by {username} with {len(ideas)} ideas, ending in {poll_duration_minutes} minutes")
        return True

    def _cmd_vote(self, connection, event, msg, username, match):
        """Cast a vote for an idea."""
        if not self._active_poll:
            self.safe_reply(connection, event, "There is no active poll at the moment.")
            return True

        if self._active_poll["channel"] != event.target:
            self.safe_reply(connection, event, f"The active poll is in {self._active_poll['channel']}.")
            return True

        vote_num = int(match.group(1))
        max_option = len(self._active_poll["ideas"])

        if vote_num < 1 or vote_num > max_option:
            self.safe_reply(connection, event, f"Invalid option. Please vote between 1 and {max_option}.")
            return True

        user_lower = username.lower()
        previous_vote = self._votes.get(user_lower)

        if previous_vote == vote_num:
            self.safe_reply(connection, event, f"You've already voted for option {vote_num}.")
            return True

        self._votes[user_lower] = vote_num

        if previous_vote:
            self.safe_reply(connection, event, f"Vote changed from option {previous_vote} to option {vote_num}.")
        else:
            has_flavor = self.has_flavor_enabled(username)
            if has_flavor:
                self.safe_reply(connection, event, f"Your vote for option {vote_num} has been recorded, {self.bot.title_for(username)}.")
            else:
                self.safe_reply(connection, event, f"Vote for option {vote_num} recorded.")
        return True

    def _cmd_list_winners(self, connection, event, msg, username, match):
        """List all winning ideas."""
        winners = self.get_state("winners", [])

        if not winners:
            self.safe_reply(connection, event, "No winning ideas have been recorded yet.")
            return True

        self.safe_reply(connection, event, f"Winning ideas ({len(winners)}):")
        for i, winner in enumerate(winners, 1):
            self.safe_reply(connection, event, f"{i}. {winner['username']}: \"{winner['idea']}\" (won {winner.get('won_at', 'unknown')})")
        return True

    def _cmd_delete_winner(self, connection, event, msg, username, match):
        """Delete a winner by number or 'all' (admin only)."""
        target = match.group(1).strip().lower()
        winners = self.get_state("winners", [])

        if not winners:
            self.safe_reply(connection, event, "There are no winners to delete.")
            return True

        if target == "all":
            count = len(winners)
            self.set_state("winners", [])
            self.save_state()
            self.safe_reply(connection, event, f"All {count} winner(s) have been cleared.")
            return True

        try:
            index = int(target)
        except ValueError:
            self.safe_reply(connection, event, "Please specify a number or 'all'.")
            return True

        if index < 1 or index > len(winners):
            self.safe_reply(connection, event, f"Invalid number. Please choose between 1 and {len(winners)}.")
            return True

        removed = winners.pop(index - 1)
        self.set_state("winners", winners)
        self.save_state()
        self.safe_reply(connection, event, f"Removed winner: \"{removed['idea']}\" by {removed['username']}.")
        return True

    # --- Poll Management ---

    def _end_poll(self):
        """End the current poll and announce results."""
        self._clear_poll_jobs()

        if not self._active_poll:
            return schedule.CancelJob

        channel = self._active_poll["channel"]
        ideas = self._active_poll["ideas"]

        # Tally votes
        vote_counts: Dict[int, int] = {}
        for option in self._votes.values():
            vote_counts[option] = vote_counts.get(option, 0) + 1

        total_votes = len(self._votes)

        if total_votes == 0:
            self.safe_say("The poll has ended with no votes cast. All ideas have been discarded.", channel)
            self._active_poll = None
            self._votes = {}
            return schedule.CancelJob

        # Find winner(s)
        max_votes = max(vote_counts.values())
        winning_options = [opt for opt, count in vote_counts.items() if count == max_votes]

        if len(winning_options) > 1:
            # Tie - announce it and don't record a winner
            tied_nums = ", ".join(str(o) for o in sorted(winning_options))
            self.safe_say(f"The poll has ended in a tie between options {tied_nums} with {max_votes} vote(s) each! No winner recorded.", channel)
        else:
            # We have a winner
            winner_num = winning_options[0]
            winner_idea = ideas[winner_num - 1]

            # Record the winner
            winners = self.get_state("winners", [])
            winners.append({
                "username": winner_idea["username"],
                "idea": winner_idea["idea"],
                "votes": max_votes,
                "total_votes": total_votes,
                "won_at": datetime.now(UTC).strftime("%Y-%m-%d")
            })
            self.set_state("winners", winners)
            self.save_state()

            self.safe_say(f"The poll has ended! Option {winner_num} wins with {max_votes} vote(s) out of {total_votes}!", channel)
            self.safe_say(f"Winner: {winner_idea['username']} - \"{winner_idea['idea']}\"", channel)

        self._active_poll = None
        self._votes = {}

        return schedule.CancelJob
