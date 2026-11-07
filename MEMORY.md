# 🧠 AMBI CLIMATE 2 - PROJECT MEMORY & CHEATSHEET

เอกสารสรุปความทรงจำ ข้อมูลจำเพาะทางเทคนิค ผังระบบ และคู่มือใช้งานฉบับย่อ สำหรับใช้งานต่อทันทีโดยไม่ต้องเริ่มต้นศึกษาใหม่

---

## 📌 ข้อมูลระบบโดยสรุป (System Specs)

* **อุปกรณ์เป้าหมาย:** Ambi Climate 2 (Model: AC02)
* **Real Device ID:** `05D7FF353831564B43158715`
* **MAC Address:** `DC:E5:33:13:02:BD`
* **Fixed Server IP:** `192.168.1.199` (Raspberry Pi 3/4 รัน Raspbian 10 Buster บนพอร์ต `bond0`)
* **Default Router Gateway:** `192.168.1.1`
* **Web Dashboard URL:** **`http://192.168.1.199:9090`** (⚠️ พอร์ต 8080 ถูกห้ามใช้เนื่องจากมีเซอร์วิสอื่นบน Pi ใช้งานอยู่แล้ว)
* **แอร์ที่ควบคุม:** Daikin Inverter (ARC480A46 / Protocol B 216-bit)
* **พอร์ตส่งสัญญาณ IR:** TCP `4998` (Global Caché iTach WF2IR - อนุญาต 1 Connection เท่านั้น)
* **พอร์ตข้อมูลเซ็นเซอร์ตัวเครื่อง:** TCP `8070` (Ambi Native Protocol)
* **พอร์ตจำลอง Cloud:** TCP `8866` (Plain TCP) และ TCP `8867` (TLS 1.2)

---

## 🕹️ CLI Console Shortcuts (`ambi_hub.py`)

เมื่อรันผ่าน Terminal หรือ Windows Console สามารถกดปุ่มแล้ว Enter ได้ทันที:
* `[1]` : ตรวจสอบที่อยู่ Cloud Server ปัจจุบันที่ตั้งไว้ในตัวเครื่อง Ambi (`NCA`)
* `[2]` : สั่งเปลี่ยน Cloud ในตัวเครื่องชี้มาที่เซิร์ฟเวอร์ TLS -> `192.168.1.199:8867` (`NCE + NCD`)
* `[3]` : สั่งเปลี่ยน Cloud ในตัวเครื่องชี้มาที่เซิร์ฟเวอร์ TCP -> `192.168.1.199:8866` (`NCE + NCD`)
* `[4]` : สั่ง Ambi Reconnect หลุดและต่อใหม่ทันที (`NCD`)
* `[5]` : ดึงและอ่านค่าเซ็นเซอร์สดจากตัวเครื่องทันที (`NTP / NHM / NLU`)
* `[6]` : สั่งไฟ LED หน้าเครื่องเป็นสีเขียวค้าง (`Solid Green / NLD`)
* `[7]` : ปรับระดับความสว่าง LED หน้าเครื่อง (`0` = ปิด, `1000 - 10000`, ดีฟอลต์ `5700`)
* `[P]` : สลับเปิด/ปิดการดึงเซ็นเซอร์อัตโนมัติ (Auto Pull Query ทุก 20 วินาที)
* `[N]` : ตรวจจับและอัปเดตข้อมูลเครือข่ายใหม่ (Auto Detect Network)
* `[M]` : สลับโหมด Ambi (1=Comfort, 2=Temperature, 3=Manual, 4=Away, 0=Off)
* `[L]` : ดึงและแสดง System Dump Log ของตัวเครื่อง Ambi (`NSL`)
* `[R]` : คืนค่า Cloud กลับไปที่ฮ่องกง (`connect.smartambi.com:8867`)

---

## 🌐 REST API Endpoints (Port 9090)

