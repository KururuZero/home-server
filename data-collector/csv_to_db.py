import os
import glob
import psycopg2
import time

from pathlib import Path
from dotenv import load_dotenv

# Load secrets from the central file (never hardcode credentials)
CENTRAL_ENV = Path.home() / ".config" / "secrets" / ".env"
LOCAL_ENV   = Path(__file__).resolve().parent / ".env"

if CENTRAL_ENV.exists():
    load_dotenv(CENTRAL_ENV)
if LOCAL_ENV.exists():
    load_dotenv(LOCAL_ENV, override=True)

# Database connection parameters
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "data_db")
DB_USER = os.getenv("DB_USER", "kururuzero")
DB_PASS = os.getenv("DB_PASSWORD") or os.getenv("DB_PASS")

if not DB_PASS:
    raise SystemExit("DB_PASSWORD not set — check ~/.config/secrets/.env")

# Data and target
DATA_DIR   = os.getenv("DATA_DIR", "/mnt/raw_orderbook")
TABLE_NAME = os.getenv("TABLE_NAME", "futures_orderbook_depth_5")

if not os.path.isdir(DATA_DIR):
    raise SystemExit(f"DATA_DIR does not exist: {DATA_DIR}")


def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=int(DB_PORT),
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
    )


def load_csv_to_db(filepath, conn):
    """Uses PostgreSQL COPY command for ultra-fast bulk insert"""
    cursor = conn.cursor()
    try:
        with open(filepath, 'r') as f:
            cursor.copy_expert(f"""
                COPY {TABLE_NAME}
                FROM STDIN
                WITH (FORMAT CSV, HEADER TRUE, ON_ERROR IGNORE)
            """, f)
        conn.commit()
        print(f"Successfully loaded: {os.path.basename(filepath)}")
    except Exception as e:
        conn.rollback()
        print(f"Error loading {os.path.basename(filepath)}: {e}")
    finally:
        cursor.close()


def main():
    csv_files = glob.glob(os.path.join(DATA_DIR, "*.csv"))

    if not csv_files:
        print(f"No CSV files found in {DATA_DIR}.")
        return

    print(f"Found {len(csv_files)} CSV files in {DATA_DIR}")
    print(f"Loading into table: {TABLE_NAME}")
    conn = get_db_connection()

    start_time = time.time()
    for file in csv_files:
        load_csv_to_db(file, conn)

    conn.close()
    end_time = time.time()
    print(f"All done. Total time: {round(end_time - start_time, 2)} seconds.")


if __name__ == "__main__":
    main()
