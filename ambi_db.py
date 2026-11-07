"""
Ambi Climate 2 - SQLite Storage & Analytics Database Module
===========================================================
Handles persistent storage for:
1. Real-time Sensor Telemetry (Temperature, Humidity, Humidex, Comfort Score, Light)
2. AC Actions & Control Events (AI Auto-tuning, Manual Controls, Feedback, Power Sync)
3. Historical Metric Aggregation & Timeline Extraction for the Dashboard UI
"""

import os
import time
import sqlite3
import datetime
import threading

def init_timezone():
    """Detects and applies the host OS timezone to the Python runtime."""
    tz = os.environ.get("TZ")
    if not tz:
        if os.path.exists("/etc/timezone"):
            try:
                with open("/etc/timezone", "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        tz = content
            except Exception:
                pass
        if not tz and os.path.exists("/etc/localtime"):
            try:
                real = os.path.realpath("/etc/localtime")
                if "zoneinfo/" in real:
                    tz = real.split("zoneinfo/")[-1]
            except Exception:
                pass
    if tz:
        os.environ["TZ"] = tz
    if hasattr(time, "tzset"):
        try:
            time.tzset()
        except Exception:
            pass
    return tz or time.tzname[0]

CURRENT_TIMEZONE = init_timezone()

DIR = os.path.dirname(os.path.abspath(__file__))

def get_db_path(custom_path=None):
    """
    Resolves the actual SQLite database file path.
    Handles environment variables (DATABASE_PATH), directory mounts,
    and automatically creates parent directories if needed.
    """
    target = custom_path or os.environ.get("DATABASE_PATH") or os.path.join(DIR, "ambi_data.db")
    # If target is an existing directory (e.g. Docker mounted a directory to this path),
    # place the db inside that directory
    if os.path.isdir(target):
        return os.path.join(target, "ambi_data.db")
    parent = os.path.dirname(os.path.abspath(target))
    if parent and not os.path.exists(parent):
        try:
            os.makedirs(parent, exist_ok=True)
        except Exception:
            pass
    return target

DB_FILE = get_db_path()

_DB_LOCK = threading.Lock()
_LAST_SENSOR_LOG_TIME = 0
_LAST_SENSOR_VALUES = (None, None)

def get_connection(db_path=None):
    """Creates a connection to SQLite with WAL mode for safe multi-thread reads/writes."""
    path = get_db_path(db_path)
    conn = sqlite3.connect(path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def init_db(db_path=None):
    """Initializes the database schema and indexes."""
    path = get_db_path(db_path)
    with _DB_LOCK:
        conn = get_connection(path)
        try:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS sensor_telemetry (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL NOT NULL,
                        datetime_str TEXT NOT NULL,
                        temperature REAL NOT NULL,
                        humidity REAL NOT NULL,
                        luminosity INTEGER DEFAULT 0,
                        humidex REAL,
                        comfort_score REAL,
                        comfort_label TEXT,
                        source TEXT DEFAULT 'poll'
                    );
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_sensor_ts ON sensor_telemetry(timestamp);")

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS ac_actions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL NOT NULL,
                        datetime_str TEXT NOT NULL,
                        action_type TEXT NOT NULL,
                        power TEXT NOT NULL,
                        temperature REAL,
                        fan TEXT,
                        swing TEXT,
                        mode TEXT,
                        trigger_reason TEXT,
                        room_temp REAL,
                        room_humidity REAL,
                        humidex REAL,
                        result TEXT,
                        details TEXT
                    );
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_actions_ts ON ac_actions(timestamp);")

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS comfort_profile (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        auto_tune_enabled INTEGER DEFAULT 1,
                        target_base_humidex REAL DEFAULT 26.0,
                        user_offset REAL DEFAULT 0.0,
                        temp_calibration_offset REAL DEFAULT -3.0,
                        humidity_calibration_offset REAL DEFAULT 4.0,
                        min_temp INTEGER DEFAULT 22,
                        max_temp INTEGER DEFAULT 27,
                        cooldown_minutes INTEGER DEFAULT 10,
                        last_tune_time REAL DEFAULT 0,
                        last_tune_action TEXT DEFAULT '',
                        updated_at REAL NOT NULL
                    );
                """)

                try:
                    conn.execute("ALTER TABLE comfort_profile ADD COLUMN temp_calibration_offset REAL DEFAULT -3.0;")
                except Exception:
                    pass
                try:
                    conn.execute("ALTER TABLE comfort_profile ADD COLUMN humidity_calibration_offset REAL DEFAULT 4.0;")
                except Exception:
                    pass

                # Update existing profile record if offsets are at old default 0.0 or NULL
                conn.execute("""
                    UPDATE comfort_profile 
                    SET temp_calibration_offset = -3.0, 
                        humidity_calibration_offset = 4.0 
                    WHERE id = 1 AND (temp_calibration_offset = 0.0 OR temp_calibration_offset IS NULL);
                """)

                # Auto-migrate any past misclassified AI actions
                conn.execute("""
                    UPDATE ac_actions 
                    SET action_type = 'ai_tune' 
                    WHERE action_type = 'manual_control' 
                      AND (
                        trigger_reason LIKE '%Auto-Tune%' 
                        OR trigger_reason LIKE '%AI%' 
                        OR trigger_reason LIKE '%หนาวไป%' 
                        OR trigger_reason LIKE '%ร้อนไป%'
                        OR trigger_reason LIKE '%Warmed%'
                        OR trigger_reason LIKE '%Cooled%'
                      );
                """)
        finally:
            conn.close()
    seed_initial_data_if_empty(path)

def seed_initial_data_if_empty(db_path=None):
    """Backfills past actions from user_comfort_profile.json and seeds baseline 4-hour curve if empty."""
    import json
    import math
    path = get_db_path(db_path)
    with _DB_LOCK:
        conn = get_connection(path)
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM ac_actions")
            action_count = cur.fetchone()[0]

            profile_file = os.path.join(DIR, "user_comfort_profile.json")
            if action_count == 0 and os.path.exists(profile_file):
                try:
                    with open(profile_file, "r", encoding="utf-8") as f:
                        prof = json.load(f)
                    hist = prof.get("history", [])
                    now = time.time()
                    for idx, h in enumerate(reversed(hist)):
                        ts = now - (len(hist) - idx) * 180
                        dt_str = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
                        action = h.get("action", "")
                        atype = "manual_control"
                        if "Feedback" in action:
                            atype = "user_feedback"
                        elif "Mode" in action:
                            atype = "mode_change"
                        elif "AI" in action or "Auto" in action:
                            atype = "ai_tune"
                        elif "Power" in action:
                            atype = "power"

                        cur.execute("""
                            INSERT INTO ac_actions 
                            (timestamp, datetime_str, action_type, power, temperature, fan, swing, mode, trigger_reason, room_temp, room_humidity, humidex, result, details)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (ts, dt_str, atype, h.get("power", "On"), h.get("temp", 24), h.get("fan", "Auto"), "Auto", "Cool",
                              action, h.get("room_temp"), h.get("room_humidity"), None, h.get("result", ""), ""))
                    conn.commit()
                except Exception as e:
                    print(f"[-] Backfill actions error: {e}")

            cur.execute("SELECT COUNT(*) FROM sensor_telemetry")
            sensor_count = cur.fetchone()[0]
            if sensor_count == 0:
                now = time.time()
                for i in range(120, -1, -1):
                    ts = now - (i * 120)
                    dt_str = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
                    t = round(26.6 + 0.45 * math.sin(i * 0.08) - 0.2 * math.cos(i * 0.03), 2)
                    h = round(60.5 + 2.8 * math.cos(i * 0.07) + 1.2 * math.sin(i * 0.04), 2)
                    v = 6.112 * (10 ** ((7.5 * t) / (237.7 + t))) * (h / 100.0)
                    hx = round(t + (5.0 / 9.0) * (v - 10.0), 2)
                    cur.execute("""
                        INSERT INTO sensor_telemetry 
                        (timestamp, datetime_str, temperature, humidity, luminosity, humidex, comfort_score, comfort_label, source)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (ts, dt_str, t, h, 85, hx, 0.2, "comfortable", "seed"))
                conn.commit()

            # Migrate or seed comfort_profile
            cur.execute("SELECT COUNT(*) FROM comfort_profile WHERE id = 1")
            prof_count = cur.fetchone()[0]
            if prof_count == 0:
                prof_data = {}
                if os.path.exists(profile_file):
                    try:
                        with open(profile_file, "r", encoding="utf-8") as f:
                            prof_data = json.load(f)
                    except Exception as e:
                        print(f"[-] Load comfort profile error during seed: {e}")
                now = time.time()
                cur.execute("""
                    INSERT INTO comfort_profile
                    (id, auto_tune_enabled, target_base_humidex, user_offset, temp_calibration_offset, humidity_calibration_offset, min_temp, max_temp, cooldown_minutes, last_tune_time, last_tune_action, updated_at)
                    VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    1 if prof_data.get("auto_tune_enabled", True) else 0,
                    float(prof_data.get("target_base_humidex", 26.0)),
                    float(prof_data.get("user_offset", 1.7 if prof_data else 0.0)),
                    float(prof_data.get("temp_calibration_offset", -3.0)),
                    float(prof_data.get("humidity_calibration_offset", 4.0)),
                    int(prof_data.get("min_temp", 22)),
                    int(prof_data.get("max_temp", 27)),
                    int(prof_data.get("cooldown_minutes", 10)),
                    float(prof_data.get("last_tune_time", 0)),
                    str(prof_data.get("last_tune_action", "")),
                    now
                ))
                conn.commit()
        finally:
            conn.close()

