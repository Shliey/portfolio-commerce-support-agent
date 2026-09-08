from __future__ import annotations

import argparse
import os
from pathlib import Path

from commerce_support.repository import SQLiteRepository


def main() -> None:
    parser = argparse.ArgumentParser(description="Create/migrate and seed the demo business DB")
    parser.add_argument(
        "--database",
        type=Path,
        default=Path(os.getenv("BUSINESS_DB", "data/business.db")),
    )
    args = parser.parse_args()
    with SQLiteRepository(args.database) as repository:
        repository.seed()
    print(f"seeded={args.database}")


if __name__ == "__main__":
    main()
