IRC Fishing Bot - Implementation Plan
Core Mechanics:

!cast command - Initiates a fishing attempt

Randomly generates cast distance (store with timestamp)
Provides flavor text: "You cast your line, it goes [distance]m and floats quietly"
Records cast time for wait duration calculation


!reel command - Completes the fishing attempt

Calculates wait time since cast
Longer wait = bigger fish (with diminishing returns to prevent infinite waiting)
Success chance based on wait time + player level + random events
Can result in: fish catch, junk item, broken line, or nothing


Fish Database:

Real and fictional fish with weight ranges (lbs)
Rarity tiers (common, uncommon, rare, legendary)
Location-specific fish pools (puddle fish vs moon fish)
Distance requirements for certain fish types


Leveling System:

XP awarded based on fish size/rarity
Level thresholds determine fishing location
Locations: Puddle (0) → Pond (1) → Lake (2) → River (3) → Ocean (4) → Deep Sea (5) → Moon (6) → Mars (7) → [Cap at your preference]
Higher levels unlock crazier fish


Junk Items:

Boots, tires, shopping carts, underwear, license plates, etc.
Small XP reward for cleaning up the environment
Possibly location-specific junk (moon garbage is different than pond garbage)


Broken Lines:

Probability increases with fish size
Lost fish if line breaks
Flavor text about "the one that got away"
Maybe track broken line stats


Random Events (announced by Jeeves when someone casts):

Full Moon: Rare fish spawn rate increased
Solar Flare (Mars): Double XP/size
Feeding Frenzy: Reduced wait time needed
Murky Waters: Increased junk catch rate
Meteor Shower (space locations): Chance of alien fish
Events trigger on timer or random chance when anyone casts


Achievements:

First Fish
Catch X total fish
Catch specific rare/legendary fish
Cast X total times
Reach max distance
Catch junk items
Break X lines
Reach each location tier
Catch fish in every location


Stats Tracking:

Fishing level
Total fish caught
Biggest fish (by weight)
Total casts
Furthest cast
Lines broken
Current location


Integration:

Tie into existing XP/achievement system
Stats visible in !stats command and on stats website (Need to modify in web/)
Achievements added to current achievement pool from achievements.py
Leaderboards for biggest fish, total catches, etc.



Technical Considerations:

Store active casts with timestamp in memory/database
Persist player fishing data (level, catches, stats)
Random event state management (duration, active effects)
Distance-based fish pool filtering
Wait time calculations with diminishing returns curve
Line break probability algorithm based on fish size

Commands:

!cast - Cast your fishing line
!reel - Reel in your catch
!fishing or !fishstats - Show your fishing statistics
!aquarium - Show your rare/legendary catches (optional trophy room)

Fun Additions to Consider:

Fishing tournaments (timed events, biggest catch wins)
Trading fish with other players
Fish recipes/cooking system
Bait system (different bait attracts different fish)
Weather effects influencing catches

Start with core cast/reel mechanics, basic fish database, and leveling system. Add events and achievements once foundation is solid.