def load_comfort_profile(db_path=None):
    """Loads the active comfort profile from SQLite database."""
    path = get_db_path(db_path)
    with _DB_LOCK:
        conn = get_connection(path)
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT auto_tune_enabled, target_base_humidex, user_offset,
                       min_temp, max_temp, cooldown_minutes, last_tune_time, last_tune_action,
                       temp_calibration_offset, humidity_calibration_offset
                FROM comfort_profile
                WHERE id = 1
            """)
            r = cur.fetchone()
            if r:
                t_cal = -3.0
                h_cal = 4.0
                try:
                    if "temp_calibration_offset" in r.keys() and r["temp_calibration_offset"] is not None:
                        t_cal = float(r["temp_calibration_offset"])
                except Exception:
                    pass
                try:
                    if "humidity_calibration_offset" in r.keys() and r["humidity_calibration_offset"] is not None:
                        h_cal = float(r["humidity_calibration_offset"])
                except Exception:
                    pass
                return {
                    "auto_tune_enabled": bool(r["auto_tune_enabled"]),
                    "target_base_humidex": float(r["target_base_humidex"]),
                    "user_offset": float(r["user_offset"]),
                    "temp_calibration_offset": t_cal,
                    "humidity_calibration_offset": h_cal,
                    "min_temp": int(r["min_temp"]),
                    "max_temp": int(r["max_temp"]),
                    "cooldown_minutes": int(r["cooldown_minutes"]),
                    "last_tune_time": float(r["last_tune_time"]),
                    "last_tune_action": str(r["last_tune_action"] or "")
                }
        finally:
            conn.close()

    return {
        "auto_tune_enabled": True,
        "target_base_humidex": 26.0,
        "user_offset": 0.0,
        "temp_calibration_offset": -3.0,
        "humidity_calibration_offset": 4.0,
        "min_temp": 22,
        "max_temp": 27,
        "cooldown_minutes": 10,
        "last_tune_time": 0,
        "last_tune_action": ""
    }

def save_comfort_profile(profile, db_path=None):
    """Saves comfort profile updates to SQLite database."""
    path = get_db_path(db_path)
    now = time.time()
    with _DB_LOCK:
        conn = get_connection(path)
        try:
            with conn:
                conn.execute("""
                    INSERT INTO comfort_profile 
                    (id, auto_tune_enabled, target_base_humidex, user_offset, temp_calibration_offset, humidity_calibration_offset, min_temp, max_temp, cooldown_minutes, last_tune_time, last_tune_action, updated_at)
                    VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        auto_tune_enabled = excluded.auto_tune_enabled,
                        target_base_humidex = excluded.target_base_humidex,
                        user_offset = excluded.user_offset,
                        temp_calibration_offset = excluded.temp_calibration_offset,
                        humidity_calibration_offset = excluded.humidity_calibration_offset,
                        min_temp = excluded.min_temp,
                        max_temp = excluded.max_temp,
                        cooldown_minutes = excluded.cooldown_minutes,
                        last_tune_time = excluded.last_tune_time,
                        last_tune_action = excluded.last_tune_action,
                        updated_at = excluded.updated_at
                """, (
                    1 if profile.get("auto_tune_enabled", True) else 0,
                    float(profile.get("target_base_humidex", 26.0)),
                    float(profile.get("user_offset", 0.0)),
                    float(profile.get("temp_calibration_offset", -3.0)),
                    float(profile.get("humidity_calibration_offset", 4.0)),
                    int(profile.get("min_temp", 22)),
                    int(profile.get("max_temp", 27)),
                    int(profile.get("cooldown_minutes", 10)),
                    float(profile.get("last_tune_time", 0)),
                    str(profile.get("last_tune_action", "")),
                    now
                ))
            return True
        except Exception as e:
            print(f"[-] DB save_comfort_profile error: {e}")
            return False
        finally:
            conn.close()

def parse_luminosity(val):
    """Safely parses luminosity value which can be int, float, or raw string like '0 94 67'."""
    if val is None:
        return 0
    if isinstance(val, (int, float)):
        return int(val)
    if isinstance(val, str):
        val = val.strip()
        if not val:
            return 0
        parts = val.split()
        int_vals = []
        for p in parts:
            try:
                int_vals.append(int(float(p)))
            except Exception:
                pass
        if int_vals:
            return max(int_vals)
    return 0

def record_sensor(temperature, humidity, luminosity=0, humidex=None, comfort_score=None, comfort_label=None, source="poll", db_path=None):
    """
    Records a live sensor reading into the database.
    Throttles identical rapid reads within 8 seconds.
    """
    global _LAST_SENSOR_LOG_TIME, _LAST_SENSOR_VALUES
    if temperature is None or humidity is None:
        return False

    now = time.time()
    # Throttle identical reads if within 8 seconds
    if (now - _LAST_SENSOR_LOG_TIME < 8.0) and (_LAST_SENSOR_VALUES == (round(temperature, 2), round(humidity, 2))):
        return False

    _LAST_SENSOR_LOG_TIME = now
    _LAST_SENSOR_VALUES = (round(temperature, 2), round(humidity, 2))
    dt_str = datetime.datetime.fromtimestamp(now).strftime('%Y-%m-%d %H:%M:%S')

    path = get_db_path(db_path)
    with _DB_LOCK:
        conn = get_connection(path)
        try:
            with conn:
                conn.execute("""
                    INSERT INTO sensor_telemetry 
                    (timestamp, datetime_str, temperature, humidity, luminosity, humidex, comfort_score, comfort_label, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (now, dt_str, round(temperature, 2), round(humidity, 2), parse_luminosity(luminosity),
                      round(humidex, 2) if humidex is not None else None,
                      round(comfort_score, 2) if comfort_score is not None else None,
                      comfort_label, source))
            return True
        except Exception as e:
            print(f"[-] DB record_sensor error: {e}")
            return False
        finally:
            conn.close()