| Endpoint | Method | คำอธิบาย |
| :--- | :---: | :--- |
| `/api/state` | GET | ดึงสถานะเครื่องแอร์, สภาพอากาศ, Humidex, และค่า Network ทั้งหมด |
| `/api/control?temp=24&fan=Auto&power=On` | GET | ส่งคำสั่ง IR ควบคุมแอร์ Daikin ผ่านพอร์ต 4998 |
| `/api/feedback?choice=comfy` | GET | ป้อน Feedback สอน AI (`freezing`, `cold`, `comfy`, `warm`, `hot`) |
| `/api/mode?mode=Comfort` | GET | สลับโหมดการทำงาน (`Comfort`, `Temperature`, `Manual`, `Away`, `Off`) |
| `/api/led/brightness?level=5700` | GET | ปรับระดับแสงไฟ LED (`0-10000`) |
| `/api/led/green` | GET | สั่งไฟหน้าเครื่องเป็นสีเขียวค้างทันที |
| `/api/sensors/query` | GET | สั่ง Query อุณหภูมิและความชื้นสดจาก Ambi พอร์ต 8070 ทันที |
| `/api/sensors/polling?enable=1` | GET | เปิด/ปิดการดึงค่าเซ็นเซอร์เบื้องหลังทุก 20 วินาที |
| `/api/history/metrics?range=4h` | GET | ดึงข้อมูล Time-series กราฟสภาพอากาศจาก SQLite (4h, 24h, 7d) |
| `/api/history/timeline?limit=50` | GET | ดึงรายการประวัติคำสั่ง/กิจกรรม (Deployments Timeline) จาก SQLite |
| `/api/sync/state?power=On` | GET | ซิงค์สถานะแอร์ (เปิด/ปิด) จากรีโมทจริงหรือ Smart Plug เข้าระบบ |
| `/api/network/detect` | POST/GET | สั่งคำนวณและตรวจจับ IP เครือข่ายใหม่ |
| `/api/cloud/change?server=...` | GET | สั่งเปลี่ยนเป้าหมาย Cloud ในเครื่อง Ambi |
| `/api/cloud/reconnect` | GET | สั่ง NCD ตัดและเชื่อมต่อใหม่ |
| `/api/system_log` | GET | ดึง System Dump Log (NSL) ออกมาแสดง |

---

## ❄️ โครงสร้างรหัส IR Daikin (ARC480A46 / Protocol B)

* **ความถี่:** 38,000 Hz
* **Frame 1 (Header 8 ไบต์):** `11 DA 27 00 C5 00 00 D7`
* **Gap คั่นเฟรม:** 29,000 µs
* **Frame 2 (Command 19 ไบต์):**
  * Byte 0-2: `11 DA 27`
  * Byte 5: Power & Mode (`0x31` = ON Cool, `0x30` = OFF Cool)
  * Byte 6: Temperature (`temp * 2`, เช่น 24°C = `0x30`)
  * Byte 8: Fan & Swing (Fan Auto = `0xA0`, Quiet = `0xB0`, Swing Vertical = `0x0F`)
  * Byte 18: Checksum (ผลรวมไบต์ modulo 256)

---

## 📟 โครงสร้างโปรโตคอล Ambi Climate (Port 8070)

* **ส่งคำสั่ง:** `\x07` + `00` + `[CMD]` + `\r`
* **ตอบรับ:** `\x07` + `00` + `0` + `[CMD]` + `[Payload]` + `\r\n`
* ตัวอย่าง:
  * `\x0700NTP\r` -> ตอบ `\x07000NTP+2671C2\r\n` = 26.71 °C
  * `\x0700NHM\r` -> ตอบ `\x07000NHM+6161%2\r\n` = 61.61 %
  * `\x0700NLD\r` -> ไฟเขียว
  * `\x0700NLL1 5700\r` -> ปรับแสง 57%

---

## 🐳 คำสั่ง Docker บน Raspberry Pi (Raspbian 10 Buster)

```bash
# 1. เข้าโฟลเดอร์โปรเจกต์
cd ~/ambiclimate

# 2. ดึงโค้ดล่าสุดจาก GitHub
git pull

# 3. สั่ง Rebuild และรันในพื้นหลัง
sudo docker compose up -d --build

# 4. ดูการทำงานแบบสด
sudo docker logs -f ambi-hub

# 5. สั่งหยุดการทำงาน
sudo docker compose down
```

### เกร็ดความรู้ทางเทคนิคเรื่อง Docker บน Raspbian Buster:
* **ปัญหา `RuntimeError: can't start new thread`:** เกิดจาก `python:3.12-slim` รันบน Debian 12 Bookworm ที่เรียกใช้ syscall `clone3()` ซึ่งถูก `libseccomp2` รุ่นเก่าของ Buster บล็อกด้วย `EPERM`
* **ทางแก้สำเร็จ:** ใช้ `FROM python:3.9-slim-buster` ควบคู่กับ `security_opt: [ "seccomp:unconfined" ]` ใน `docker-compose.yml`

