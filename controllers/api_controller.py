#!/usr/bin/env python3
"""
Ambi Climate Web & REST API Controller
--------------------------------------
Implements HTTP/HTTPS request handling for Web Dashboard, REST APIs, and Apple HomeKit (Homebridge).
"""

import json
import time
import socket
from urllib.parse import urlparse, parse_qs
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import ambi_db

from models.config import (
    DASHBOARD_PORT, HOST_IP, ROUTER_GATEWAY_IP, ROUTER_WAN_IP,
    DNS_REDIRECT_IP, hub_log, refresh_network_settings
)
import models.ac_state as ac_mod
from models.ac_state import (
    AC_STATE, REAL_DEVICE_ID, DEVICE_UUID, MAC_ADDRESS,
    DEVICE, APPLIANCE, IRP_ID, get_ambi_ip, get_pending_ir_status
)
from models.comfort import (
    COMFORT_PROFILE, save_comfort_profile, evaluate_comfort, calculate_humidex
)
from controllers.hardware_controller import (
    send_daikin_ir, send_ambi_cmd, get_cloud_server_setting,
    change_cloud_server, fetch_ambi_system_log, set_ambi_led_green,
    set_ambi_led_brightness, query_live_sensors
)
from views.dashboard_view import get_dashboard_html

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class AmbiAPIHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        msg = format % args
        if "Bad request version" in msg or "code 400" in msg:
            return
        hub_log(f"[HTTP/S :{self.server.server_port}] {self.address_string()} - {msg}")

    def log_error(self, format, *args):
        msg = format % args
        if "Bad request version" in msg or "code 400" in msg:
            return
        hub_log(f"[-] HTTP Error :{self.server.server_port} - {msg}")

    def handle_one_request(self):
        try:
            peek = self.connection.recv(1, socket.MSG_PEEK)
            if peek and peek[0] == 0x16:
                self.close_connection = True
                return
        except Exception:
            pass
        super().handle_one_request()

    def do_GET(self):
        AC_STATE["last_seen"] = time.strftime('%H:%M:%S')
        hub_log(f"[GET :{self.server.server_port}] from {self.client_address[0]} Path: {self.path}")

        if (self.server.server_port in (DASHBOARD_PORT, 9090)) and (self.path == '/' or self.path.startswith('/api') or self.path.startswith('/status') or self.path.startswith('/target')):
            self.handle_web_ui()
            return
 
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Connection', 'keep-alive')
        self.end_headers()

        response = {
            "status": "OK",
            "data": {
                "device_id": REAL_DEVICE_ID,
                "uuid": DEVICE_UUID,
                "mac": MAC_ADDRESS,
                "online": True,
                "room_name": DEVICE["ZROOM_NAME"],
                "appliance": {
                    "id": APPLIANCE["ZID"],
                    "manufacturer": APPLIANCE["ZMANUFACTURER"],
                    "irp_id": IRP_ID,
                    "type": APPLIANCE["ZTYPE"],
                    "state": AC_STATE
                }
            }
        }
        self.wfile.write(json.dumps(response).encode('utf-8'))

    def do_POST(self):
        AC_STATE["last_seen"] = time.strftime('%H:%M:%S')
        if (self.server.server_port in (DASHBOARD_PORT, 9090)) and (self.path.startswith('/api') or self.path.startswith('/status') or self.path.startswith('/target')):
            self.handle_web_ui()
            return
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode('utf-8', errors='ignore') if length > 0 else ""
        hub_log(f"[POST :{self.server.server_port}] from {self.client_address[0]} Path: {self.path} Body: {body}")

        try:
            if body:
                data = json.loads(body)
                updated = False
                t_calib = float(COMFORT_PROFILE.get("temp_calibration_offset", -3.0))
                h_calib = float(COMFORT_PROFILE.get("humidity_calibration_offset", 4.0))
                if "temperature" in data:
                    raw_t = float(data["temperature"])
                    AC_STATE["room_temp_raw"] = raw_t
                    AC_STATE["room_temp"] = round(raw_t + t_calib, 2)
                    updated = True
                if "humidity" in data:
                    raw_h = float(data["humidity"])
                    AC_STATE["room_humidity_raw"] = raw_h
                    AC_STATE["room_humidity"] = round(min(100.0, max(0.0, raw_h + h_calib)), 2)
                    updated = True
                if updated:
                    AC_STATE["sensor_status"] = f"PUSH (HTTP POST :{self.server.server_port})"
                    AC_STATE["sensor_time"] = time.strftime('%H:%M:%S')
                    c = evaluate_comfort(AC_STATE.get("room_temp", 25.0), AC_STATE.get("room_humidity", 50.0))
                    AC_STATE["humidex"] = c["humidex"]
                    AC_STATE["comfort_score"] = c["score"]
                    AC_STATE["comfort_label"] = c["label"]
                    AC_STATE["comfort_badge_color"] = c["badge_color"]
                    hub_log(f"[PUSH SENSOR HTTP] 📥 Temp: {AC_STATE['room_temp']}°C | Hum: {AC_STATE['room_humidity']}% | Humidex: {c['humidex']}°C")
                    ambi_db.record_sensor(
                        temperature=AC_STATE["room_temp"],
                        humidity=AC_STATE["room_humidity"],
                        luminosity=AC_STATE.get("luminosity", 0),
                        humidex=c.get("humidex"),
                        comfort_score=c.get("score"),
                        comfort_label=c.get("label"),
                        source="push"
                    )
        except Exception:
            pass

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Connection', 'keep-alive')
        self.end_headers()

        response = {"status": "OK", "message": "Success"}
        self.wfile.write(json.dumps(response).encode('utf-8'))

    def do_PUT(self):
        self.do_POST()

    def handle_web_ui(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        # 0. Homebridge Apple HomeKit Integration Endpoints
        if path in ('/api/homebridge/status', '/status'):
            is_off = str(AC_STATE.get("power", "off")).lower() == 'off'
            mode = str(AC_STATE.get("mode", "cool")).lower()

            if is_off:
                hk_state = 0
            elif mode == 'heat':
                hk_state = 1
            elif mode == 'auto':
                hk_state = 3
            else:
                hk_state = 2  # Cool is default for AC

            current_t = AC_STATE.get("room_temp")
            current_t = float(current_t) if current_t is not None else float(AC_STATE.get("temperature", 25.0))

            current_rh = AC_STATE.get("room_humidity")
            current_rh = float(current_rh) if current_rh is not None else 50.0

            target_t = float(AC_STATE.get("temperature", 25.0))

            hb_payload = {
                "targetHeatingCoolingState": hk_state,
                "targetTemperature": target_t,
                "currentHeatingCoolingState": hk_state,
                "currentTemperature": round(current_t, 1),
                "currentRelativeHumidity": round(current_rh, 1)
            }
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(hb_payload).encode('utf-8'))
            return

        if path in ('/api/homebridge/targetHeatingCoolingState', '/targetHeatingCoolingState'):
            val = str(query.get('value', [''])[0]).strip()
            hub_log(f"[Homebridge] Set HeatingCoolingState: {val}")
            if val == '0':
                send_daikin_ir(power='off', reason='Homebridge Mode OFF')
            elif val == '1':
                send_daikin_ir(power='on', mode='heat', reason='Homebridge Mode HEAT')
            elif val == '2':
                send_daikin_ir(power='on', mode='cool', reason='Homebridge Mode COOL')
            elif val == '3':
                send_daikin_ir(power='on', mode='auto', reason='Homebridge Mode AUTO')

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "OK", "targetHeatingCoolingState": int(val) if val.isdigit() else 0, "ac_state": AC_STATE}).encode('utf-8'))
            return

        if path in ('/api/homebridge/targetTemperature', '/targetTemperature'):
            val = str(query.get('value', [''])[0]).strip()
            hub_log(f"[Homebridge] Set TargetTemperature: {val}")
            try:
                new_temp = int(round(float(val)))
                send_daikin_ir(temp=new_temp, power='on', reason=f'Homebridge Target Temp {new_temp}C')
            except Exception as e:
                hub_log(f"[Homebridge] Error parsing target temp '{val}': {e}")

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "OK", "targetTemperature": AC_STATE.get("temperature", 25), "ac_state": AC_STATE}).encode('utf-8'))
            return

        # 1. State API
        if path == '/api/state':
            room_t = AC_STATE.get("room_temp")
            room_rh = AC_STATE.get("room_humidity")
            comfort = evaluate_comfort(room_t, room_rh)

            now = time.time()
            cooldown_sec = COMFORT_PROFILE.get("cooldown_minutes", 10) * 60
            last_tune = COMFORT_PROFILE.get("last_tune_time", 0)
            remaining_cooldown = max(0, int(cooldown_sec - (now - last_tune)))

            data = {
                "status": "OK",
                "device_ip": get_ambi_ip(),
                "network": {
                    "host_ip": HOST_IP,
                    "gateway_ip": ROUTER_GATEWAY_IP,
                    "wan_ip": ROUTER_WAN_IP,
                    "dns_redirect_ip": DNS_REDIRECT_IP,
                    "ambi_ip": get_ambi_ip()
                },
                "ac_state": AC_STATE,
                "comfort": comfort,
                "profile": {
                    "auto_tune_enabled": COMFORT_PROFILE.get("auto_tune_enabled", True),
                    "target_base_humidex": COMFORT_PROFILE.get("target_base_humidex", 26.0),
                    "user_offset": COMFORT_PROFILE.get("user_offset", 0.0),
                    "temp_calibration_offset": float(COMFORT_PROFILE.get("temp_calibration_offset", -3.0)),
                    "humidity_calibration_offset": float(COMFORT_PROFILE.get("humidity_calibration_offset", 4.0)),
                    "min_temp": COMFORT_PROFILE.get("min_temp", 22),
                    "max_temp": COMFORT_PROFILE.get("max_temp", 27),
                    "cooldown_minutes": COMFORT_PROFILE.get("cooldown_minutes", 10),
                    "last_tune_action": COMFORT_PROFILE.get("last_tune_action", ""),
                    "history": COMFORT_PROFILE.get("history", [])[:10]
                },
                "cooldown_remaining_sec": remaining_cooldown,
                "pending_ir": get_pending_ir_status()
            }
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(data).encode('utf-8'))
            return

        # 2. Control API
        if path == '/api/control':
            t = query.get('temp', [None])[0]
            f = query.get('fan', [None])[0]
            p = query.get('power', [None])[0]
            m = query.get('mode', [None])[0]
            resp = send_daikin_ir(temp=t, fan=f, power=p, mode=m, reason="Web UI Manual Control")
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "OK", "ac_state": AC_STATE, "ir_result": resp}).encode('utf-8'))
            return

        # 3. Feedback API (User Teaching AI)
        if path == '/api/feedback':
            choice = query.get('choice', [''])[0].strip().lower()
            curr_offset = COMFORT_PROFILE.get("user_offset", 0.0)
            action_desc = ""

            if choice in ('cold', 'too_cold', 'freezing', 'หนาว', 'หนาวไป', 'เย็นไป'):
                new_offset = round(curr_offset + 0.5, 2)
                COMFORT_PROFILE["user_offset"] = new_offset
                curr_t = AC_STATE.get("temperature", 24)
                max_t = COMFORT_PROFILE.get("max_temp", 27)
                new_t = min(max_t, curr_t + 1)
                new_fan = "Low" if AC_STATE.get("fan") == "High" else AC_STATE.get("fan")
                action_desc = f"Feedback: หนาวไป -> ปรับ {new_t}°C (ชดเชย +{new_offset}°C)"
                send_daikin_ir(temp=new_t, fan=new_fan, reason=action_desc)
                COMFORT_PROFILE["last_tune_time"] = time.time()
                COMFORT_PROFILE["last_tune_action"] = action_desc
                save_comfort_profile(COMFORT_PROFILE)

            elif choice in ('warm', 'too_warm', 'hot', 'ร้อน', 'ร้อนไป'):
                new_offset = round(curr_offset - 0.5, 2)
                COMFORT_PROFILE["user_offset"] = new_offset
                curr_t = AC_STATE.get("temperature", 24)
                min_t = COMFORT_PROFILE.get("min_temp", 22)
                new_t = max(min_t, curr_t - 1)
                new_fan = "High" if AC_STATE.get("fan") in ("Quiet", "Low") else AC_STATE.get("fan")
                action_desc = f"Feedback: ร้อนไป -> ปรับ {new_t}°C (ชดเชย {new_offset}°C)"
                send_daikin_ir(temp=new_t, fan=new_fan, reason=action_desc)
                COMFORT_PROFILE["last_tune_time"] = time.time()
                COMFORT_PROFILE["last_tune_action"] = action_desc
                save_comfort_profile(COMFORT_PROFILE)

            elif choice in ('comfy', 'comfortable', 'สบาย', 'สบายดี'):
                room_t = AC_STATE.get("room_temp") or 25.0
                room_rh = AC_STATE.get("room_humidity") or 50.0
                curr_hx = calculate_humidex(room_t, room_rh) or 26.0
                base = COMFORT_PROFILE.get("target_base_humidex", 26.0)
                new_offset = round(curr_hx - base, 2)
                COMFORT_PROFILE["user_offset"] = new_offset
                action_desc = f"Feedback: บันทึกความสบายเป้าหมายที่ {curr_hx}°C (ชดเชย {new_offset}°C)"
                COMFORT_PROFILE["last_tune_time"] = time.time()
                COMFORT_PROFILE["last_tune_action"] = action_desc
                entry = {
                    "time": time.strftime('%H:%M:%S'),
                    "action": action_desc,
                    "temp": AC_STATE['temperature'],
                    "fan": AC_STATE['fan'],
                    "power": AC_STATE['power'],
                    "room_temp": room_t,
                    "room_humidity": room_rh,
                    "result": "Comfort Target Calibrated"
                }
                history = COMFORT_PROFILE.get("history", [])
                history.insert(0, entry)
                COMFORT_PROFILE["history"] = history[:25]
                save_comfort_profile(COMFORT_PROFILE)

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "OK",
                "choice": choice,
                "action": action_desc,
                "user_offset": COMFORT_PROFILE.get("user_offset", 0.0),
                "ac_state": AC_STATE
            }).encode('utf-8'))
            return

        # 4. AutoTune Toggle API
        if path == '/api/autotune':
            en_val = query.get('enable', [''])[0].lower()
            if en_val in ('1', 'true', 'on'):
                COMFORT_PROFILE["auto_tune_enabled"] = True
            elif en_val in ('0', 'false', 'off'):
                COMFORT_PROFILE["auto_tune_enabled"] = False
            save_comfort_profile(COMFORT_PROFILE)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "OK",
                "auto_tune_enabled": COMFORT_PROFILE["auto_tune_enabled"]
            }).encode('utf-8'))
            return

        # 4.05 Sensor Calibration API (Temperature & Humidity Offsets: default -3.0°C / +4%)
        if path in ('/api/settings/calibration', '/api/sensors/calibration'):
            t_off = query.get('temp_offset', [None])[0]
            h_off = query.get('humidity_offset', [None])[0]
            updated = False
            if t_off is not None:
                try:
                    val_t = round(float(t_off), 2)
                    COMFORT_PROFILE["temp_calibration_offset"] = val_t
                    AC_STATE["temp_calibration_offset"] = val_t
                    updated = True
                except ValueError:
                    pass
            if h_off is not None:
                try:
                    val_h = round(float(h_off), 2)
                    COMFORT_PROFILE["humidity_calibration_offset"] = val_h
                    AC_STATE["humidity_calibration_offset"] = val_h
                    updated = True
                except ValueError:
                    pass

            if updated:
                save_comfort_profile(COMFORT_PROFILE)
                raw_t = AC_STATE.get("room_temp_raw")
                if raw_t is not None:
                    AC_STATE["room_temp"] = round(raw_t + float(COMFORT_PROFILE.get("temp_calibration_offset", -3.0)), 2)
                raw_h = AC_STATE.get("room_humidity_raw")
                if raw_h is not None:
                    AC_STATE["room_humidity"] = round(min(100.0, max(0.0, raw_h + float(COMFORT_PROFILE.get("humidity_calibration_offset", 4.0)))), 2)
                if AC_STATE.get("room_temp") is not None and AC_STATE.get("room_humidity") is not None:
                    c = evaluate_comfort(AC_STATE["room_temp"], AC_STATE["room_humidity"])
                    AC_STATE["humidex"] = c["humidex"]
                    AC_STATE["comfort_score"] = c["score"]
                    AC_STATE["comfort_label"] = c["label"]
                    AC_STATE["comfort_badge_color"] = c["badge_color"]

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "OK",
                "temp_calibration_offset": float(COMFORT_PROFILE.get("temp_calibration_offset", -3.0)),
                "humidity_calibration_offset": float(COMFORT_PROFILE.get("humidity_calibration_offset", 4.0)),
                "room_temp": AC_STATE.get("room_temp"),
                "room_temp_raw": AC_STATE.get("room_temp_raw"),
                "room_humidity": AC_STATE.get("room_humidity"),
                "room_humidity_raw": AC_STATE.get("room_humidity_raw")
            }).encode('utf-8'))
            return

        # 4.1 Mode Selection API (Comfort, Temperature, Manual, Away, Off - Ambi User Guide)
        if path == '/api/mode':
            m = query.get('mode', ['Comfort'])[0]
            m_cap = m.capitalize()
            if m_cap not in ('Comfort', 'Temperature', 'Manual', 'Away', 'Off'):
                m_cap = 'Comfort'
            AC_STATE['ambi_mode'] = m_cap
            if m_cap == 'Off':
                AC_STATE['power'] = 'Off'
                send_daikin_ir(power='Off', reason="Mode Change: OFF")
            elif m_cap == 'Comfort':
                AC_STATE['power'] = 'On'
                COMFORT_PROFILE["auto_tune_enabled"] = True
                save_comfort_profile(COMFORT_PROFILE)
                send_daikin_ir(power='On', reason="Mode Change: Comfort Mode")
            elif m_cap == 'Temperature':
                AC_STATE['power'] = 'On'
                COMFORT_PROFILE["auto_tune_enabled"] = False
                save_comfort_profile(COMFORT_PROFILE)
                send_daikin_ir(power='On', reason="Mode Change: Temperature Mode")
            elif m_cap == 'Manual':
                AC_STATE['power'] = 'On'
                COMFORT_PROFILE["auto_tune_enabled"] = False
                save_comfort_profile(COMFORT_PROFILE)
                send_daikin_ir(power='On', reason="Mode Change: Manual Mode")
            elif m_cap == 'Away':
                AC_STATE['power'] = 'Off'
                send_daikin_ir(power='Off', reason="Mode Change: Away Mode")
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "OK", "ambi_mode": m_cap, "ac_state": AC_STATE}).encode('utf-8'))
            return

        # 5. Cloud Status API
        if path == '/api/cloud/status':
            curr = get_cloud_server_setting()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "OK", "device_ip": get_ambi_ip(), "cloud_server": curr}).encode('utf-8'))
            return

        # 6. Cloud Change API
        if path == '/api/cloud/change':
            srv = query.get('server', [f"{HOST_IP}:8867"])[0]
            res = change_cloud_server(srv)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(res).encode('utf-8'))
            return

        # 7. Cloud Reconnect API
        if path == '/api/cloud/reconnect':
            res = send_ambi_cmd("NCD")
            res_str = res.decode('latin1', errors='ignore').strip() if res else "None"
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "OK", "device_ip": get_ambi_ip(), "response": res_str}).encode('utf-8'))
            return

        # 8. Ambi System Dump Log API (NSL)
        if path == '/api/system_log':
            log_text = fetch_ambi_system_log()
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(log_text.encode('utf-8'))
            return

        # 9. Set LED Green API
        if path == '/api/led/green':
            ok = set_ambi_led_green()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "OK" if ok else "Error", "device_ip": get_ambi_ip()}).encode('utf-8'))
            return

        # 10. Manual Sensor Refresh / Query API (On-Demand)
        if path in ('/api/sensors/query', '/api/sensors/refresh'):
            res = query_live_sensors()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(res).encode('utf-8'))
            return

        # 10.1 Sensor Polling Status / Toggle API
        if path == '/api/sensors/polling':
            en = query.get('enable', [None])[0]
            if en is not None:
                ac_mod.POLL_SENSORS_ENABLED = str(en).lower() in ('1', 'true', 'on')
                hub_log(f"[*] Sensor Polling updated: enabled={ac_mod.POLL_SENSORS_ENABLED}")
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "OK",
                "polling_enabled": ac_mod.POLL_SENSORS_ENABLED,
                "interval_sec": 20,
                "sensor_status": AC_STATE.get("sensor_status"),
                "sensor_time": AC_STATE.get("sensor_time")
            }).encode('utf-8'))
            return

        # 10.2 Auto Network Refresh / Detect API
        if path == '/api/network/detect':
            refresh_network_settings()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "OK",
                "network": {
                    "host_ip": HOST_IP,
                    "gateway_ip": ROUTER_GATEWAY_IP,
                    "wan_ip": ROUTER_WAN_IP,
                    "dns_redirect_ip": DNS_REDIRECT_IP,
                    "ambi_ip": get_ambi_ip()
                }
            }).encode('utf-8'))
            return

        # 11. Set LED Brightness API (0 = OFF, 1-10000 = PWM brightness)
        if path == '/api/led/brightness':
            try:
                lvl = int(query.get('level', ['5700'])[0])
            except (ValueError, TypeError):
                lvl = 5700
            ok = set_ambi_led_brightness(lvl)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "OK" if ok else "Error", "level": lvl, "device_ip": get_ambi_ip()}).encode('utf-8'))
            return

        # 12. SQLite Metrics History API (For Graphs - 1h, 4h, 8h, 12h, 24h, 7d)
        if path == '/api/history/metrics':
            range_str = query.get('range', ['4h'])[0].lower()
            hours = 4
            if range_str.endswith('h'):
                try:
                    hours = int(range_str[:-1])
                except ValueError:
                    hours = 4
            elif range_str.endswith('d'):
                try:
                    hours = int(range_str[:-1]) * 24
                except ValueError:
                    hours = 168
            elif range_str == '24h':
                hours = 24
            elif range_str == '12h':
                hours = 12
            elif range_str == '8h':
                hours = 8
            elif range_str == '7d':
                hours = 168
            elif range_str == '1h':
                hours = 1
            metrics = ambi_db.get_sensor_metrics(hours=hours)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "OK", "data": metrics}).encode('utf-8'))
            return

        # 13. SQLite Activity Timeline API (Deployments / Actions History with range & limit)
        if path == '/api/history/timeline':
            try:
                limit = int(query.get('limit', ['100'])[0])
            except (ValueError, TypeError):
                limit = 100
            range_str = query.get('range', [''])[0].lower()
            hours = None
            if range_str:
                if range_str.endswith('h'):
                    try:
                        hours = int(range_str[:-1])
                    except ValueError:
                        hours = None
                elif range_str.endswith('d'):
                    try:
                        hours = int(range_str[:-1]) * 24
                    except ValueError:
                        hours = None
            events = ambi_db.get_timeline(limit=limit, hours=hours)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "OK", "events": events, "hours": hours}).encode('utf-8'))
            return

        # 14. Physical Remote State Sync API (Sync AC Power On/Off without blasting IR)
        if path == '/api/sync/state':
            target_power = query.get('power', ['On'])[0].capitalize()
            if target_power not in ('On', 'Off'):
                target_power = 'On'
            prev_power = AC_STATE.get('power')
            AC_STATE['power'] = target_power

            if target_power == 'On' and AC_STATE.get('ambi_mode') == 'Comfort':
                COMFORT_PROFILE["auto_tune_enabled"] = True
                save_comfort_profile(COMFORT_PROFILE)

            reason = f"Manual Remote Sync: ซิงค์สถานะแอร์เป็น {target_power} (เปิด/ปิดด้วยรีโมทจริง)"
            ambi_db.record_action(
                action_type='thermal_sync',
                power=target_power,
                temperature=AC_STATE['temperature'],
                fan=AC_STATE['fan'],
                swing=AC_STATE.get('swing', 'Auto'),
                mode=AC_STATE['mode'],
                trigger_reason=reason,
                room_temp=AC_STATE.get('room_temp'),
                room_humidity=AC_STATE.get('room_humidity'),
                humidex=AC_STATE.get('humidex'),
                result=f"State Synced ({prev_power} -> {target_power})"
            )
            hub_log(f"[STATE SYNC] AC power state manually synced to: {target_power} (Prev: {prev_power})")
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "OK",
                "synced_power": target_power,
                "prev_power": prev_power,
                "ac_state": AC_STATE
            }).encode('utf-8'))
            return

        # 15. Serve HTML Dashboard
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        html_page = get_dashboard_html()
        self.wfile.write(html_page.encode('utf-8'))