def record_action(action_type, power, temperature=None, fan=None, swing=None, mode=None,
                  trigger_reason="", room_temp=None, room_humidity=None, humidex=None,
                  result="", details="", db_path=None):
    """Records an AC control action into the database."""
    now = time.time()
    dt_str = datetime.datetime.fromtimestamp(now).strftime('%Y-%m-%d %H:%M:%S')
    path = get_db_path(db_path)

    with _DB_LOCK:
        conn = get_connection(path)
        try:
            with conn:
                conn.execute("""
                    INSERT INTO ac_actions 
                    (timestamp, datetime_str, action_type, power, temperature, fan, swing, mode, trigger_reason, room_temp, room_humidity, humidex, result, details)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (now, dt_str, action_type, power, temperature, fan, swing, mode,
                      trigger_reason,
                      round(room_temp, 2) if room_temp is not None else None,
                      round(room_humidity, 2) if room_humidity is not None else None,
                      round(humidex, 2) if humidex is not None else None,
                      result, details))
            return True
        except Exception as e:
            print(f"[-] DB record_action error: {e}")
            return False
        finally:
            conn.close()

def get_sensor_metrics(hours=4, max_points=120, db_path=None):
    """
    Retrieves sensor metrics for the given hours range.
    Automatically downsamples evenly if points exceed max_points.
    Returns points and min/max/average statistics.
    """
    now = time.time()
    start_ts = now - (hours * 3600)
    path = get_db_path(db_path)

    with _DB_LOCK:
        conn = get_connection(path)
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT timestamp, datetime_str, temperature, humidity, humidex, comfort_label
                FROM sensor_telemetry
                WHERE timestamp >= ?
                ORDER BY timestamp ASC
            """, (start_ts,))
            rows = cur.fetchall()
        finally:
            conn.close()

    if not rows:
        return {
            "range_hours": hours,
            "count": 0,
            "start_timestamp": start_ts,
            "end_timestamp": now,
            "points": [],
            "stats": {
                "min_temp": None, "max_temp": None, "avg_temp": None,
                "min_hum": None, "max_hum": None, "avg_hum": None,
                "latest_temp": None, "latest_hum": None, "latest_humidex": None
            }
        }

    total_count = len(rows)
    # Downsample if needed
    if total_count > max_points:
        step = total_count / max_points
        sampled_rows = [rows[int(i * step)] for i in range(max_points)]
        # Always ensure the latest point is included
        if sampled_rows[-1]["timestamp"] != rows[-1]["timestamp"]:
            sampled_rows[-1] = rows[-1]
    else:
        sampled_rows = rows

    points = []
    temps = []
    hums = []

    for r in sampled_rows:
        t = r["temperature"]
        h = r["humidity"]
        temps.append(t)
        hums.append(h)
        dt = datetime.datetime.fromtimestamp(r["timestamp"])
        points.append({
            "timestamp": r["timestamp"],
            "time_str": dt.strftime('%H:%M'),
            "datetime_str": r["datetime_str"],
            "temperature": t,
            "humidity": h,
            "humidex": r["humidex"] or t,
            "comfort_label": r["comfort_label"] or "comfortable"
        })

    all_temps = [r["temperature"] for r in rows]
    all_hums = [r["humidity"] for r in rows]

    stats = {
        "min_temp": round(min(all_temps), 1),
        "max_temp": round(max(all_temps), 1),
        "avg_temp": round(sum(all_temps) / len(all_temps), 1),
        "min_hum": round(min(all_hums), 1),
        "max_hum": round(max(all_hums), 1),
        "avg_hum": round(sum(all_hums) / len(all_hums), 1),
        "latest_temp": rows[-1]["temperature"],
        "latest_hum": rows[-1]["humidity"],
        "latest_humidex": rows[-1]["humidex"]
    }

    return {
        "range_hours": hours,
        "count": total_count,
        "start_timestamp": start_ts,
        "end_timestamp": now,
        "points": points,
        "stats": stats
    }

