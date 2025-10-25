#!/usr/bin/env python3
"""
Theme switcher for Jeeves bot
Automatically switches themes based on the current month
"""

import os
import shutil
import json
import yaml
from datetime import datetime

def switch_quest_theme():
    """Switch quest content based on current month"""
    current_month = datetime.now().month

    if current_month == 11:  # November - Noir theme
        print("Switching to Noir November theme...")

        # Backup original quest content if not already backed up
        if not os.path.exists("quest_content_halloween_backup.json"):
            if os.path.exists("quest_content.json"):
                shutil.copy2("quest_content.json", "quest_content_halloween_backup.json")
                print("Backed up Halloween quest content")

        # Apply noir theme
        if os.path.exists("quest_content_noir.json"):
            shutil.copy2("quest_content_noir.json", "quest_content.json")
            print("Applied Noir quest theme")
        else:
            print("Noir quest content not found")

    elif current_month == 10:  # October - Halloween theme
        print("Switching to Halloween theme...")

        # Restore Halloween theme if backup exists
        if os.path.exists("quest_content_halloween_backup.json"):
            shutil.copy2("quest_content_halloween_backup.json", "quest_content.json")
            print("Restored Halloween quest theme")
        else:
            print("No Halloween backup found")

    else:
        print(f"Month {current_month} - no theme change needed")

def switch_hunt_theme():
    """Switch hunt animals in config based on current month"""
    current_month = datetime.now().month
    config_file = "config/config.yaml"

    if current_month == 11:  # November - Noir theme
        print("Switching hunt to Noir theme...")

        # Load current config
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)

            # Backup original hunt config if not already backed up
            if not os.path.exists("config/config_halloween_backup.yaml"):
                shutil.copy2(config_file, "config/config_halloween_backup.yaml")
                print("Backed up Halloween hunt config")

            # Load noir hunt config and merge
            if os.path.exists("config_hunt_noir.yaml"):
                with open("config_hunt_noir.yaml", 'r') as f:
                    noir_hunt = yaml.safe_load(f)

                if 'hunt' in noir_hunt:
                    config['hunt'] = noir_hunt['hunt']

                    # Save updated config
                    with open(config_file, 'w') as f:
                        yaml.dump(config, f, default_flow_style=False)

                    print("Applied Noir hunt theme")
                else:
                    print("No hunt section found in noir config")
            else:
                print("Noir hunt config not found")

    elif current_month == 10:  # October - Halloween theme
        print("Switching hunt to Halloween theme...")

        # Restore Halloween theme if backup exists
        if os.path.exists("config/config_halloween_backup.yaml"):
            shutil.copy2("config/config_halloween_backup.yaml", config_file)
            print("Restored Halloween hunt theme")
        else:
            print("No Halloween hunt backup found")

    else:
        print(f"Month {current_month} - no hunt theme change needed")

def switch_web_theme():
    """Switch web UI theme based on current month"""
    current_month = datetime.now().month
    web_theme_file = "web/quest/theme.json"

    if current_month == 11:  # November - Noir theme
        print("Switching web UI to Noir theme...")

        # Backup original web theme if not already backed up
        if not os.path.exists("web/quest/theme_halloween_backup.json"):
            if os.path.exists(web_theme_file):
                shutil.copy2(web_theme_file, "web/quest/theme_halloween_backup.json")
                print("Backed up Halloween web theme")

        # Apply noir web theme
        if os.path.exists("web_theme_noir.json"):
            shutil.copy2("web_theme_noir.json", web_theme_file)
            print("Applied Noir web theme")
        else:
            print("Noir web theme not found")

    elif current_month == 10:  # October - Halloween theme
        print("Switching web UI to Halloween theme...")

        # Restore Halloween theme if backup exists
        if os.path.exists("web/quest/theme_halloween_backup.json"):
            shutil.copy2("web/quest/theme_halloween_backup.json", web_theme_file)
            print("Restored Halloween web theme")
        else:
            print("No Halloween web theme backup found")

    else:
        print(f"Month {current_month} - no web theme change needed")

def main():
    """Main theme switching logic"""
    print(f"Theme switcher running for {datetime.now().strftime('%Y-%m-%d')}")

    switch_quest_theme()
    switch_hunt_theme()
    switch_web_theme()

    print("Theme switching complete!")

if __name__ == "__main__":
    main()