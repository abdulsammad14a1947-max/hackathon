"""Create the hcm_lite database on the local portable PostgreSQL (idempotent)."""
import psycopg

DB_HOST = "127.0.0.1"
DB_PORT = 5433

with psycopg.connect(
    host=DB_HOST, port=DB_PORT, user="postgres", dbname="postgres", autocommit=True
) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", ("hcm_lite",))
        if cur.fetchone() is None:
            cur.execute("CREATE DATABASE hcm_lite")
            print("created database hcm_lite")
        else:
            print("database hcm_lite already exists")
        cur.execute("SELECT version()")
        print(cur.fetchone()[0])
