import os
import psycopg2
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timezone
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

# Query window and output file (overridable via env)
QUERY_DATE = os.getenv("QUERY_DATE", "2026-08-15")   # YYYY-MM-DD, interpreted in UTC
OUTPUT_PNG = os.getenv("OUTPUT_PNG", "orderbook_plot.png")


def query_data():
    year, month, day = (int(x) for x in QUERY_DATE.split("-"))
    start_dt = datetime(year, month, day, 0, 0, 0, tzinfo=timezone.utc)
    end_dt   = datetime(year, month, day, 23, 59, 59, tzinfo=timezone.utc)

    start_ms = int(start_dt.timestamp() * 1000)
    end_ms   = int(end_dt.timestamp() * 1000)

    print(f"Querying data from {start_dt} to {end_dt}...")

    conn = psycopg2.connect(
        host=DB_HOST,
        port=int(DB_PORT),
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
    )
    try:
        # Parameterised query - placeholders are filled by the driver,
        # so the values are never interpolated into the SQL string.
        query = """
            SELECT timestamp, best1_bid, best1_ask, mid
            FROM futures_orderbook_depth_5
            WHERE timestamp >= %s AND timestamp <= %s
            ORDER BY timestamp ASC
        """
        cursor = conn.cursor()
        cursor.execute(query, (start_ms, end_ms))
        cols = [d[0] for d in cursor.description]
        rows = cursor.fetchall()
        cursor.close()
        df = pd.DataFrame(rows, columns=cols)
    finally:
        conn.close()

    print(f"Successfully loaded {len(df)} rows into Pandas DataFrame.")
    return df


def plot_data(df):
    if df.empty:
        print("No data to plot.")
        return

    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)

    plt.figure(figsize=(12, 6))
    plt.plot(df['datetime'], df['best1_bid'], label='Best Bid', color='green', alpha=0.7)
    plt.plot(df['datetime'], df['best1_ask'], label='Best Ask', color='red', alpha=0.7)
    plt.plot(df['datetime'], df['mid'],        label='Mid Price', color='blue', linewidth=1)

    plt.title(f'BTCUSDT Futures Order Book - {QUERY_DATE} (UTC)')
    plt.xlabel('Time')
    plt.ylabel('Price (USDT)')
    plt.legend()
    plt.grid(True, alpha=0.3)

    # Save to file (headless server - cannot use plt.show())
    plt.savefig(OUTPUT_PNG, dpi=150, bbox_inches='tight')
    print(f"Plot saved as '{OUTPUT_PNG}'")


if __name__ == "__main__":
    df = query_data()
    plot_data(df)