def format_relative_time_th(ts):
    """Formats timestamp into relative Thai time description."""
    now = time.time()
    diff = int(now - ts)
    if diff < 60:
        return "เมื่อสักครู่"
    elif diff < 3600:
        mins = diff // 60
        return f"เมื่อ {mins} นาทีที่แล้ว"
    elif diff < 86400:
        hrs = diff // 3600
        return f"เมื่อ {hrs} ชั่วโมงที่แล้ว"
    else:
        days = diff // 86400
        return f"เมื่อ {days} วันที่แล้ว"

def get_timeline(limit=50, db_path=None):
    """
    Retrieves recent AC actions formatted as timeline items matching Ambi Climate app style.
    """
    path = get_db_path(db_path)
    with _DB_LOCK:
        conn = get_connection(path)
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, timestamp, datetime_str, action_type, power, temperature,
                       fan, swing, mode, trigger_reason, room_temp, room_humidity, humidex, result, details
                FROM ac_actions
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
            rows = cur.fetchall()
        finally:
            conn.close()

    events = []
    today_date = datetime.date.today().strftime('%Y-%m-%d')
    yesterday_date = (datetime.date.today() - datetime.timedelta(days=1)).strftime('%Y-%m-%d')

    for r in rows:
        dt = datetime.datetime.fromtimestamp(r["timestamp"])
        d_str = dt.strftime('%Y-%m-%d')
        if d_str == today_date:
            date_group = "วันนี้ (Today)"
        elif d_str == yesterday_date:
            date_group = "เมื่อวานนี้ (Yesterday)"
        else:
            date_group = dt.strftime('%d/%m/%Y')

        # Determine icon, badge style, title based on action_type
        atype = r["action_type"]
        power = r["power"]
        temp = r["temperature"]
        fan = r["fan"]
        reason = r["trigger_reason"] or ""

        # Auto fallback: if trigger_reason mentions auto-tune/ai, classify as ai_tune
        reason_l = reason.lower()
        if atype == 'manual_control' and any(k in reason_l for k in ("auto-tune", "auto-tuning", "ai", "หนาวไป", "ร้อนไป", "warmed", "cooled")):
            atype = 'ai_tune'

        is_ai = (atype == 'ai_tune')

        if is_ai:
            icon = "🤖"
            badge = "AI Adjust"
            color = "#00c4b4"  # Ambi Teal
            title = f"AI ปรับจูนอัตโนมัติ: {temp}°C • พัดลม {fan}"
        elif atype == 'thermal_sync':
            icon = "🔄"
            badge = "Smart State Sync"
            color = "#38bdf8"
            title = f"ซิงค์สถานะ: แอร์เปิดอยู่จริง ({temp}°C)"
        elif atype == 'user_feedback':
            icon = "😊"
            badge = "Feedback"
            color = "#f59e0b"
            title = f"สอน AI: {reason}"
        elif atype == 'mode_change':
            icon = "⚡"
            badge = "Mode Change"
            color = "#a855f7"
            title = f"เปลี่ยนโหมด: {reason}"
        elif atype == 'power':
            icon = "🔌"
            badge = "Power"
            color = "#ef4444" if power == 'Off' else "#10b981"
            title = f"สั่งแอร์: {'เปิดแอร์' if power == 'On' else 'ปิดแอร์'}"
        else:
            icon = "📱"
            badge = "Manual Remote"
            color = "#60a5fa"
            title = f"สั่งรีโมท: {temp}°C • {fan}"

        events.append({
            "id": r["id"],
            "timestamp": r["timestamp"],
            "date_group": date_group,
            "time_str": dt.strftime('%H:%M:%S'),
            "relative_time": format_relative_time_th(r["timestamp"]),
            "action_type": atype,
            "icon": icon,
            "badge": badge,
            "color": color,
            "title": title,
            "power": power,
            "temperature": temp,
            "fan": fan,
            "swing": r["swing"],
            "mode": r["mode"],
            "trigger_reason": reason,
            "room_temp": r["room_temp"],
            "room_humidity": r["room_humidity"],
            "humidex": r["humidex"],
            "result": r["result"],
            "is_ai": is_ai
        })

    return events

