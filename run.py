#!/usr/bin/env python3
"""
Run script for Claude Dictate
Use this to run the application from the claude-dictate directory.
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.main import main

if __name__ == "__main__":
    main()
