#!/usr/bin/env python3
"""
Unified web UI launcher (quest + stats).

Kept for compatibility with documentation that references `web/quest_web.py`.

Usage:
    python web/quest_web.py --host 127.0.0.1 --port 8080
"""

import sys
from pathlib import Path

# Ensure repo root is on sys.path for `import web.*`
sys.path.insert(0, str(Path(__file__).parent.parent))

from web.server import main

if __name__ == "__main__":
    main()
