# Ambi Climate 2 Local Revive - Agent Memory & Context Rules

> **IMPORTANT FOR ANTIGRAVITY AGENTS:**
> This file contains the complete persistent memory, hardware parameters, network architecture, and operational rules for the Ambi Climate 2 local revive project. Always read and adhere strictly to these rules in every session.

---

## 1. Project Overview & Working Directory
* **Goal:** Revive abandoned Ambi Climate 2 (AC02) hardware units to run 100% locally without cloud dependencies.
* **Core Codebase Location:** `c:\Users\maneepon\Documents\Projects\Ambi Climate\ambiclimate` (All code edits, git commits, and scripts MUST be inside this folder).
* **Git Repository:** `git@github.com:Weerawit/ambiclimate.git` (Branch: `main`).

---

## 2. Network & Server Configuration
* **Target Server:** Raspberry Pi (Raspbian GNU/Linux 10 Buster) with Network Bonding (`bond0`).
* **Fixed Server LAN IP:** `192.168.1.199` (Configured in `docker-compose.yml` and `ambi_hub.py`).
* **Router Default Gateway:** `192.168.1.1` (Detected automatically).
* **Router WAN IP (CGNAT / Public):** Auto-detected via web probe (e.g. `27.130.5.178` or `100.112.62.200`).
* **DNS Redirect Target:** Matches Router WAN IP so OpenWrt/dnsmasq `--stop-dns-rebind` does not reject responses.
* **Web Dashboard Port:** **`9090`** (`http://192.168.1.199:9090`).
  > [!WARNING]
  > **DO NOT USE PORT 8080!** Port 8080 is already occupied by another service on the Raspberry Pi. The dashboard must strictly bind only to port `9090`.

---

## 3. Hardware Architecture & Ports
| Port | Protocol | Purpose | Key Notes |
| :--- | :--- | :--- | :--- |
| **9090** | HTTP | Web UI Dashboard & REST API | Replaced port 8080. Accessible at `http://192.168.1.199:9090` |
| **4998** | TCP | Global Caché iTach WF2IR | **Only 1 TCP connection allowed at a time!** IR Port `1:1` |
| **8070** | TCP | Ambi Native Hardware Telemetry | Protected with `AMBI_PORT_8070_LOCK`. Timeout = 7.0s |
| **8867** | TLS 1.2 TCP | Ambi Cloud Sync (`connect.smartambi.com`) | Self-signed certificate chain (`server_cert.pem`) |
| **8866** | Plain TCP | Ambi Cloud Framing (`connect.ambiclimate.com`) | Backup raw socket |
| **53** | UDP | Local DNS Interceptor & Redirection | Intercepts `*.ambiclimate.com`, `*.smartambi.com` |
| **9131** | UDP | AMX Beacon Multicast (`239.255.250.250`) | Global Caché discovery |

---

## 4. Hardware Communication Protocols

### A. Air Conditioner IR Control (Daikin Inverter ARC480A46)
* **Model:** Daikin FTKQ / FTKF / Sabai Inverter. Remote: `ARC480A46`.
* **Protocol:** **Protocol B (216-bit, 2-Frame)** at 38 kHz.
  * **Frame 1:** `11 DA 27 00 C5 00 00 D7` (Header, 8 bytes)
  * **Inter-frame Gap:** 29,000 µs
  * **Frame 2:** 19 bytes (Mode, Temp, Fan, Swing, Power, Checksum)
  * Sent via Global Caché command format: `sendir,1:1,1,38000,1,1,...`

### B. Ambi Climate Port 8070 Native Protocol
* **Packet Request Format:** `[0x07 (ASCII 7)]` + `[2-char sequence, e.g. '00']` + `[Command]` + `[\r]`
* **Packet Response Format:** `[0x07]` + `[2-char seq]` + `['0' (status OK)]` + `['N' + 2-char code]` + `[Payload]` + `[\r\n]`
* **Essential Commands:**
  * `NTP` : Temperature query (returns `+2889C2` = 28.89°C)
  * `NHM` : Humidity query (returns `+4973%2` = 49.73%)
  * `NID` : Real hardware ID (`05D7FF353831564B43158715`)
  * `NLL1 <0-10000>` : Front LED PWM brightness (`0` = OFF, `5700` = normal 57%, `10000` = 100%)
  * `NLD` : Turn front LED solid green
  * `NCA` : Query cloud server address
  * `NCE <host:port>` : Change cloud server destination
  * `NCD` : Force reconnect
  * `NSL` : System dump log

---

## 5. Raspberry Pi Buster (Debian 10) Docker Rules
* **Critical Issue:** Raspbian 10 Buster has an outdated `libseccomp2` (2.3.x). Modern Docker images based on Debian 12 (Bookworm) use Glibc 2.36+, which calls `clone3()` to spawn threads. Buster's seccomp intercepts `clone3()` and returns `EPERM`, causing `RuntimeError: can't start new thread`.
* **Mandatory Fixes:**
  1. `Dockerfile` **MUST** use `FROM python:3.9-slim-buster` (compiled for Buster with Glibc 2.28 which uses `clone()`).
  2. `docker-compose.yml` **MUST** have `security_opt: [ "seccomp:unconfined" ]`.
  3. `docker-compose.yml` **MUST** use `network_mode: "host"` so UDP 53 DNS and UDP 9131 Beacon are bound directly.

---

## 6. Comfort AI & Operational Rules
* **Felt Temperature:** Calculated using the Canadian Humidex formula from real-time temp and relative humidity.
* **Auto Sensor Polling:** Background worker queries Port 8070 every 20 seconds.
* **Auto-Tuning Hold:** Never trigger IR transmission while AC is OFF.
* **Front LED:** Once Ambi client IP is detected, immediately set LED to Solid Green (`NLD`). Keep-alive worker reaffirms it every 120s.

---

## 7. Fast Operational Commands

### Update & Run on Raspberry Pi:
```bash
cd ~/ambiclimate
git pull
sudo docker compose up -d --build
sudo docker logs -f ambi-hub
```

### Run Locally on Windows:
```bash
run_hub.bat
# or
python ambi_hub.py
```

