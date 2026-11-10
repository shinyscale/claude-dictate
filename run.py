#!/usr/bin/env python3
"""
Run script for Claude Dictate
Use this to run the application from the claude-dictate directory.
"""

import sys
import os

# Add src to path
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# Started at sign-in, the working folder is wherever Windows felt like
# (often System32); relative paths such as ./outputs must not land there.
os.chdir(HERE)

from src.main import main

if __name__ == "__main__":
    main()
