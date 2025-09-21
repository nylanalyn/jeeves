import sqlite3
import json
from collections import defaultdict

def get_animal_stats(db_path='bot.db'):
    """
    Connects to the bot.db SQLite database and prints a summary of animal stats.

    Args:
        db_path (str): The path to the SQLite database file.
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Dictionary to hold user stats
        # defaultdict is used for convenience to handle new users
        user_stats = defaultdict(lambda: defaultdict(int))

        # Fetch all relevant settings from the user_channel_settings table
        cursor.execute("""
            SELECT
                u.nickname,
                ucs.setting,
                ucs.value
            FROM user_channel_settings ucs
            JOIN users u ON ucs.user_id = u.user_id
            WHERE ucs.setting IN (
                'cats-buddied', 'cats-stolen',
                'ducks-befriended', 'ducks-shot',
                'puppies-buddied', 'puppies-caged'
            )
        """)

        rows = cursor.fetchall()

        for nickname, setting, value in rows:
            # The value is stored as a JSON string, so we need to load it
            count = json.loads(value)
            user_stats[nickname][setting] += count

        # Print the stats for each user
        for nickname, stats in user_stats.items():
            print(f"Stats for {nickname}:")
            if stats.get('cats-buddied', 0) > 0:
                print(f"  - Cats Buddied: {stats['cats-buddied']}")
            if stats.get('cats-stolen', 0) > 0:
                print(f"  - Cats Trapped: {stats['cats-stolen']}")
            if stats.get('ducks-befriended', 0) > 0:
                print(f"  - Ducks Befriended: {stats['ducks-befriended']}")
            if stats.get('ducks-shot', 0) > 0:
                print(f"  - Ducks Trapped: {stats['ducks-shot']}")
            if stats.get('puppies-buddied', 0) > 0:
                print(f"  - Puppies Buddied: {stats['puppies-buddied']}")
            if stats.get('puppies-caged', 0) > 0:
                print(f"  - Puppies Caged: {stats['puppies-caged']}")
            print("-" * 20)

    except sqlite3.Error as e:
        print(f"Database error: {e}")
    except FileNotFoundError:
        print(f"Error: The database file was not found at '{db_path}'")
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    get_animal_stats()