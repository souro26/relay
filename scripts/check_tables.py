"""Utility script to verify table schemas in the database."""

import sys
from pathlib import Path

# Ensure project root src is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import text

from relay.db.session import engine


def main() -> None:
    with engine.connect() as conn:
        print("--- PostgreSQL Tables ---")
        try:
            query = "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            result = conn.execute(text(query)).fetchall()
            for row in result:
                print(f"Table: {row[0]}")
        except Exception as e:
            print(f"Could not inspect PostgreSQL information_schema: {e}")

        print("\n--- SQLite Tables ---")
        try:
            result = conn.execute(
                text("SELECT table_name FROM sqlite_master WHERE type='table'")
            ).fetchall()
            for row in result:
                print(f"SQLite Table: {row[0]}")
        except Exception as e:
            print(f"Could not inspect SQLite master: {e}")


if __name__ == "__main__":
    main()
