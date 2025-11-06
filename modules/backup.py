"""
State Backup Module - Automated backups for Jeeves state files.
Runs daily at 2am, keeps last 3 backups for each managed state file.
"""

import os
import shutil
import glob
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, Tuple
import schedule
from .base import ModuleBase

def setup(bot: Any) -> 'BackupModule':
    """Module setup entry point."""
    return BackupModule(bot)

class BackupModule(ModuleBase):
    """Automated backup module for Jeeves state files."""

    name = "backup"
    version = "1.1.0"
    description = "Automated daily backups of state files at 2am, keeping last 3 backups per file"

    def __init__(self, bot: Any) -> None:
        super().__init__(bot)
        self.state_manager: Optional[Any] = getattr(self.bot, "state_manager", None)
        self.max_backups: int = 3
        self.managed_suffixes: Tuple[str, ...] = ("state", "games", "users", "stats")

        if not self.state_manager:
            self.state_dir: Optional[Path] = None
            self.backup_dir: Optional[Path] = None
            self.managed_files: List[Path] = []
            self.bot.log_debug(f"[{self.name}] ERROR: state manager unavailable, backups disabled")
            return

        self.state_dir = Path(self.state_manager.base_dir)
        self.backup_dir = self.state_dir / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.managed_files = [self.state_dir / f"{suffix}.json" for suffix in self.managed_suffixes]

    def on_load(self) -> None:
        """Schedule daily backup at 2am."""
        if not self.state_manager:
            self.bot.log_debug(f"[{self.name}] Backup scheduling skipped; state manager unavailable")
            return
        schedule.every().day.at("02:00").do(self._perform_backup).tag(f"{self.name}-daily-backup")
        self.bot.log_debug(f"[{self.name}] Scheduled daily backup at 2am")

    def on_unload(self) -> None:
        """Clean up scheduled tasks."""
        schedule.clear(f"{self.name}-daily-backup")

    def _perform_backup(self) -> None:
        """Perform the backup operation."""
        if not self.state_manager or not self.backup_dir:
            self.bot.log_debug(f"[{self.name}] WARNING: skipping backup; state manager unavailable")
            return

        try:
            self.state_manager.force_save()
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            self.backup_dir.mkdir(parents=True, exist_ok=True)

            for state_path in self.managed_files:
                if not state_path.exists():
                    self.bot.log_debug(f"[{self.name}] WARNING: {state_path} not found, skipping")
                    continue
                backup_file = self.backup_dir / f"{state_path.stem}.bak-{timestamp}{state_path.suffix}"
                shutil.copy2(state_path, backup_file)
                self.bot.log_debug(f"[{self.name}] Created backup: {backup_file}")

            self._cleanup_old_backups()

        except Exception as e:
            self.bot.log_debug(f"[{self.name}] ERROR during backup: {e}")

    def _cleanup_old_backups(self) -> None:
        """Remove old backups, keeping only the most recent N per state file."""
        try:
            for state_path in self.managed_files:
                pattern = str(self.backup_dir / f"{state_path.stem}.bak-*{state_path.suffix}")
                backups = sorted(glob.glob(pattern), reverse=True)
                for old_backup in backups[self.max_backups:]:
                    os.remove(old_backup)
                    self.bot.log_debug(f"[{self.name}] Removed old backup: {old_backup}")
        except Exception as e:
            self.bot.log_debug(f"[{self.name}] ERROR during cleanup: {e}")
