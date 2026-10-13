#!/usr/bin/env python3
"""N.A.N.I. V2 Root Launcher"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from nani.main import main

if __name__ == "__main__":
    sys.exit(main())
