"""Remove the pre-2.0 RoleSignal / CS5588 files that the new JobPilot architecture replaces.

Usage:  python scripts/cleanup_legacy.py          (dry run)
        python scripts/cleanup_legacy.py --yes    (delete)
Everything stays recoverable through git history.
"""

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ["agents", "data", "evals", "report", "tests/test_agents.py", "__pycache__"]


def main() -> None:
    targets = [ROOT / p for p in LEGACY if (ROOT / p).exists()]
    if not targets:
        print("Nothing to clean.")
        return
    for t in targets:
        print(("deleting " if "--yes" in sys.argv else "would delete ") + str(t.relative_to(ROOT)))
        if "--yes" in sys.argv:
            shutil.rmtree(t) if t.is_dir() else t.unlink()
    if "--yes" not in sys.argv:
        print("\nRe-run with --yes to delete (or: git rm -r agents data evals report tests/test_agents.py).")


if __name__ == "__main__":
    main()
