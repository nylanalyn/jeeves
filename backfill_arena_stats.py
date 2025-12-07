#!/usr/bin/env python3
"""
Backfill player arena stats from creature wins/losses.

This script calculates each player's total arena wins and losses
by summing up the wins/losses of all their creatures.
"""

import sqlite3
from pathlib import Path

def backfill_arena_stats(db_path: Path):
    """Backfill player arena statistics from creature data."""

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("🔍 Analyzing creature arena records...")

    # Get all creatures with their wins/losses
    cursor.execute("""
        SELECT owner_id,
               SUM(total_wins) as total_wins,
               SUM(total_losses) as total_losses
        FROM creatures
        WHERE owner_id IS NOT NULL
        GROUP BY owner_id
    """)

    player_stats = cursor.fetchall()

    print(f"Found {len(player_stats)} players with arena history")
    print()

    # Update each player's stats
    updated_count = 0
    for stats in player_stats:
        owner_id = stats['owner_id']
        total_wins = stats['total_wins'] or 0
        total_losses = stats['total_losses'] or 0

        if total_wins > 0 or total_losses > 0:
            # Get player username for display
            cursor.execute("SELECT username FROM players WHERE user_id = ?", (owner_id,))
            player = cursor.fetchone()
            username = player['username'] if player else owner_id

            # Update player's arena stats
            cursor.execute("""
                UPDATE players
                SET total_arena_wins = ?,
                    total_arena_losses = ?
                WHERE user_id = ?
            """, (total_wins, total_losses, owner_id))

            print(f"  {username}: {total_wins} wins, {total_losses} losses")
            updated_count += 1

    conn.commit()
    conn.close()

    print()
    print(f"✅ Updated {updated_count} players")
    print()
    print("Note: Win streaks cannot be backfilled from historical data.")
    print("These will start tracking from now on.")

if __name__ == "__main__":
    db_path = Path(__file__).parent / "config" / "absurdia.db"

    if not db_path.exists():
        print(f"❌ Database not found at {db_path}")
        exit(1)

    print("=" * 50)
    print("Arena Stats Backfill Script")
    print("=" * 50)
    print()

    backfill_arena_stats(db_path)

    print()
    print("=" * 50)
    print("Done!")
    print("=" * 50)
