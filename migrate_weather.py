# migrate_weather.py
import json
import requests
import time
from pathlib import Path

# --- Configuration ---
# This locates your state file, assuming the standard location.
CONFIG_DIR = Path.home() / ".config" / "jeeves"
STATE_PATH = CONFIG_DIR / "state.json"
USER_AGENT = "JeevesMigrationScript/1.0"

def get_geocode_data(location_string: str) -> dict | None:
    """Geocodes a location string and returns the new dictionary format."""
    print(f"  -> Geocoding '{location_string}'...")
    geo_url = f"https://nominatim.openstreetmap.org/search?q={requests.utils.quote(location_string)}&format=json&limit=1"
    try:
        response = requests.get(geo_url, headers={'User-Agent': USER_AGENT})
        response.raise_for_status()
        data = response.json()
        if not data:
            print(f"  -> FAILURE: No results from geocoding API for '{location_string}'.")
            return None

        # Construct the new dictionary object
        new_location_obj = {
            "query": location_string,
            "lat": data[0]["lat"],
            "lon": data[0]["lon"],
            "display_name": data[0]["display_name"]
        }
        print(f"  -> SUCCESS: Found '{data[0]['display_name']}'.")
        return new_location_obj
    except Exception as e:
        print(f"  -> ERROR: An exception occurred for '{location_string}': {e}")
        return None

def main():
    """Main migration logic."""
    if not STATE_PATH.exists():
        print(f"Error: State file not found at {STATE_PATH}")
        return

    print(f"Loading state from: {STATE_PATH}")
    
    # 1. Create a backup
    backup_path = STATE_PATH.with_suffix(".json.bak")
    print(f"Backing up current state to: {backup_path}")
    STATE_PATH.rename(backup_path)

    # 2. Load the data from the backup file
    with open(backup_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Navigate to the relevant part of the state
    try:
        user_locations = data['modules']['weather']['user_locations']
    except KeyError:
        print("Could not find 'user_locations' in state file. Nothing to migrate.")
        # Restore the original file and exit
        backup_path.rename(STATE_PATH)
        return

    print("\nStarting weather location migration...")
    locations_to_update = {}
    success_count = 0
    fail_count = 0

    # 3. Find and convert all old-format strings
    for username, location_data in user_locations.items():
        if isinstance(location_data, str):
            print(f"\nFound old format for user '{username}':")
            new_data = get_geocode_data(location_data)
            if new_data:
                locations_to_update[username] = new_data
                success_count += 1
            else:
                fail_count += 1
            # To avoid hitting API rate limits
            time.sleep(1.1) 

    # 4. Update the main data object
    if locations_to_update:
        print("\nApplying updates...")
        user_locations.update(locations_to_update)
    else:
        print("\nNo locations in the old format were found.")

    # 5. Save the new, migrated state file
    print(f"Saving migrated state back to: {STATE_PATH}")
    with open(STATE_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, sort_keys=True)
    
    print("\n--- Migration Summary ---")
    print(f"Successfully migrated: {success_count} user(s)")
    print(f"Failed to migrate:    {fail_count} user(s)")
    print("Migration complete!")

if __name__ == "__main__":
    main()