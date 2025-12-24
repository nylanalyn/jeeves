#!/usr/bin/env python3
"""
Unified web UI launcher (quest + stats).

Usage:
    python stats_web.py --host 127.0.0.1 --port 8080
"""

import sys
from pathlib import Path

# Ensure repo root is on sys.path for `import web.*`
sys.path.insert(0, str(Path(__file__).parent))

from web.server import main

if __name__ == "__main__":
    main()
