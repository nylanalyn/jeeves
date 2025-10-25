#!/bin/bash

# Setup cron job for automatic theme switching
# This script sets up a cron job that runs at midnight on November 1st

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
THEME_SWITCHER="$SCRIPT_DIR/theme_switcher.py"

# Create temporary crontab file
TEMP_CRON=$(mktemp)

# Export current crontab
crontab -l > "$TEMP_CRON" 2>/dev/null || echo "# Crontab for Jeeves theme switching" > "$TEMP_CRON"

# Check if the theme switcher cron job already exists
if ! grep -q "theme_switcher.py" "$TEMP_CRON"; then
    # Add new cron job for November 1st at 00:00
    echo "# Auto-switch to Noir November theme at midnight on November 1st" >> "$TEMP_CRON"
    echo "0 0 1 11 * cd $SCRIPT_DIR && /usr/bin/python3 $THEME_SWITCHER >> $SCRIPT_DIR/theme_switch.log 2>&1" >> "$TEMP_CRON"

    # Install new crontab
    crontab "$TEMP_CRON"
    echo "✅ Theme switcher cron job installed for November 1st"
else
    echo "⚠️  Theme switcher cron job already exists"
fi

# Clean up
rm -f "$TEMP_CRON"

echo "Theme switching cron setup complete!"
echo "The theme will automatically switch to Noir November at midnight on November 1st"
echo "You can also run it manually with: $THEME_SWITCHER"