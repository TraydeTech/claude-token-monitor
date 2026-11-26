#!/usr/bin/env python3
"""Claude Token Monitor launcher."""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from claude_monitor.app import main

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Claude Token Monitor")
    parser.add_argument(
        "--limit",
        type=int,
        default=200_000,
        help="Token limit for the 4-hour window (default: 200000)",
    )
    args = parser.parse_args()
    sys.exit(main(token_limit=args.limit))
