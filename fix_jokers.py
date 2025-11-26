#!/usr/bin/env python3
import json
import random

# List of hilariously rude real place names
RUDE_PLACES = [
    {
        "name": "Cockermouth, England",
        "lat": "54.6600",
        "lon": "-3.3600",
        "short_name": "Cockermouth, GB",
        "display_name": "Cockermouth, Cumbria, England, United Kingdom",
        "country_code": "GB"
    },
    {
        "name": "Poo, India",
        "lat": "32.0667",
        "lon": "78.0667",
        "short_name": "Poo, IN",
        "display_name": "Poo, Himachal Pradesh, India",
        "country_code": "IN"
    },
    {
        "name": "Bum, Sierra Leone",
        "lat": "7.8000",
        "lon": "-11.7167",
        "short_name": "Bum, SL",
        "display_name": "Bum, Southern Province, Sierra Leone",
        "country_code": "SL"
    },
    {
        "name": "Anus, France",
        "lat": "47.1167",
        "lon": "0.0667",
        "short_name": "Anus, FR",
        "display_name": "Anus, Yonne, Bourgogne-Franche-Comté, France",
        "country_code": "FR"
    },
    {
        "name": "Fucking, Austria",
        "lat": "48.0673",
        "lon": "12.8633",
        "short_name": "Fugging, AT",
        "display_name": "Fugging (formerly Fucking), Tarsdorf, Oberösterreich, Austria",
        "country_code": "AT"
    },
    {
        "name": "Middelfart, Denmark",
        "lat": "55.5061",
        "lon": "9.7302",
        "short_name": "Middelfart, DK",
        "display_name": "Middelfart, Region of Southern Denmark, Denmark",
        "country_code": "DK"
    },
    {
        "name": "Twatt, Scotland",
        "lat": "59.0833",
        "lon": "-3.0333",
        "short_name": "Twatt, GB",
        "display_name": "Twatt, Orkney, Scotland, United Kingdom",
        "country_code": "GB"
    },
    {
        "name": "Shitterton, England",
        "lat": "50.6667",
        "lon": "-2.1667",
        "short_name": "Shitterton, GB",
        "display_name": "Shitterton, Dorset, England, United Kingdom",
        "country_code": "GB"
    },
    {
        "name": "Dildo, Canada",
        "lat": "47.5667",
        "lon": "-53.5500",
        "short_name": "Dildo, CA",
        "display_name": "Dildo, Newfoundland and Labrador, Canada",
        "country_code": "CA"
    },
    {
        "name": "Tittybong, Australia",
        "lat": "-35.4667",
        "lon": "142.4833",
        "short_name": "Tittybong, AU",
        "display_name": "Tittybong, Victoria, Australia",
        "country_code": "AU"
    }
]

# Read the users file
with open('/home/zote/bots/jeeves/config/users.json', 'r') as f:
    users = json.load(f)

# Track changes
changes = []

# Find and fix the jokers
for user_id, user_data in users.items():
    # Check in the weather section for user_locations
    if 'weather' in user_data and 'user_locations' in user_data['weather']:
        for loc_id, location in user_data['weather']['user_locations'].items():
            user_input = location.get('user_input', '').lower().strip()

            # Check if they literally put "location" or "location here"
            if user_input in ['location', 'location here']:
                # Pick a random rude place
                rude_place = random.choice(RUDE_PLACES)

                old_name = location.get('short_name', location.get('display_name', 'unknown'))

                # Update the location data
                location['lat'] = rude_place['lat']
                location['lon'] = rude_place['lon']
                location['short_name'] = rude_place['short_name']
                location['display_name'] = rude_place['display_name']
                location['country_code'] = rude_place['country_code']
                # Keep the user_input as-is so they know what they did wrong :)

                changes.append(f"User {user_id}: {old_name} -> {rude_place['name']} (input was: '{user_input}')")

# Write back the modified data
if changes:
    with open('/home/zote/bots/jeeves/config/users.json', 'w') as f:
        json.dump(users, f, indent=4, ensure_ascii=False)

    print(f"Fixed {len(changes)} jokers:")
    for change in changes:
        print(f"  - {change}")
else:
    print("No jokers found! Everyone behaved properly.")
