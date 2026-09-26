#!/usr/bin/env python3
"""Run the shared site validation used by CI and production builds."""

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
CHECKS = (
    ("scripts/check_public_repo_hygiene.py",),
    ("scripts/build_all.py",),
    ("scripts/lint_knowledge_base.py",),
    ("scripts/lint_provenance.py",),
    ("-m", "unittest", "discover", "-s", "tests"),
)


def main() -> int:
    for args in CHECKS:
        print(f"Running: python3 {' '.join(args)}", flush=True)
        result = subprocess.run((sys.executable, *args), cwd=ROOT)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
