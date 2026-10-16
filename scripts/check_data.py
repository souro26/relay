"""Utility script to verify orders and idempotency keys in the database."""

import sys
from pathlib import Path

# Ensure project root src is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import text

from relay.db.session import engine


def main() -> None:
    with engine.connect() as conn:
        print("--- Orders ---")
        result = conn.execute(text("SELECT id, customer_id, status FROM orders")).fetchall()
        for row in result:
            print(f"id={row[0]}, customer_id={row[1]}, status={row[2]}")

        print("\n--- Idempotency Keys ---")
        result = conn.execute(
            text("SELECT order_id, idempotency_key FROM idempotency_keys")
        ).fetchall()
        for row in result:
            print(f"order_id={row[0]}, key={row[1]}")


if __name__ == "__main__":
    main()
