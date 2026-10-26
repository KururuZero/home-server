"""
Discord monitoring bot with:
  - 00:00 / 12:00 HKT heartbeat + 12h hardware report
  - HTTP /notify endpoint so any other program can "shout" to the channel
  - /dblast slash command + !dblast prefix command (DB freshness check)
"""
import os
import asyncio
import psutil
import psycopg2
from datetime import datetime, time as dtime
from pathlib import Path

from dotenv import load_dotenv
import discord
from discord.ext import commands, tasks
from aiohttp import web

# ---------- config ----------
BASE_DIR    = Path(__file__).resolve().parent
CENTRAL_ENV = Path.home() / ".config" / "secrets" / ".env"
LOCAL_ENV   = BASE_DIR / ".env"

if CENTRAL_ENV.exists():
    load_dotenv(CENTRAL_ENV)
if LOCAL_ENV.exists():
    load_dotenv(LOCAL_ENV, override=True)

TOKEN          = os.getenv("DISCORD_BOT_TOKEN", "")
CHANNEL_ID     = int(os.getenv("DISCORD_CHANNEL_ID", "0") or 0)
NOTIFY_HOST    = os.getenv("NOTIFY_HOST", "127.0.0.1")
NOTIFY_PORT    = int(os.getenv("NOTIFY_PORT", "8765"))
NOTIFY_SECRET  = os.getenv("NOTIFY_SECRET", "")

DB_HOST        = os.getenv("DB_HOST", "localhost")
DB_PORT        = os.getenv("DB_PORT", "5432")
DB_NAME        = os.getenv("DB_NAME", "data_db")
DB_USER        = os.getenv("DB_USER", "kururuzero")
DB_PASSWORD    = os.getenv("DB_PASSWORD") or os.getenv("DB_PASS")

_missing = [n for n, v in (
    ("DISCORD_BOT_TOKEN", TOKEN),
    ("DISCORD_CHANNEL_ID", CHANNEL_ID),
    ("NOTIFY_SECRET", NOTIFY_SECRET),
) if not v]
if _missing:
    raise SystemExit(f"missing required env vars: {', '.join(_missing)} (check {CENTRAL_ENV})")

# DB_* is optional at startup (the bot still works without /dblast),
# but warn loudly so the operator notices.
if not DB_PASSWORD:
    print("[warn] DB_PASSWORD not set — /dblast and !dblast will fail")

# ---------- hardware monitoring ----------
TEMP_SENTINEL = -273.0
FAN_SENTINEL  = -9999

def get_cpu_temperature():
    try:
        temps = psutil.sensors_temperatures()
        if 'coretemp' in temps:
            return round(temps['coretemp'][0].current, 1)
        if 'acpitz' in temps:
            return round(temps['acpitz'][0].current, 1)
    except (AttributeError, IndexError):
        pass
    return None

def get_fan_speed():
    try:
        fans = psutil.sensors_fans()
        if fans:
            return next(iter(fans.values()))[0].current
    except (AttributeError, IndexError):
        pass
    return None

def get_disk_info():
    info = {}
    for part in psutil.disk_partitions(all=False):
        if part.mountpoint in ("/", "/mnt"):
            u = psutil.disk_usage(part.mountpoint)
            info[part.mountpoint] = {
                "total":   round(u.total / (1024**3), 1),
                "used":    round(u.used  / (1024**3), 1),
                "percent": u.percent,
            }
    return info

class MetricsTracker:
    """
    Sample buffers seeded with sentinel values so the list is never empty.
    Sentinels are popped at report time only when real data exists behind them.
    reset() re-seeds them so the next 12-hour cycle behaves identically.
    """
    def __init__(self):
        self.temps = [TEMP_SENTINEL]
        self.fans  = [FAN_SENTINEL]

    def record(self):
        t = get_cpu_temperature()
        if t is not None:
            self.temps.append(t)
        f = get_fan_speed()
        if f is not None:
            self.fans.append(f)

    def summary(self) -> str:
        if len(self.temps) > 1 and self.temps[0] == TEMP_SENTINEL:
            self.temps.pop(0)
        if len(self.fans) > 1 and self.fans[0] == FAN_SENTINEL:
            self.fans.pop(0)

        has_temp = bool(self.temps) and self.temps[0] != TEMP_SENTINEL
        has_fan  = bool(self.fans)  and self.fans[0]  != FAN_SENTINEL

        s = ""
        if has_temp:
            s += (
                f"CPU Temp (last 12h): avg {sum(self.temps)/len(self.temps):.1f}°C, "
                f"max {max(self.temps):.1f}°C\n"
            )
        else:
            s += "CPU Temp: data unavailable.\n"

        if has_fan:
            s += (
                f"Fan (last 12h): avg {sum(self.fans)/len(self.fans):.0f} RPM, "
                f"max {max(self.fans)} RPM\n"
            )
        else:
            s += "Fan: data unavailable.\n"

        return s

    def reset(self):
        self.temps = [TEMP_SENTINEL]
        self.fans  = [FAN_SENTINEL]

tracker = MetricsTracker()

