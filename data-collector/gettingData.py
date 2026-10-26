# Name: gettingData.py
import sys
import time
import websocket
import json
import os
import traceback
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

# ================= Config: load secrets from central file =================
CENTRAL_ENV = Path.home() / ".config" / "secrets" / ".env"
LOCAL_ENV   = Path(__file__).resolve().parent / ".env"

if CENTRAL_ENV.exists():
    load_dotenv(CENTRAL_ENV)
if LOCAL_ENV.exists():
    load_dotenv(LOCAL_ENV, override=True)

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "data_db")
DB_USER = os.getenv("DB_USER", "kururuzero")
DB_PASS = os.getenv("DB_PASSWORD")

if not DB_PASS:
    raise SystemExit(
        "DB_PASS not set - check ~/.config/secrets/.env for a DB_PASSWORD= line"
    )

# ================= Notifier: use the monitor bot's /notify endpoint =====
# Add the bot project to sys.path so we can import notify_safe()
sys.path.insert(0, "/mnt/projects/Discord_Monitor_Bot")
from notify import notify_safe


# ================= Database =================
def get_db_connection():
    """Establish and return a new database connection."""
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
    )


def flush_to_db(records):
    """Insert a batch of records into the PostgreSQL database."""
    if not records:
        return

    insert_query = """
        INSERT INTO futures_orderbook_depth_5 (
            timestamp, best1_bid, best1_bid_qty, best1_ask, best1_ask_qty,
            best2_bid, best2_bid_qty, best2_ask, best2_ask_qty,
            best3_bid, best3_bid_qty, best3_ask, best3_ask_qty,
            best4_bid, best4_bid_qty, best4_ask, best4_ask_qty,
            best5_bid, best5_bid_qty, best5_ask, best5_ask_qty,
            mid, spread
        ) VALUES %s
    """

    values = [
        (
            r['timestamp'], r['best1_bid'], r['best1_bid_qty'], r['best1_ask'], r['best1_ask_qty'],
            r['best2_bid'], r['best2_bid_qty'], r['best2_ask'], r['best2_ask_qty'],
            r['best3_bid'], r['best3_bid_qty'], r['best3_ask'], r['best3_ask_qty'],
            r['best4_bid'], r['best4_bid_qty'], r['best4_ask'], r['best4_ask_qty'],
            r['best5_bid'], r['best5_bid_qty'], r['best5_ask'], r['best5_ask_qty'],
            r['mid'], r['spread']
        )
        for r in records
    ]

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        psycopg2.extras.execute_values(cursor, insert_query, values)
        conn.commit()
        print(f"Successfully inserted {len(records)} records into Database.")
    except Exception as e:
        print(f"Database insert error: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()


# ================= WebSocket Collector =================
def getdata2():
    while True:
        try:
            SYMBOL = 'btcusdt'
            LEVELS = 5
            SAVE_INTERVAL = 500
            STREAM_URL = f"wss://fstream.binance.com/ws/{SYMBOL}@depth{LEVELS}@100ms"
            print(f"Connecting to {STREAM_URL}")

            records = []

            def on_message(ws, message):
                nonlocal records
                try:
                    data = json.loads(message)
                    if 'b' not in data or 'a' not in data:
                        return

                    timestamp = data.get('E', int(time.time() * 1000))
                    bids = data['b']
                    asks = data['a']

                    while len(bids) < LEVELS:
                        bids.append(["0", "0"])
                    while len(asks) < LEVELS:
                        asks.append(["0", "0"])

                    record = {'timestamp': timestamp}
                    for i in range(LEVELS):
                        record[f'best{i+1}_bid']     = float(bids[i][0])
                        record[f'best{i+1}_bid_qty'] = float(bids[i][1])
                        record[f'best{i+1}_ask']     = float(asks[i][0])
                        record[f'best{i+1}_ask_qty'] = float(asks[i][1])

                    record['mid']    = (record['best1_bid'] + record['best1_ask']) / 2.0
                    record['spread'] = record['best1_ask'] - record['best1_bid']

                    records.append(record)

                    if len(records) >= SAVE_INTERVAL:
                        flush_to_db(records)
                        records = []

                except Exception as e:
                    print(f"on_message error: {e}")

            def on_error(ws, error):
                print(f"WebSocket Error: {error}")

            def on_close(ws, close_status_code, close_msg):
                print("WebSocket closed. Saving remaining records to DB...")
                flush_to_db(records)
                print("Connection closed.")
                notify_safe(f"WebSocket disconnected (code: {close_status_code}). Reconnecting...")

            def on_open(ws):
                print("Connected to Binance Futures WebSocket. Streaming data to DB...")
                notify_safe("Collector started. Writing to PostgreSQL.")

            ws = websocket.WebSocketApp(
                STREAM_URL,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
            )

            ws.run_forever(ping_interval=30, ping_timeout=10)

        except KeyboardInterrupt:
            print("\nStopping data collector via Ctrl+C.")
            notify_safe("Collector stopped manually.")
            break
        except Exception as e:
            with open("error.log", "a") as f:
                f.write(f"{datetime.now()}: {e}\n{traceback.format_exc()}\n")
            print(f"WebSocket crashed: {e}. Restarting in 3 seconds...")
            notify_safe(f"Collector crashed: {e}. Restarting in 3 seconds.")
            time.sleep(3)


def main():
    getdata2()


if __name__ == '__main__':
    main()
