from __future__ import annotations

import argparse
import json
import sys

from app.core.preflight import run_preflight


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate backend configuration and optionally test PostgreSQL connectivity."
    )
    parser.add_argument(
        "--check-db",
        action="store_true",
        help="Run a read-only SELECT 1 connectivity check after configuration validation.",
    )
    args = parser.parse_args()
    report = run_preflight(check_connectivity=args.check_db)
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
