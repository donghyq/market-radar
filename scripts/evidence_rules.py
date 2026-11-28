"""Expose the root rules package to scripts run directly from this directory."""

import sys
from pathlib import Path


repo_root = str(Path(__file__).resolve().parents[1])
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from rules import *
from rules.engine import main


if __name__ == "__main__":
    main()
