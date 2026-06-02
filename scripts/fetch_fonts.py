#!/usr/bin/env python3
"""Pre-fetch the OFL fonts used for rendering.

Optional: the renderer fetches them automatically on first run. Run this to
warm the cache (e.g. in CI or a Docker build with network access):

    python scripts/fetch_fonts.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arts.config import Config
from arts.utils import ensure_fonts

if __name__ == "__main__":
    ensure_fonts(Config.load())
    print("fonts ready in assets/fonts/")
