# file_lock.py
# Cross-process file locking utility for safe concurrent access to state files

import fcntl
import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

class FileLock:
    """Context manager for advisory file locking using fcntl.

    This provides inter-process locking for JSON state files to prevent
    corruption when both the IRC bot and web server access them simultaneously.

    Usage:
        with FileLock("/path/to/file.json"):
            # Read/write the file safely
            pass
    """

    def __init__(self, path: Path, timeout: float = 10.0):
        """
        Args:
            path: Path to the file to lock
            timeout: Maximum seconds to wait for lock acquisition
        """
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self.timeout = timeout
        self.lock_file: Optional[object] = None

    def __enter__(self):
        """Acquire the lock."""
        start_time = time.time()

        # Create lock file if it doesn't exist
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)

        while True:
            try:
                # Open lock file (create if doesn't exist)
                self.lock_file = open(self.lock_path, 'w')

                # Try to acquire exclusive lock (non-blocking)
                fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self

            except (IOError, OSError) as e:
                # Lock is held by another process
                if self.lock_file:
                    self.lock_file.close()
                    self.lock_file = None

                # Check timeout
                if time.time() - start_time >= self.timeout:
                    raise TimeoutError(
                        f"Could not acquire lock for {self.path} after {self.timeout}s"
                    ) from e

                # Wait a bit and retry
                time.sleep(0.01)

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Release the lock and clean up lock file."""
        if self.lock_file:
            try:
                fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
                self.lock_file.close()
            except Exception:
                logger.exception("Failed to release file lock for %s", self.path)
            finally:
                self.lock_file = None
            # Best-effort cleanup of lock file
            try:
                self.lock_path.unlink(missing_ok=True)
            except OSError:
                pass
        return False
