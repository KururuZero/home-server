# Home Server

A headless Ubuntu Server 24.04 machine that runs a 24/7 financial market-data pipeline and a Discord monitoring bot. This repository is a sanitised snapshot of the code and operational setup.

The pipeline collects real-time Binance Futures Level-2 order book data into PostgreSQL. The Discord bot exposes a local HTTP endpoint so any other program on the server can send a message to a channel, and it also sends scheduled health reports with hardware metrics.

## Architecture

- Hardware: Dell Vostro 3710 SFF, Intel i5-12400, 16 GB RAM, 256 GB NVMe + 1 TB SATA
- OS: Ubuntu Server 24.04 LTS (headless, no GUI)
- Access: SSH key authentication only, Tailscale VPN (no public ports), UFW firewall, fail2ban
- Database: PostgreSQL 18, storing tens of millions of order book rows
- Services run under tmux, managed from a terminal over SSH

## Services

### Data collector (`data-collector/`)

A 24/7 pipeline that ingests real-time order book snapshots from the Binance Futures WebSocket API.

- Source: `btcusdt@depth5@100ms` — top 5 price levels, 100 ms cadence
- Writes to a PostgreSQL table `futures_orderbook_depth_5` with 23 columns (timestamp, 5 × [bid, bid_qty, ask, ask_qty], mid, spread)
- Batches 500 rows per insert using `psycopg2.extras.execute_values`
- Roughly 600 rows/minute sustained (~500k–750k rows/day depending on connection uptime)
- Bulk-loading script for historical CSV files (~12 GB, ~80 files) using PostgreSQL `COPY`
- One-off repair script for a malformed CSV (skips rows with wrong column counts rather than aborting)

Data quality:

- Freshness checks compare the newest row timestamp against wall-clock time
- Duplicate detection (used to catch a duplicate collector process)
- Fixed-depth padding for symbols with fewer than 5 price levels

### Discord monitor (`discord-monitor/`)

A Discord bot that runs 24/7 and provides two things:

1. Scheduled health reports — sent twice daily (00:00 and 12:00 HKT) with average and maximum CPU temperature, fan speed, and current disk usage for `/` and `/mnt`
2. A local HTTP `/notify` endpoint — lets any other program on the server send a message to a channel

The `/notify` endpoint requires a shared secret header. It is bound to `127.0.0.1` only (not exposed to the network). Every other program on the server (collector, importers, cron jobs) uses the `notify.py` helper rather than embedding credentials:

```python
import sys
sys.path.insert(0, "/mnt/projects/Discord_Monitor_Bot")
from notify import notify_safe
notify_safe("collector restarted")
