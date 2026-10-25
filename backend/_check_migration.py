"""Throwaway: count tables created by `alembic upgrade head` in migration_check.db."""
import sqlite3

c = sqlite3.connect("migration_check.db")
tables = sorted(r[0] for r in c.execute("select name from sqlite_master where type='table'"))
print("table count:", len(tables))
print(", ".join(tables))
