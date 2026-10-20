import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

connection_string = {
    "host": os.getenv("PGHOST"),
    "port": os.getenv("PGPORT", "5432"),
    "dbname": os.getenv("PGDATABASE"),
    "user": os.getenv("PGUSER"),
    "password": os.getenv("PGPASSWORD"),
}

required = ["host", "dbname", "user", "password"]
missing = [key for key in required if not connection_string.get(key)]

if missing:
    raise ValueError(f"Missing database settings: {', '.join(missing)}")

with psycopg.connect(**connection_string) as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                current_database(),
                current_user,
                current_setting('server_version');
        """)
        database, user, version = cur.fetchone()

print(f"Database: {database}")
print(f"User: {user}")
print(f"PostgreSQL version: {version}")
print("Connection successful!")