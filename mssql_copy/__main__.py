import argparse
import sys

from mssql_copy.config import load_config
from mssql_copy.copy import copy_all_tables
from mssql_copy.db import connect


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copy data between two MSSQL databases."
    )

    parser.add_argument(
        "--config",
        default="config.yml",
        help="Path to YAML config file. Default: config.yml",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        config = load_config(args.config)

        source_conn = connect(config.source, config.options)
        target_conn = connect(config.target, config.options)

        try:
            copy_all_tables(source_conn, target_conn, config)
        finally:
            source_conn.close()
            target_conn.close()

        print("\nCopy finished successfully.")
        return 0

    except Exception as error:
        print(f"\nCopy failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