# ---------- database freshness query (for /dblast) ----------
def _db_query_dblast():
    """Blocking DB query — always call via asyncio.to_thread()."""
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, database=DB_NAME,
        user=DB_USER, password=DB_PASSWORD,
        connect_timeout=10,
    )
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                  MAX(timestamp)                                                      AS newest_ts,
                  to_timestamp(MAX(timestamp)/1000.0) AT TIME ZONE 'Asia/Hong_Kong'   AS newest_hkt,
                  now()                               AT TIME ZONE 'Asia/Hong_Kong'   AS now_hkt,
                  (EXTRACT(EPOCH FROM NOW())*1000)::bigint - MAX(timestamp)           AS lag_ms
                FROM futures_orderbook_depth_5
            """)
            return cur.fetchone()
    finally:
        conn.close()

async def build_dblast_text() -> str:
    """Return the formatted /dblast message (plain text, no table)."""
    try:
        row = await asyncio.to_thread(_db_query_dblast)
    except Exception as e:
        return f"DB query failed: {e}"

    if row is None or row[0] is None:
        return "No rows in futures_orderbook_depth_5 yet."

    newest_ts, newest_hkt, now_hkt, lag_ms = row
    return (
        f"newest_ts: {newest_ts}\n"
        f"newest_hkt: {newest_hkt}\n"
        f"now_hkt: {now_hkt}\n"
        f"lag_ms: {lag_ms}"
    )

# ---------- discord bot ----------
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------- slash command: /dblast ----------
@bot.tree.command(name="dblast", description="Show last write time of futures_orderbook_depth_5")
async def dblast_slash(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    text = await build_dblast_text()
    await interaction.followup.send(text)

# ---------- prefix fallback: !dblast ----------
@bot.command(name="dblast")
async def dblast_prefix(ctx: commands.Context):
    text = await build_dblast_text()
    await ctx.send(text)

# ---------- notify HTTP server ----------
_web_started      = False
_startup_notified = False

async def handle_notify(request: web.Request):
    if request.headers.get("X-Notify-Secret") != NOTIFY_SECRET:
        return web.json_response({"error": "unauthorized"}, status=401)
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid json"}, status=400)
    message = data.get("message")
    if not isinstance(message, str) or not message.strip():
        return web.json_response({"error": "message must be a non-empty string"}, status=400)
    channel = bot.get_channel(CHANNEL_ID)
    if channel is None:
        return web.json_response({"error": "channel not found in cache yet"}, status=503)
    try:
        await channel.send(message)
    except Exception as e:
        return web.json_response({"error": f"discord send failed: {e}"}, status=500)
    return web.json_response({"status": "sent"})

async def handle_health(request: web.Request):
    return web.json_response({"status": "ok", "bot": str(bot.user)})

async def run_web_server():
    app = web.Application()
    app.router.add_post("/notify", handle_notify)
    app.router.add_get("/health",  handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, NOTIFY_HOST, NOTIFY_PORT)
    await site.start()
    print(f"[notify] listening on http://{NOTIFY_HOST}:{NOTIFY_PORT}/notify")

# ---------- events & tasks ----------
@bot.event
async def on_ready():
    global _web_started, _startup_notified
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")

    if not _web_started:
        bot.loop.create_task(run_web_server())
        _web_started = True

    # Sync slash commands to the guild that owns the target channel — instant
    # (global sync can take up to 1 hour to propagate).
    try:
        ch = bot.get_channel(CHANNEL_ID)
        if ch is not None and ch.guild is not None:
            guild_obj = discord.Object(id=ch.guild.id)
            bot.tree.copy_global_to(guild=guild_obj)
            synced = await bot.tree.sync(guild=guild_obj)
            print(f"[commands] synced {len(synced)} command(s) to guild {ch.guild.id}")
        else:
            synced = await bot.tree.sync()
            print(f"[commands] synced {len(synced)} command(s) globally")
    except Exception as e:
        print(f"[commands] sync failed: {e}")

    # Send startup message once per process (not on every Discord reconnect).
    if not _startup_notified:
        ch = bot.get_channel(CHANNEL_ID)
        if ch is not None:
            try:
                await ch.send(
                    f"Monitoring Starts — "
                    f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} HKT"
                )
                _startup_notified = True
            except Exception as e:
                print(f"[startup] could not send startup message: {e}")
        else:
            print(f"[startup] channel {CHANNEL_ID} not in cache yet — skipping startup message")

    if not record_metrics.is_running():
        record_metrics.start()
    if not heartbeat.is_running():
        heartbeat.start()
    if not twelve_hour_report.is_running():
        twelve_hour_report.start()


@tasks.loop(minutes=10)
async def record_metrics():
    tracker.record()


# dtime(h, m) is UTC. dtime(16,0) = 00:00 HKT, dtime(4,0) = 12:00 HKT.
@tasks.loop(time=[dtime(16, 0), dtime(4, 0)])
async def heartbeat():
    ch = bot.get_channel(CHANNEL_ID)
    if ch:
        await ch.send(f"Bot alive — {datetime.now().strftime('%Y-%m-%d %H:%M')}")


@tasks.loop(time=[dtime(16, 0), dtime(4, 0)])
async def twelve_hour_report():
    ch = bot.get_channel(CHANNEL_ID)
    if ch is None:
        print(f"channel {CHANNEL_ID} not found")
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg  = f"System Health — {now}\n\n"
    msg += tracker.summary() + "\n"
    msg += "Disk usage:\n"
    for mount, d in get_disk_info().items():
        msg += f"  - {mount}: {d['used']} / {d['total']} GB ({d['percent']}%)\n"

    await ch.send(msg)
    tracker.reset()


if __name__ == "__main__":
    bot.run(TOKEN)
