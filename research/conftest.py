"""Make the prototype package importable without touching project configuration."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