def check_thermal_drop(window_minutes=10, min_drop_c=0.35, db_path=None):
    """
    Analyzes recent temperature telemetry to see if temperature dropped significantly
    indicating that the AC was physically powered on by an external remote.
    Returns (detected: bool, start_temp, latest_temp, drop_amount).
    """
    now = time.time()
    start_ts = now - (window_minutes * 60)
    path = get_db_path(db_path)

    with _DB_LOCK:
        conn = get_connection(path)
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT temperature, timestamp
                FROM sensor_telemetry
                WHERE timestamp >= ?
                ORDER BY timestamp ASC
            """, (start_ts,))
            rows = cur.fetchall()
        finally:
            conn.close()

    if len(rows) < 6:  # Need at least 2 minutes of polling data (every 20s = 6 points)
        return False, None, None, 0.0

    temps = [r["temperature"] for r in rows]
    # Check drop from the maximum in the earlier half to the latest
    half = len(temps) // 2
    initial_peak = max(temps[:half])
    latest = temps[-1]
    drop = initial_peak - latest

    if drop >= min_drop_c:
        return True, initial_peak, latest, round(drop, 2)
    return False, initial_peak, latest, round(drop, 2)

def check_thermal_rise(window_minutes=15, min_rise_c=0.8, min_temp_threshold=27.0, db_path=None):
    """
    Analyzes recent temperature telemetry to see if temperature rose steadily while AC was supposed to be ON,
    indicating that the AC was physically powered OFF by an external remote.
    Returns (detected: bool, start_temp, latest_temp, rise_amount).
    """
    now = time.time()
    start_ts = now - (window_minutes * 60)
    path = get_db_path(db_path)

    with _DB_LOCK:
        conn = get_connection(path)
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT temperature, timestamp
                FROM sensor_telemetry
                WHERE timestamp >= ?
                ORDER BY timestamp ASC
            """, (start_ts,))
            rows = cur.fetchall()
        finally:
            conn.close()

    if len(rows) < 8:  # Need at least ~3-4 minutes of polling data
        return False, None, None, 0.0

    temps = [r["temperature"] for r in rows]
    half = len(temps) // 2
    initial_low = min(temps[:half])
    latest = temps[-1]
    rise = latest - initial_low

    if rise >= min_rise_c and latest >= min_temp_threshold:
        return True, initial_low, latest, round(rise, 2)
    return False, initial_low, latest, round(rise, 2)

# Self-initialize on module load
init_db()
