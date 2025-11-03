# December Holiday Shopping Theme

## Activation Instructions

### One-Step Theme Activation
```bash
# Backup current theme (optional)
cp quest_content.json quest_content_backup.json

# Activate December theme
cp quest_content_december.json quest_content.json

# Reload in IRC
!admin reload quest
```

That's it! The theme file now includes injuries, monsters, classes, and all story elements, so everything changes automatically.

## Optional: Update Item Display Names (Future Enhancement)
Currently items like "medkit", "energy_potion", etc. are hardcoded. Here are thematic alternatives:

| Current Item | December Theme Alternative |
|--------------|---------------------------|
| Medkit | First Aid Kit / Band-Aid Box / Healing Balm |
| Energy Potion | Coffee / Peppermint Latte / Hot Cocoa |
| Lucky Charm | Gift Card / Coupon Book / Store Credit |
| Armor Shard | Shopping Bag / Cart Upgrade / Reusable Tote |
| XP Scroll | Shopping List / Strategy Guide / Mall Map |
| Dungeon Relic | VIP Shopper Pass / Store Manager's Special / Golden Ticket |

**Note:** To fully theme items, we'd need to add an "item_names" section to the quest_content JSON and update the quest module to use themed names when displaying items.

## Theme Features

### Visual Design
- **Colors:** Festive red (#c41e3a) and evergreen (#2d5f3f) with gold accents
- **Prestige Icons:**
  - Tier 1: 🎁 (Gifts)
  - Tier 2: 🎄 (Christmas Tree)
  - Tier 3: ⭐ (Star)

### Combat Reframing
Instead of fighting monsters, players are "dealing with" or "overcoming" shopping obstacles:
- **Monsters** = Shopping hazards (traffic, lines, out-of-stock items)
- **Winning** = Successfully navigating the challenge
- **Losing** = Item sold out, too stressed, gave up

### Character Classes
- **Planner:** Organized, strategic, uses lists and spreadsheets
- **Procrastinator:** Last-minute, panic-driven, caffeinated
- **Bargain Hunter:** Deal-seeking, coupon-clipping, clearance rack expert

### Injuries (Holiday Shopping Hazards)
- Paper Cut (from wrapping)
- Sore Feet (from mall walking)
- Stress Headache (from crowds and chaos)
- Cookie Burn (from holiday baking)
- Wallet Strain (from overspending)

### Boss Encounters
- **Black Friday Stampede** - The ultimate shopping chaos
- **The Last Minute Shopper** - Racing against the clock
- **Santa's Naughty List Coordinator** - The final challenge

## Reverting to Previous Theme

```bash
# Go back to Noir November (or whatever was active)
cp quest_content_noir.json quest_content.json
!admin reload quest

# Restore original injuries in config/config.yaml
# Then: !admin config reload
```

## What's Now Theme-able

The following elements automatically change when you switch theme files:

✅ **Visual Design** (colors, icons, prestige tiers)
✅ **World Lore** (ambient flavor text)
✅ **Story Beats** (combat openers and action text)
✅ **Monsters** (enemies and their stats)
✅ **Boss Monsters** (special encounters)
✅ **Character Classes** (class names, descriptions, actions)
✅ **Injuries** (types, descriptions, durations, effects) - **NEW!**

## Future Enhancements

To make theming even more seamless, consider:

1. **Config-based theme selection**
   - Add `quest.active_theme: "december"` to config
   - Module automatically loads `quest_content_{theme}.json`

2. **Item name theming**
   - Add `"item_names": {...}` section to theme JSON
   - Update quest module to use themed names in all messages

3. **Seasonal auto-switching**
   - Auto-detect current month
   - Switch themes automatically (noir in November, holiday in December, etc.)
