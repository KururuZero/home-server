import os
import psycopg2

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
    raise SystemExit("DB_PASSWORD not set - check ~/.config/secrets/.env")

# Data directory and specific files
# This is a one-off repair script for the corrupted 2026-09-29 file.
DATA_DIR = os.getenv("DATA_DIR", "/mnt/raw_orderbook")
BAD_FILE   = os.path.join(DATA_DIR, "live_futures_live_orderbook_depth_2026-09-29.csv")
CLEAN_FILE = os.path.join(DATA_DIR, "clean_2026-09-29.csv")

if not os.path.isfile(BAD_FILE):
    raise SystemExit(f"Source file not found: {BAD_FILE}")


def clean_file():
    """Keep only lines with exactly 23 columns (22 commas)."""
    print(f"Cleaning file: {BAD_FILE}")
    kept = 0
    skipped = 0
    with open(BAD_FILE, 'r') as f_in, open(CLEAN_FILE, 'w') as f_out:
        for i, line in enumerate(f_in):
            if line.count(',') == 22:
                f_out.write(line)
                kept += 1
            else:
                skipped += 1
                print(f"Skipping corrupted line at row {i+1}: {line[:50]}")
    print(f"Kept {kept} lines, skipped {skipped} corrupted lines.")


def load_to_db():
    """Bulk insert the cleaned file via COPY."""
    print("Loading cleaned file to DB...")
    conn = psycopg2.connect(
        host=DB_HOST,
        port=int(DB_PORT),
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
    )
    cursor = conn.cursor()
    try:
        with open(CLEAN_FILE, 'r') as f:
            cursor.copy_expert("""
                COPY futures_orderbook_depth_5
                FROM STDIN
                WITH (FORMAT CSV, HEADER TRUE, ON_ERROR IGNORE)
            """, f)
        conn.commit()
        print("Cleaned file successfully loaded.")
    except Exception as e:
        conn.rollback()
        print(f"Error: {e}")
    finally:
        cursor.close()
        conn.close()


def main():
    clean_file()
    load_to_db()

    # Remove the temporary clean file
    if os.path.exists(CLEAN_FILE):
        os.remove(CLEAN_FILE)
        print(f"Removed temporary file: {CLEAN_FILE}")


if __name__ == "__main__":
    main()
