# Ambi Climate Local Hub & Hybrid Comfort AI

Revive and operate abandoned **Ambi Climate 2** hardware units locally without official cloud backend dependence, featuring Canadian Humidex Comfort AI, Daikin Inverter AC control, and multi-protocol hardware communication.

---

## 🌟 Key Features

1. **Standalone Local Cloud Server:**
   - Emulates official Ambi Climate backend on ports `8866` (Plain TCP) and `8867` (TLS 1.2 with custom certificate chain).
   - Responds to Ambi native commands (`NPS`, `NCO`, `NHS`, `NID`, `NSL`).
   - Integrated DNS interceptor on UDP `53` and AMX Beacon detector on UDP `9131`.

2. **Hybrid Local Comfort AI:**
   - Calculates **Canadian Humidex** felt temperature from live room temperature and relative humidity.
   - 7-tier comfort scale (`Freezing`, `Too Cold`, `Cool`, `Comfortable`, `Warm`, `Too Warm`, `Hot`).
   - Personal preference learning: Remembers user comfort offsets (`user_comfort_profile.json`).
   - Safe auto-tuning engine with deadband filters and 10-minute cooldown protection.

3. **Daikin AC Control (ARC480A46 / Protocol B):**
   - Transmits native 216-bit Daikin IR signals via the Ambi Climate's built-in Global Caché IR transmitter (Port `4998`).

4. **Modern Responsive Web Dashboard:**
   - Live real-time room metrics & Comfort Index at `http://localhost:9090` (or `http://192.168.1.199:9090`).
   - Interactive AI comfort dials & teaching chips matching official Ambi Climate App manual.
   - LED brightness slider & presets, manual on-demand sensor query, and background auto-polling.
   - Full Daikin remote control panel and Cloud target manager (`NCA`, `NCE`, `NCD`).

---

## 🚀 Quick Start

### Option A: Run Directly on Windows
Double-click `run_hub.bat` or run:
```bash
python ambi_hub.py
```
Access the dashboard at `http://localhost:9090`.

### Option B: Run on Raspberry Pi / Linux via Docker Compose
```bash
git clone https://github.com/Weerawit/ambiclimate.git
cd ambiclimate
sudo docker compose up -d --build
```
Access the dashboard at `http://192.168.1.199:9090`.

---

## 📡 Hardware & Protocol Architecture

| Port | Protocol | Purpose |
| :--- | :--- | :--- |
| **9090** | HTTP | Modern Web Dashboard & REST APIs (`http://192.168.1.199:9090`) |
| **8867** | TLS 1.2 TCP | Ambi Cloud Sync & Telemetry (`connect.smartambi.com`) |
| **8866** | Plain TCP | Ambi Native Cloud Framing (`connect.ambiclimate.com`) |
| **8070** | TCP | Ambi Native Hardware Telemetry (`NTP`, `NHM`, `NCA`, `NCE`, `NLL1`, `NLD`) |
| **4998** | TCP | Global Caché iTach IR Transmitter Engine (Single connection) |
| **53** | UDP | Local DNS Interceptor & Redirection |
| **9131** | UDP | Global Caché AMX Beacon Multicast (`239.255.250.250`) |

---

## 📄 License
MIT License.

