# Theme Operations

## Switching Quest Themes
All quest narrative and styling now live in a single consolidated file: `quest_content.json`.  
The file exposes a `themes` map where each key is a theme slug (for example `noir_november`, `december_shopping`, `neon_frontier`).

To activate a theme:

1. Set the slug in `config/config.yaml` under the quest section:
   ```yaml
   quest:
       theme: "december_shopping"
   ```
2. Reload the quest module so it re-reads the config and content:
   ```bash
   !admin reload quest
   ```

The web dashboard will automatically follow the same theme selection.

## Injury System Reference
Injuries are bundled with each theme under the `injury_system` key. Mechanics (duration, effects) stay fixed while names and descriptions provide flavor:

| Theme | Injuries |
|-------|----------|
| Noir November | Pistol Whipped, Knife Wound, Bourbon Hangover, Cigarette Burn, Broken Ribs |
| December Shopping | Paper Cut, Sore Feet, Stress Headache, Cookie Burn, Wallet Strain |
| Neon Frontier | Neural Feedback, System Overload, Code Injection, Data Corruption, Power Drain |

Use this list when crafting announcements or verifying in-game flavor text. Each injury retains the same duration/effect pairing, keeping balance intact while swapping narrative context.

## System Changes (Summary)
- `quest_content.json` now wraps multiple themes; the quest module selects one based on `quest.theme`.
- `_get_content("injury_system", ...)` still falls back to `config.yaml` only when the theme omits data.
- Admin commands, quest displays, and the web UI automatically respect the configured theme.

## Future Enhancements
- Add optional `item_names` to theme files so consumables and loot reflect the chosen narrative.
- Automate seasonal rotations by mapping months to theme slugs.
