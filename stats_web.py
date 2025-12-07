#!/usr/bin/env python3
"""
Launcher for Jeeves stats web UI.

Usage:
    python stats_web.py --host 127.0.0.1 --port 8081
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Import from the web.stats structure
from web.stats import main

if __name__ == "__main__":
    main()
