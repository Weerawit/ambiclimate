#!/usr/bin/env python3
"""
Ambi Climate All-in-One Local Hub & Hybrid Comfort AI
-----------------------------------------------------
Refactored using Model-View-Controller (MVC) Architecture:
  - Models:
      * models.config: Network auto-detection, paths, locks, logging
      * models.ac_state: AC in-memory state, hardware device profiles, pending IR queue
      * models.comfort: Canadian Humidex calculation, comfort preferences, SQLite sync
  - Views:
      * views.dashboard_view: Serves responsive web dashboard HTML
  - Controllers:
      * controllers.hardware_controller: Ambi 8070 protocol, Daikin IR 4998 engine, LED
      * controllers.api_controller: Web Dashboard APIs, HomeKit/Homebridge endpoints
      * controllers.background_controller: DNS, Cloud Mock (8866/8867), Beacon, Auto-tuning
"""

import sys
import os
import time
import threading

# Re-export all Model attributes for 100% backward compatibility
from models.config import (
    CURRENT_TIMEZONE, DASHBOARD_PORT, detect_gateway_ip, detect_local_ip,
    detect_wan_ip, refresh_network_settings, ROUTER_GATEWAY_IP, HOST_IP,
    ROUTER_WAN_IP, DNS_REDIRECT_IP, DIR, CERT_FILE, KEY_FILE, PROFILE_FILE,
    DASHBOARD_HTML_FILE, LOG_FILE, hub_log, AMBI_HW_LOCK, AMBI_PORT_8070_LOCK,
    AMBI_READY_EVENT, PENDING_IR_LOCK
)

from models.comfort import (
    DEFAULT_COMFORT_PROFILE, load_comfort_profile, save_comfort_profile,
    COMFORT_PROFILE, calculate_humidex, evaluate_comfort
)

from models.ac_state import (
    PROFILE, DEVICE, APPLIANCE, REAL_DEVICE_ID, DEVICE_UUID, MAC_ADDRESS,
    IRP_ID, AC_STATE, AMBI_IP, AMBI_AUTO_RETARGETED, POLL_SENSORS_ENABLED,
    CONSECUTIVE_OUT_OF_BOUNDS, PENDING_IR_COMMAND, get_cached_ambi_ip,
    get_ambi_ip, set_ambi_ip, queue_pending_ir, clear_pending_ir, get_pending_ir_status
)

# Re-export View attributes
from views.dashboard_view import (
    get_dashboard_html, WEB_DASHBOARD_HTML
)

# Re-export Controller attributes
from controllers.hardware_controller import (
    check_and_flush_pending_ir, update_ambi_ip, send_ambi_cmd,
    get_cloud_server_setting, change_cloud_server, fetch_ambi_system_log,
    set_ambi_led_green, set_ambi_led_brightness, query_live_sensors,
    send_daikin_ir
)

from controllers.api_controller import (
    ThreadedHTTPServer, AmbiAPIHandler
)

from controllers.background_controller import (
    AMBI_SPECIFIC_DOMAINS, AMBI_SHARED_DOMAINS, parse_dns_domain,
    make_dns_redirect_response, forward_dns_upstream, run_dns,
    run_https, run_http, run_cloud_mock, led_keepalive_worker,
    run_beacon_listener, auto_tuning_worker, poll_live_sensors,
    interactive_cli
)


def main():
    hub_log("=" * 68)
    hub_log("🚀 AMBI CLIMATE 2 ALL-IN-ONE LOCAL CLOUD & COMFORT AI HUB (MVC)")
    hub_log("=" * 68)
    hub_log(f"  Server Host LAN IP       : {HOST_IP}")
    hub_log(f"  Router Gateway IP        : {ROUTER_GATEWAY_IP}")
    hub_log(f"  Router Public/WAN IP     : {ROUTER_WAN_IP}")
    hub_log(f"  DNS Redirect Target IP   : {DNS_REDIRECT_IP}")
    hub_log(f"  Ambi Device IP (Locked)  : {get_ambi_ip() or 'Waiting for connect query...'}")
    hub_log(f"  Cloud Ports              : TCP 8866 (Plain) & TCP 8867 (TLS 1.2)")
    hub_log(f"  Dashboard Web            : http://localhost:{DASHBOARD_PORT} (or http://{HOST_IP}:{DASHBOARD_PORT})")
    hub_log(f"  OS Timezone Synced       : {CURRENT_TIMEZONE} ({time.strftime('%Z %z')})")
    hub_log("=" * 68)

    # 1. DNS Server (Port 53 UDP) - Targets & query monitors
    threading.Thread(target=run_dns, daemon=True).start()

    # 2. Dedicated Cloud Mock Servers (8866 & 8867)
    threading.Thread(target=run_cloud_mock, args=(8866,), daemon=True).start()
    threading.Thread(target=run_cloud_mock, args=(8867,), daemon=True).start()

    # 3. HTTP (80) & HTTPS (443) Servers
    threading.Thread(target=run_http, args=(80,), daemon=True).start()
    threading.Thread(target=run_https, args=(443,), daemon=True).start()

    # 4. Web UI Dashboard (:9090 - Port 8080 is reserved/used by other service)
    threading.Thread(target=run_http, args=(DASHBOARD_PORT,), daemon=True).start()

    # 5. Live Hardware Sensor Poller (TCP 8070 to Ambi Climate) - ดึงข้อมูล Pull Query อัตโนมัติทุก 20 วินาที
    threading.Thread(target=poll_live_sensors, args=(20,), daemon=True).start()
    hub_log("[+] Live Hardware Sensor Poller (Pull Query :8070) is ENABLED (every 20s).")

    # 6. Hybrid Local Comfort AI Auto-Tuning Worker
    threading.Thread(target=auto_tuning_worker, daemon=True).start()

    # 7. AMX Beacon Listener (Port 9131 UDP)
    threading.Thread(target=run_beacon_listener, daemon=True).start()

    # 8. Solid Green LED Keep-Alive Watchdog (Reaffirms every 120s)
    threading.Thread(target=led_keepalive_worker, args=(120,), daemon=True).start()

    # 9. Interactive Console Command Worker
    threading.Thread(target=interactive_cli, daemon=True).start()

    print("\n[OK] Ready! Focused on Cloud Ports 8866 & 8867 and DNS queries...\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nExiting...")


if __name__ == "__main__":
    main()
