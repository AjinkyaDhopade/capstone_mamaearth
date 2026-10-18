
import csv
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DB = DATA / "mamaearth.db"

TABLES = {
    "customers": [
        "customer_id", "name", "city", "city_tier",
        "signup_date", "acquisition_source"
    ],
    "products": [
        "product_id", "product_name", "category", "price"
    ],
    "orders": [
        "order_id", "customer_id", "product_id", "order_date",
        "quantity", "discount_pct", "payment_method",
        "rating", "returned"
    ],
}


def load_csv(conn, table, columns):
    path = DATA / f"{table}.csv"
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = [
            tuple(
                row[column] if row[column] not in ("", None) else None
                for column in columns
            )
            for row in reader
        ]

    placeholders = ", ".join("?" for _ in columns)
    column_sql = ", ".join(columns)
    conn.executemany(
        f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders})",
        rows,
    )
    print(f"Loaded {len(rows)} rows into {table}.")


def main():
    DATA.mkdir(exist_ok=True)

    with sqlite3.connect(DB) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(
            (ROOT / "sql" / "schema.sql").read_text(encoding="utf-8")
        )

        # Clear child table before parent tables so reruns are safe.
        conn.execute("DELETE FROM orders")
        conn.execute("DELETE FROM products")
        conn.execute("DELETE FROM customers")

        for table in ("customers", "products", "orders"):
            load_csv(conn, table, TABLES[table])

        for table in TABLES:
            count = conn.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
            print(f"Verification: {table} = {count}")

        assert conn.execute(
            "SELECT COUNT(*) FROM customers"
        ).fetchone()[0] == 45
        assert conn.execute(
            "SELECT COUNT(*) FROM products"
        ).fetchone()[0] == 16
        assert conn.execute(
            "SELECT COUNT(*) FROM orders"
        ).fetchone()[0] == 180

    print(f"Database created successfully: {DB}")


if __name__ == "__main__":
    main()
