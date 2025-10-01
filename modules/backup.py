"""
State Backup Module - Automated state.json backups
Runs daily at 2am, keeps last 3 backups
"""

import os
import shutil
import glob
from datetime import datetime
import schedule
from .base import ModuleBase

def setup(bot):
    """Module setup entry point."""
    return BackupModule(bot)

class BackupModule(ModuleBase):
    """Automated backup module for state.json."""

    name = "backup"
    version = "1.0.0"
    description = "Automated daily backups of state.json at 2am, keeping last 3 backups"

    def __init__(self, bot):
        super().__init__(bot)
        self.state_file = "config/state.json"
        self.backup_dir = "config"
        self.max_backups = 3

    def on_load(self):
        """Schedule daily backup at 2am."""
        schedule.every().day.at("02:00").do(self._perform_backup).tag(f"{self.name}-daily-backup")
        self.bot.log_message(f"[{self.name}] Scheduled daily backup at 2am")

    def on_unload(self):
        """Clean up scheduled tasks."""
        schedule.clear(f"{self.name}-daily-backup")

    def _perform_backup(self):
        """Perform the backup operation."""
        try:
            if not os.path.exists(self.state_file):
                self.bot.log_message(f"[{self.name}] WARNING: {self.state_file} not found, skipping backup")
                return

            # Force save current state before backup
            self.bot.state_manager.force_save()

            # Create backup filename with current date
            timestamp = datetime.now().strftime("%Y%m%d")
            backup_file = os.path.join(self.backup_dir, f"state.bak-{timestamp}")

            # Copy state.json to backup
            shutil.copy2(self.state_file, backup_file)
            self.bot.log_message(f"[{self.name}] Created backup: {backup_file}")

            # Clean up old backups, keeping only the last N
            self._cleanup_old_backups()

        except Exception as e:
            self.bot.log_message(f"[{self.name}] ERROR during backup: {e}")

    def _cleanup_old_backups(self):
        """Remove old backups, keeping only the most recent N."""
        try:
            # Find all backup files
            backup_pattern = os.path.join(self.backup_dir, "state.bak-*")
            backups = sorted(glob.glob(backup_pattern), reverse=True)

            # Remove backups beyond the limit
            for old_backup in backups[self.max_backups:]:
                os.remove(old_backup)
                self.bot.log_message(f"[{self.name}] Removed old backup: {old_backup}")

        except Exception as e:
            self.bot.log_message(f"[{self.name}] ERROR during cleanup: {e}")
