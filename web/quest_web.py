#!/usr/bin/env python3
"""
Backward compatibility wrapper for quest web UI.

This wrapper maintains compatibility with the original quest_web.py
while directing to the new organized structure.

Usage:
    python quest_web.py --host 127.0.0.1 --port 8080

The old arguments are still supported but internally use the new structure.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import from the new structure
from web.quest import main

if __name__ == "__main__":
    main()