# Ambi Climate 2 - Local Revive & Progress Log

บันทึกสรุปข้อมูลการทดสอบ ผลลัพธ์ และสถานะการกู้ชีพเครื่อง Ambi Climate 2 ให้ทำงานแบบ Local โดยไม่ต้องพึ่งพา Cloud

---

## 1. ข้อมูลฮาร์ดแวร์และระบบเครือข่าย

* **อุปกรณ์:** Ambi Climate 2 (Model: AC02)
* **IP Address:** `192.168.1.151` (เดิมคือ `192.168.1.181` / `192.168.1.121`)
* **MAC Address:** `DC:E5:33:13:02:BD`
* **Real ID:** `05D7FF353831564B43158715`
* **Device UUID:** `72eb416f-a2da-484b-8295-a6b2d440759d`
* **IP เครื่องคอมพิวเตอร์ (Host PC):** `192.168.1.138`
* **Global Caché Interface:**
  * TCP Port: `4998` (สถานะ: **OPEN**)
  * Firmware: `710-1001-05`
  * อุปกรณ์: `device,0,0 WIFI` และ `device,1,3 IR` (พอร์ตหลักในตัวเครื่องคือ `1:1`)
  * **ข้อจำกัดสำคัญ:** รับได้แค่ **1 TCP Connection พร้อมกันเท่านั้น** (หากเกิด Timeout ให้ถอดปลั๊ก USB ของ Ambi Climate เสียบใหม่ 3 วินาที)

---

## 2. ข้อมูลแอร์และสัญญาณ IR (ทดสอบแล้ว - ทำงานสำเร็จ 100%)

* **ยี่ห้อแอร์:** Daikin Inverter (Sabai Inverter / FTKQ / FTKF / FTKM)
* **รุ่นรีโมทจริง:** **`ARC480A46`** (ซีรีส์ ARC480 / ARC433)
* **ความถี่สัญญาณ:** 38,000 Hz (38 kHz)
* **โปรโตคอลที่ทดสอบแล้วใช้งานได้จริง:** **Protocol B (Standard Daikin 216-bit, 2-Frame)**
  * **Frame 1 (Header 8 ไบต์):** `11 DA 27 00 C5 00 00 D7`
  * **Gap คั่นเฟรม:** 29,000 µs (~29 ms)
  * **Frame 2 (Command 19 ไบต์ - Cool 24°C ON):** `11 DA 27 00 00 31 30 00 A0 00 00 00 00 00 00 C0 00 00 D3`
  * **Frame 2 (Command 19 ไบต์ - Cool OFF):** `11 DA 27 00 00 30 30 00 A0 00 00 00 00 00 00 C0 00 00 D2`
  * **คำสั่ง Global Caché:** `sendir,1:1,1,38000,1,1,129,66,16,49,16,16,16,...`
  * **ผลการทดสอบ:** Ambi ตอบกลับ `completeir,1:1,1` และ **แอร์ส่งเสียงดัง "ปิ๊บ" เปิดทำงานเรียบร้อย!**

---

## 3. ประวัติการทดสอบที่ผ่านมา (ไม่ต้องทำซ้ำ)

| ลำดับ | รายการทดสอบ | ผลลัพธ์ | หมายเหตุ |
| :--- | :--- | :--- | :--- |
| 1 | ทดสอบพอร์ต 4998 (Global Caché) | **สำเร็จ** | ตอบกลับ Version และ Devices ครบถ้วน |
| 2 | รันโค้ด IR Fujitsu (Profile 235 เดิม) | **ไม่ติด** | เพราะแอร์จริงคือ Daikin ไม่ใช่ Fujitsu |
| 3 | ดึงข้อมูล SQLite เก่าจาก iOS Backup | **สำเร็จ** | ได้ MAC Address, Device ID, และ Saved Sensor State (24.74°C, 54.8%) |
| 4 | ยิง IR Daikin Protocol A (F0 Header) | รอดำเนินการ | ถูกขัดจังหวะด้วย Connection Timeout |
| 5 | ยิง IR Daikin Protocol B (C5 Header) | **สำเร็จ (แอร์ดังกดติด!)** | แอร์ Daikin ARC480 ตอบรับคำสั่งและเปิดทำงาน ("ดังแล้ว") |
| 6 | สแกนพอร์ตบนตัวเครื่อง Ambi Climate | **พบพอร์ตสำคัญ** | พบ **Port 8070 เปิดอยู่ (OPEN)** และ Port 4998 เปิดอยู่ |
| 7 | ทดสอบคำสั่ง Global Caché บน 4998 | **สรุปได้ชัดเจน** | iTach มีเฉพาะ WIFI และ IR ไม่มีโมดูล Sensor โดยตรง (เซ็นเซอร์อยู่ที่บอร์ดหลักของ Ambi) |
| 8 | Reverse Engineering ถอดรหัส APK Ambi | **ค้นพบ Protocol ลับ!** | พบโปรโตคอลสื่อสารตรงของ Ambi Climate (รายละเอียดหัวข้อ 4 ด้านล่าง) |
| 9 | ทดสอบยิงคำสั่ง Ambi ผ่าน Port 8070 ครั้งแรก | **พบพฤติกรรม Socket** | ปิดเปิด Socket ถี่ๆ จะติด Timeout ทันที ต้องใช้การเชื่อมต่อค้างไว้ 1 Socket (Persistent) |
| 10 | ผลการสแกนหลายพอร์ตพร้อมกันทำให้ Socket Table เต็ม | **พบสาเหตุ Port Closed** | ชิป Wi-Fi ค้างเมื่อถูกสแกนหลายพอร์ตถี่ๆ ปรับลดเหลือเฉพาะพอร์ตเป้าหมาย 4998 และ 8070 |
| 11 | ถอดรหัส JADX และยิงคำสั่ง Port 8070 ด้วย Framed Packet (`\x0700NTP\r`) | **สำเร็จ 100%! ดึงค่าเซ็นเซอร์สดได้แล้ว!** | Ambi ตอบกลับค่าเซ็นเซอร์สดเรียลไทม์จากฮาร์ดแวร์: Temp `28.89 °C`, Humidity `49.73 %`, ID `05D7FF353831564B43158715`, Firmware `882` |
| 12 | ย้าย IP ใหม่ `192.168.1.121` และทดสอบคำสั่งควบคุมไฟ LED | **สำเร็จ 100%!** | อัปเดต IP ใหม่เชื่อมต่อได้สมบูรณ์ทั้ง 4998 และ 8070, ตั้งระดับแสงไฟ LED กลับมาที่ `5730` (`NLL1 5730`) และทดสอบ `NVR1` ผ่านฉลุย |

---

## 4. แผนที่โปรโตคอล Ambi Climate (แกะจาก Source Code APK)

จากการแกะ Source Code ในคลาส `ClientBuf.java`, `ClientParse.java`, `Cmd.java`, และ `Protocol.java`:
เครื่อง Ambi Climate มีโปรโตคอลเฉพาะตัว ทำงานผ่าน **TCP Port 8070**:

### โครงสร้าง Packet ในการส่งคำสั่ง (Request):
`[0x07 (ASCII 7 / BEL)]` + `[2 หลัก Sequence Counter เช่น '00']` + `[คำสั่งนำหน้าด้วย N]` + `[\r (0x0D)]`

* ตัวอย่างคำสั่ง:
  * **`\x0700NTP\r`** : **TEMPERATURE** (อ่านอุณหภูมิสด)
  * **`\x0700NHM\r`** : **HUMIDITY** (อ่านความชื้นสด)
  * **`\x0700NLU\r`** : **LUMINOSITY** (อ่านค่าเซ็นเซอร์แสง)
  * **`\x0700NID\r`** : **UNIQUE ID** (ขอ Real ID ของเครื่อง)
  * **`\x0700NPV\r`** : **PROTOCOL VERSION** (เวอร์ชันโปรโตคอล)
  * **`\x0700NFV\r`** : **FIRMWARE VERSION** (เวอร์ชันเฟิร์มแวร์)
  * **`\x0700NUT\r`** : **UP TIME** (เวลาที่เปิดเครื่องเป็นวินาที)
  * **`\x0700NWQ\r`** : **WIFI QUALITY** (คุณภาพสัญญาณ Wi-Fi เป็น %)
  * **`\x0700NEHFIRST_TEST\r`** : **ECHO HOST** (ทดสอบการตอบรับ)

### โครงสร้าง Packet ที่ Ambi Climate ตอบกลับ (Response):
`[0x07]` + `[Sequence 2 หลัก]` + `[Status Code 1 หลัก: '0'=OK]` + `['N' + รหัส 2 หลัก]` + `[Payload ข้อมูล]` + `[\r\n]`

* **ตัวอย่างผลลัพธ์จริงที่เครื่องตอบกลับ:**
  * อุณหภูมิ: `\x07000NTP+2889C2\r\n` -> แปลงค่า: `+2889` ทศนิยม 2 ตำแหน่ง (`C2`) = **`28.89 °C`**
  * ความชื้น: `\x07000NHM+4973%2\r\n` -> แปลงค่า: `+4973` ทศนิยม 2 ตำแหน่ง (`%2`) = **`49.73 %`**
  * รหัสประจำเครื่อง: `\x07000NID05D7FF353831564B43158715\r\n` = **`05D7FF353831564B43158715`**
  * เวอร์ชันเฟิร์มแวร์: `\x07000NFV882\r\n` = **`882`**
  * Uptime: `\x07000NUT169586\r\n` = **`169,586 วินาที (~47 ชั่วโมง)`**
  * Wi-Fi Quality: `\x07000NWQ100\r\n` = **`100%`**

---

## 5. ที่มาของค่า 24.74 °C และ 54.8 % บนหน้าเว็บ

* ค่าตัวเลข `24.74 °C` และ `54.8 %` ที่เคยเห็นบนหน้าเว็บเดิม มาจากไฟล์ `decompiled_analysis/user_device_profile.json` (ข้อมูล SQLite เก่าใน iOS backup ก่อน Cloud ปิดตัว)
* **ปัจจุบัน:** ระบบได้รับการอัปเดตให้ดึง **ค่าสดจากฮาร์ดแวร์ตัวเครื่องจริงแบบเรียลไทม์** ผ่านคำสั่ง `\x0700NTP\r` และ `\x0700NHM\r` บน Port 8070 เรียบร้อยแล้ว (อัปเดตอัตโนมัติขึ้นหน้าเว็บทุก 20 วินาที)

---

## 6. โครงสร้างไฟล์ปัจจุบัน (รวมเหลือเฉพาะที่จำเป็น)

```text
/Ambi Climate/
├── PROGRESS.md       # บันทึกสถานะและความคืบหน้าทั้งหมด (ไฟล์นี้)
├── daikin_ir.py      # ไลบรารีคำนวณไบต์และ Timing สัญญาณ IR แอร์ Daikin
├── test_daikin.py    # โปรแกรมรีโมทสั่งงานแอร์ & เครื่องมือสแกนหาเซ็นเซอร์ (All-in-one)
├── test_daikin.bat   # ตัวคลิกรัน test_daikin.py บน Windows
├── ambi_hub.py       # เว็บเซิร์ฟเวอร์ Local Dashboard (http://localhost:8080)
├── run_hub.bat       # ตัวคลิกรัน ambi_hub.py บน Windows
├── server_cert.pem   # ใบรับรอง SSL สำหรับจำลอง HTTPS
└── server_key.pem    # Private key สำหรับจำลอง HTTPS
```

---

## 7. วิธีใช้งานระบบ

### 1) สั่งงานและสแกนผ่าน WSL / Terminal (ไม่ต้องกดเมนูเอง):
สามารถสั่งรันคำสั่งได้ทันทีผ่าน WSL:
* **อ่านค่าเซ็นเซอร์สดจากเครื่อง:**
  ```bash
  python3 test_daikin.py probe
  ```
* **เปิดแอร์ Daikin (Cool 24°C):**
  ```bash
  python3 test_daikin.py on
  ```
* **ปิดแอร์ Daikin:**
  ```bash
  python3 test_daikin.py off
  ```
* **ตรวจสอบสถานะการเชื่อมต่อ:**
  ```bash
  python3 test_daikin.py status
  ```

### 2) สั่งงานแอร์ผ่าน Command Line บน Windows:
ดับเบิลคลิกไฟล์ **`test_daikin.bat`** (หรือพิมพ์ `test_daikin.bat` ใน CMD)
* **กด `1`** : เปิดแอร์ Cool 24°C (Protocol B ทำงานแน่นอน)
* **กด `2`** : ปิดแอร์ (Turn OFF)
* **กด `3`** : ตั้งอุณหภูมิตามต้องการ (18 - 30°C)
* **กด `4`** : อ่านค่าเซ็นเซอร์สด (อุณหภูมิ, ความชื้น, แสง, Uptime, สถานะเครื่อง)
* **กด `5`** : ตรวจสอบสถานะการเชื่อมต่อ Ambi Climate

### 3) สั่งงานแอร์ผ่านหน้าเว็บ (Web Dashboard):
รัน **`run_hub.bat`** แล้วเปิดเบราว์เซอร์ไปที่:
* **บนคอมพิวเตอร์:** `http://localhost:8080`
* **บนมือถือ (Wi-Fi เดียวกัน):** `http://192.168.1.138:8080`
*(หน้าเว็บจะแสดงค่าอุณหภูมิและความชื้นสดเรียลไทม์จากตัวเครื่อง Ambi Climate โดยอัตโนมัติ)*

---

## 8. ผลการแกะและควบคุมไฟ LED (LED & Visual Response)

จากการ Reverse Engineering เฟิร์มแวร์และทดสอบยิงคำสั่งบน **Port 8070**:
พบกลไกควบคุมไฟหน้าเครื่อง 3 คำสั่ง:

1. **`NVR` (VISUAL_RESPONSE):**
   * คำสั่ง: `\x0700NVR<1-24>\r`
   * ตอบกลับ: `\x07000NVR\r\n` (ACK_OK)
   * หน้าที่: ทริกเกอร์แอนิเมชันสีไฟของฮาร์ดแวร์ Ambi เช่น:
     * สีฟ้าอมเขียว (Teal / Cyan) ขณะทำความเย็น (Cooling)
     * สีส้ม/เหลือง (Amber / Orange) ขณะทำความร้อน (Warming)
     * สีเขียว (Green) แสดงสถานะสบาย (Comfort)
     * ไฟกระพริบ Pairing/Strobe
   * วิธีทดสอบ: `python3 test_daikin.py led <1-24>`

2. **`NLL` (LED_LEVEL):**
   * คำสั่งอ่าน: `\x0700NLL\r` -> ตอบกลับ `1 5730` (หลักแรกคือ State: `1`=เปิด, `0`=ปิด | หลักหลังคือระดับ PWM)
   * คำสั่งตั้งค่าเปิด + กำหนดความสว่าง: `\x0700NLL1 <ระดับ 1-10000>\r`
   * **ปิดไฟ LED ดับสนิท (OFF):** `\x0700NLL0\r` (เปลี่ยน State เป็น `0 0` ปิดวงจรไฟสมบูรณ์)

3. **`NLD` (LED_HANDLER):**
   * ควบคุมช่องสี RGB แยกรายช่อง:
     * `NLD00` : ปิดสีแดง (Red OFF) | `NLD01` : เปิดสีแดง
     * `NLD10` : ปิดสีเขียว (Green OFF) | `NLD11` : เปิดสีเขียว
     * `NLD20` : ปิดสีน้ำเงิน (Blue OFF) | `NLD21` : เปิดสีน้ำเงิน

4. **การหยุดไฟกะพริบสีส้ม (Stop Offline Blinking):**
   * สาเหตุที่ไฟยังกะพริบส้ม: เฟิร์มแวร์ของ Ambi มีลูปตรวจจับคลาวด์ ถ้าต่อคลาวด์ไม่ได้จะสั่งกะพริบส้มเตือนผู้ใช้เป็นระยะ
   * คำสั่งหยุดลูปกะพริบ:
     * `\x0700NSD\r` : **SETUP_DONE** (บอกเครื่องว่ากระบวนการตั้งค่าเสร็จสิ้นแล้ว)
     * `\x0700NCD1\r` : **CLOUD_DISCONNECT** (สั่งให้เครื่องตัดการเชื่อมต่อคลาวด์ ไม่ต้องพยายามต่อเซิร์ฟเวอร์ภายนอกอีก)

---

## 9. ระบบตรวจจับ IP อัตโนมัติ (Auto-Discovery Engine - วิธีที่ 2)

แก้ปัญหาเรื่องเราเตอร์สุ่มเปลี่ยน IP บ่อย เมื่อเปิดเครื่องทิ้งไว้นาน ๆ:
* **กลไกที่ทำงาน:**
  1. **ตรวจจับจาก DNS Query:** เมื่อ Ambi Climate ร้องขอต่อคลาวด์ ตัวเซิร์ฟเวอร์ DNS ใน Hub จะจำ IP ของเครื่องทันที
  2. **ตรวจจับจาก Global Caché AMXB Beacon:** ดึง IP จาก UDP Multicast (Port 9131)
  3. **ตรวจจับจาก ARP Table:** ดึง IP ล่าสุดจากตาราง ARP โดยค้นหาจาก MAC `DC:E5:33:13:02:BD` ภายใน 0.05 วินาที
  4. **ระบบแคชไฟล์ `ambi_ip.txt`:** อัปเดตและแชร์ IP ล่าสุดระหว่างทุกโปรแกรมโดยอัตโนมัติ
* **ผลลัพธ์:** ผู้ใช้ไม่ต้องคอยดูหรือแก้ไขเลข IP อีกต่อไป ระบบจะตามไปเชื่อมต่อ IP ใหม่อัตโนมัติทันที 100%

---

## 10. วิเคราะห์ฮาร์ดแวร์ภายในจาก Teardown Report (FCC ID: 2AFE9AMBICL)

จากการวิเคราะห์เอกสาร Teardown และภาพถ่ายแผงวงจรภายในตัวเครื่อง Ambi Climate 2:

1. **IR Transmitter Array (หลอดอินฟราเรด 3 ทิศทาง):**
   * ติดตั้งอยู่บริเวณขอบบน 3 ตัวทำมุมกระจายรอบทิศทาง 180°
   * ขับสัญญาณผ่านโมดูล Global Caché iTach บน Port 4998
   * **สถานะ:** ควบคุมสั่งงานแอร์ Daikin ARC480 สำเร็จ 100% แล้ว

2. **PIR Motion Sensor (เซ็นเซอร์จับความเคลื่อนไหวคน):**
   * แผงวงจรเซ็นเซอร์พร้อมเลนส์ Fresnel สีขาว ต่อสายเคเบิล 3 เส้นเข้าบอร์ดหลัก
   * มีคำสั่งรองรับใน Native Protocol:
     * `NPC` : `PIR_COUNT` (อ่านสถิติจำนวนครั้งที่ตรวจพบความเคลื่อนไหว)
     * `NPL` : `PIR_LOAD` (อ่านค่าโหลด/สถานะตรวจจับคนสด)
   * **การนำไปใช้ต่อ:** สามารถดึงค่าคนอยู่ในห้องมาแสดงบน Dashboard และทำระบบสั่งปิดแอร์อัตโนมัติเมื่อไม่มีคนได้

3. **Piezo Buzzer (ลำโพงส่งเสียงเตือน):**
   * ติดตั้งอยู่บนบอร์ดหลักใกล้พอร์ต Micro-USB
   * มีคำสั่งรองรับใน Native Protocol:
     * `NBB` : `BUZZER` (ส่งสัญญาณเสียงปิ๊บ เช่น `NBB1` หรือ `NBB100`)
     * `NBL` : `BUZZER_LEVEL` (ปรับระดับความดังเสียง)
   * **ข้อควรระวัง:** ห้ามส่งคำสั่ง `NBZ` เพราะเป็นคำสั่งที่ชิปไม่รองรับและจะทำให้ TCP socket ตัดการเชื่อมต่อทันที

4. **Modular Wi-Fi Daughterboard (ZRC53V2) & Bluetooth LE:**
   * บอร์ดลูกเสียบการ์ด Wi-Fi พร้อมขั้วต่อสายอากาศ U.FL
   * ชิป Bluetooth Low Energy (BLE) พร้อมเสาอากาศลายทองแดงบน PCB
   * ควบคุมการส่งสัญญาณบลูทูธผ่านคำสั่ง `NIB` (IBEACON)

5. **พอร์ต UART Serial (Test Points TP1 - TP4):**
   * **จุดเชื่อมต่อบนแผงวงจร:** จุดวงกลมทองแดง Test Points 4 จุด (TX, RX, GND, VCC)
   * **ความสามารถหากเชื่อมต่อสาย:**
     * ต่อสาย USB-to-UART (FTDI / CP2102) ที่ Baudrate 115200 เพื่อดู Console Boot Log สด
     * เข้าถึง U-Boot Bootloader หรือ Root Shell ภายในชิป (หากเฟิร์มแวร์เปิดสิทธิ์ไว้)
     * ดัมป์ไฟล์รอม (Firmware Dump) จาก Flash Memory
   * **ข้อสรุปและการตัดสินใจ:** **ไม่จำเป็นต้องทำ (Method 3 Software-only ดีกว่า)** เนื่องจากการแกะเคสและบัดกรีสายมีความเสี่ยงที่บอร์ดจะช็อตเสียหาย และปัจจุบันเราสามารถควบคุมแอร์ Daikin (Port 4998) รวมถึงอ่านเซ็นเซอร์ อุณหภูมิ ความชื้น แสง Uptime ควบคุมไฟ LED (Port 8070) ผ่าน Wi-Fi ได้สมบูรณ์ 100% แล้ว

---

## 11. สาเหตุที่เปิดทิ้งไว้นานๆ แล้ว IP เปลี่ยนบ่อย & กลไกแก้ไข

* **สาเหตุเชิงลึก:**
  1. เฟิร์มแวร์ของ Ambi Climate มีระบบ **Cloud Watchdog** ที่คอยทดสอบการเชื่อมต่อกับเซิร์ฟเวอร์หลัก (`connect.ambiclimate.com`)
  2. เมื่อเซิร์ฟเวอร์คลาวด์ปิดตัวลงอย่างถาวร เครื่องจะต่อคลาวด์ไม่สำเร็จ
  3. หลังจาก Timeout ซ้ำๆ (ทุกประมาณ 15-30 นาที) Watchdog จะคิดว่า Wi-Fi ของบ้านขัดข้อง จึงสั่งรีเซ็ตชิป Wi-Fi และเริ่มกระบวนการ Re-association ใหม่
  4. ในการเชื่อมต่อ Wi-Fi ใหม่ เครื่องจะส่งคำขอ **DHCP Request** ไปหาเราเตอร์
  5. หากเราเตอร์ไม่ได้ตั้งค่า Static Lease / DHCP Reservation ไว้ เราเตอร์จะสุ่มแจก IP ใหม่จาก Pool ว่าง (เช่น `.181` -> `.121` -> `.151` -> `.152` ...)
* **วิธีแก้แบบ Software-Only (วิธีที่ 2 - ใช้งานได้จริงแล้ว):**
  * โค้ดใน [`test_daikin.py`](file:///mnt/c/Users/maneepon/Documents/Projects/Ambi%20Climate/test_daikin.py) และ [`ambi_hub.py`](file:///mnt/c/Users/maneepon/Documents/Projects/Ambi%20Climate/ambi_hub.py) จะรันฟังก์ชัน `get_ambi_ip()` ทุกครั้งก่อนส่งคำสั่ง
  * ค้นหา MAC `DC:E5:33:13:02:BD` จาก ARP Table และดักจับจาก DNS Port 53 โดยอัตโนมัติ
  * หาก IP เปลี่ยน ระบบจะบันทึกลง [`ambi_ip.txt`](file:///mnt/c/Users/maneepon/Documents/Projects/Ambi%20Climate/ambi_ip.txt) ทันที ผู้ใช้จึงไม่ต้องกังวลเรื่อง IP เปลี่ยนอีกต่อไป

---

## 12. สรุปบันทึกข้อห้ามและสิ่งที่ไม่ควรทดสอบซ้ำ (Do NOT Retry Log)

เพื่อป้องกันการเสียเวลาและการลองผิดลองถูกซ้ำ:

1. ❌ **ห้ามลองรหัสรีโมท Fujitsu (Profile 235 เดิม):** แอร์จริงของผู้ใช้คือ Daikin Inverter (รีโมท ARC480A46) ซึ่งต้องใช้ Daikin Protocol B (Header C5) เท่านั้น
2. ❌ **ห้ามส่งคำสั่ง `NBZ`:** ทำให้ TCP Socket 8070 พังและหลุด (Broken pipe) ทันที
3. ❌ **ห้ามสแกนพอร์ตแบบกวาดหลายพอร์ตพร้อมกัน (Port Scanning):** ทำให้ตาราง lwIP Socket Connection ของบอร์ดเต็ม ส่งผลให้อุปกรณ์ไม่ตอบสนอง ต้องรอรีเซ็ต
4. ❌ **ห้ามพยายามแฟลช Custom Firmware ผ่าน Wi-Fi (`NUH`/`NUS`):** Bootloader ของ Ambi มีระบบตรวจสอบ RSA Digital Signature และไม่มีไฟล์รอมทางการ หากแฟลชไฟล์ผิดจะทำให้เครื่องกลายเป็นที่ทับกระดาษ (Hard Brick) กู้คืนไม่ได้
5. ❌ **ไม่ต้องทำ Fake SSL Certificate หรือดักฟัง HTTPS:** เพราะแอปมือถือและการตั้งค่า Wi-Fi ไม่ได้ส่งใบรับรอง Root CAs ผ่าน Wi-Fi (ใบรับรองถูกฝังแน่นในตัวรอมของบอร์ดตั้งแต่โรงงาน)
6. ❌ **ไม่ต้องเปิดเคสบัดกรีพอร์ต UART Serial:** การควบคุมและอ่านเซ็นเซอร์ทั้งหมดผ่าน Port 4998 และ 8070 ทำได้ครบถ้วน 100% ทางระบบเครือข่ายแล้ว

---

## 13. ผลการดึง System Log สดจากเครื่อง (System Log & OS Architecture Discovery)

จากการยิงคำสั่ง `\x0701NSL\r` เข้า TCP Port 8070 สำเร็จ ได้ข้อมูล Raw Syslog จากเครื่องมาทั้งหมด **9,737 ไบต์** (บันทึกไว้ใน `ambi_system_dump.log`):

### 1. การค้นพบสถาปัตยกรรมภายใน (OS & Daemons):
* **ระบบปฏิบัติการ:** ชิป Wi-Fi Host รันระบบ **OpenWrt Embedded Linux**!
* **Network & Wi-Fi Management:**
  * ใช้ **`netifd`** (OpenWrt Network Interface Daemon)
  * ใช้ **`wpa_supplicant`** (IEEE 802.11i WPA/WPA2 client)
  * ใช้ **`uci`** (Unified Configuration Interface ใน `/etc/config/wireless`)
  * ไดรเวอร์ Wi-Fi: **`mac80211`** (`iw phy phy0`)
  * DNS/DHCP: **`dnsmasq`**
* **โปรเซสหลักควบคุมระบบ:** **`aircom`** (PID: `813`)
* **การสื่อสารระหว่าง Host กับ Slave MCU:**
  * Host (Linux OpenWrt) คุยกับ Slave MCU ผ่าน Serial/UART
  * Slave Firmware ตอบกลับ: `000980NSVV3.1.448_ALL`

### 2. ข้อมูลเวอร์ชันเฟิร์มแวร์และฮาร์ดแวร์ล่าสุด (ดึงสดเรียลไทม์):
* **Temperature:** `33.08 °C` (NTP)
* **Humidity:** `62.23 %` (NHM)
* **Luminosity:** `0 120 87` (NLU)
* **Real Device ID:** `05D7FF353831564B43158715` (NID)
* **Protocol Version:** `24` (NPV)
* **Firmware Build Version (Host):** `882` (NFV)
* **Slave Firmware Version (MCU):** `V3.1.448_ALL` (NSV)
* **Slave Build Version:** `448` (NBN)
* **Build Timestamp:** `2021-06-21 10:24:01` (NBT)
* **Uptime:** `465,940 วินาที (~5.4 วัน)` (NUT)
* **WiFi Quality:** `100%` (NWQ)
* **USB Logging Status:** `0` (Disabled) (NUL)

### 3. ต้นตอการหลุดและต่อ Wi-Fi ใหม่ที่พบใน Syslog:
* ใน Log ปรากฏข้อความ:
  ```text
  aircom[813]: dact: Disconnected for 3638 seconds, 82762 seconds before IR Action
  aircom[813]: wireless: reloading wifi
  wpa_supplicant: wlan0: CTRL-EVENT-DISCONNECTED
  wpa_supplicant: wlan0: Associated with 6e:ff:7b:c7:53:1f (SSID='TG39')
  wpa_supplicant: wlan0: WPA: Key negotiation completed
  aircom[813]: wireless: warning - AP scan error
  ```
* ยืนยันชัดเจนว่า **โปรเซส `aircom` ในเครื่องเองเป็นตัวสั่งรีโหลด Wi-Fi (`reloading wifi`)** เมื่อตรวจพบว่าการเชื่อมต่อคลาวด์ขาดหายไปนาน (Disconnected timer เกินขีดจำกัด) ส่งผลให้ DHCP ขอ IP ใหม่อยู่เป็นระยะ

---

## 14. การค้นพบ Cloud Endpoint ลับ (`connect.smartambi.com:8867`) & ระบบ Real-time Log Streaming

### 1. Endpoint คลาวด์ที่แท้จริงของตัวเครื่อง:
* **Host Domain:** `connect.smartambi.com`
* **Target Port:** **`8867`** (TCP)
* **ข้อความจาก Syslog:**
  ```text
  cloudc: cloud client open socket to server connect.smartambi.com:8867 (try 3/3)
  sockGen: gethostbyname connect.smartambi.com
  cloudc: cloud client connection in progress to server connect.smartambi.com:8867
  ```
* **การแก้ไข:** เพิ่ม `smartambi.com` ใน Fake DNS และสร้าง Mock Cloud Listener บน Port 8867 ใน `ambi_hub.py` และสคริปต์ `sniff_cloud_8867.py`

### 2. เครื่องมือ Real-time Log Monitoring (แบบ `tail -f`):
* สร้างสคริปต์ [`tail_ambi_log.py`](file:///c:/Users/maneepon/Documents/Projects/Ambi%20Climate/tail_ambi_log.py) และ [`tail_ambi_log.bat`](file:///c:/Users/maneepon/Documents/Projects/Ambi%20Climate/tail_ambi_log.bat)
* **กลไกการทำงาน:** เชื่อมต่อ TCP Port 8070 ค้างไว้ (Persistent Socket), Polling คำสั่ง `NSL` ทุก 1.5 วินาที, มีระบบ Deduplicate และสตรีมเฉพาะบรรทัดใหม่ที่เพิ่งเกิดขึ้นพร้อมระบบใส่สี (ANSI Colors) แยกตามประเภท Daemon ทันที

---

## 15. ค้นพบและปลดบล็อกปัญหา DNS-Rebind Attack ใน OpenWrt ของ Ambi

### 1. สาเหตุที่เครื่องไม่ยอมเชื่อมต่อ Cloud แม้ Fake DNS ตอบกลับแล้ว:
จากการวิเคราะห์ Syslog ภายในตัวเครื่อง Ambi พบบรรทัดสำคัญ:
```text
daemon.warn dnsmasq[1082]: possible DNS-rebind attack detected: connect.smartambi.com
local1.notice aircom[813]: sockGen: gethostbyname failed
local1.notice aircom[813]: sockGen: unknown host name errno is: 32 h_errno is: 1
local1.notice aircom[813]: cloudc: cloud sock error(32) herror (1)
```
* **สาเหตุเชิงลึก:** ตัวเครื่อง Ambi Climate รัน `dnsmasq` บน OpenWrt โดยเปิดระบบความปลอดภัย **DNS Rebind Protection (`--stop-dns-rebind`)** ไว้
* เมื่อ Fake DNS หลอกชี้ชื่อโดเมนสาธารณะ (`connect.smartambi.com`, `connect.ambiclimate.com`) ไปที่ไอพี Private เครือข่ายภายในบ้าน (RFC 1918 เช่น `192.168.1.138`)
* `dnsmasq` ของ Ambi จะถือว่าเป็นพฤติกรรมหลอกลวงแบบ DNS-Rebind และ **ตัดผลลัพธ์ DNS ทิ้งทันที** ทำให้โปรเซส `aircom` หาไอพีของเซิร์ฟเวอร์ไม่เจอและเชื่อมต่อไม่สำเร็จ

---

## 16. ทะลุข้อจำกัด DNS Rebind ด้วย Router Port Forwarding & CGNAT WAN IP

เพื่อแก้ปัญหา DNS Rebind โดยไม่ต้องไปเจาะแก้ไขคอนฟิกไฟล์ใน OpenWrt ของเครื่อง:

### 1. การตั้งค่า Port Forwarding บนเราเตอร์บ้าน (ONT Gateway):
* **ผู้ใช้ได้ตั้งค่า Port Forwarding บนเราเตอร์สำเร็จ:**
  * **ชื่อ Rule:** `AmbiCloud`
  * **Protocol:** `TCP`
  * **WAN Port:** `8866 ~ 8867`
  * **LAN Host:** `192.168.1.138` (เครื่อง Host PC)
  * **LAN Host Port:** `8866 ~ 8867`

### 2. ปรับ DNS ให้ชี้ไปที่ WAN IP ของเราเตอร์ (`100.112.62.200`):
* WAN IP ของเราเตอร์คือ `100.112.62.200` ซึ่งอยู่ในช่วง **Carrier-Grade NAT (RFC 6598 - Shared Address Space)** ไม่ถือว่าเป็น Private IP ตาม RFC 1918
* ตัว `dnsmasq` ของ Ambi จึง **ยอมรับผลลัพธ์ DNS 100%** โดยไม่มีการแจ้งเตือน DNS Rebind อีกต่อไป
* เมื่อเครื่อง Ambi ยิง Connection ออกไปหา `100.112.62.200:8866` หรือ `8867` เราเตอร์จะทำ **NAT Loopback (Hairpinning)** และส่งต่อแพ็กเก็ตมาให้เซิร์ฟเวอร์บนคอมพิวเตอร์ `192.168.1.138` ได้อย่างสมบูรณ์แบบ!

---

## 17. บันทึกผลการดักจับ Cloud Packet ของจริง (Capture & Packet Dissection)

เมื่อวันที่ 3 พฤศจิกายน 2569 เวลาประมาณ 12:16 - 12:23 น. เครื่อง Ambi Climate ได้ยิงคำขอเชื่อมต่อเข้ามายัง Cloud Mock Server สำเร็จเป็นครั้งแรก!

### 1. แผนที่ Cloud Endpoints ที่ตัวเครื่องใช้ติดต่อจริง:
| โดเมนเป้าหมาย | พอร์ต | รูปแบบโปรโตคอล | แพ็กเก็ตแรกที่เครื่องส่งมา |
| :--- | :--- | :--- | :--- |
| `connect.ambiclimate.com` | **`8866`** | **Plain TCP (Ambi Framing)** | `\x0701NPS\r\n` (8 ไบต์) |
| `connect.smartambi.com` | **`8867`** | **TLS 1.2 Encrypted** | `TLS Client Hello` (258 ไบต์) |
| `connect.ambiclimate.com` | **`8867`** | **TLS 1.2 Encrypted** | `TLS Client Hello` (258 ไบต์) |

### 2. รายละเอียดแพ็กเก็ต Port 8866 (Plain TCP):
* **Hex:** `07 30 31 4e 50 53 0d 0a`
* **ASCII:** `\x07 0 1 N P S \r \n`
* **การถอดรหัสโครงสร้าง:**
  * `0x07` = Start of Frame (BEL)
  * `01` = Sequence / Message ID
  * `NPS` = คำสั่ง **Network Provisioning / Pair / Push Status**
  * `\r\n` = End of Frame

### 3. รายละเอียดแพ็กเก็ต Port 8867 (TLS 1.2 Client Hello):
* **ขนาด:** 258 ไบต์
* **Hex ตัวอย่าง:** `16 03 01 00 fd 01 00 00 f9 03 03 ...`
* **Cipher Suites ที่เครื่องรองรับ:**
  * `TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384`
  * `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256`
  * `TLS_RSA_WITH_AES_256_GCM_SHA384`
  * `TLS_RSA_WITH_AES_128_GCM_SHA256`

---

## 18. อัปเดต Cloud Mock Server ใน `ambi_hub.py`

ได้ทำการพัฒนาฟังก์ชัน `run_cloud_mock(port)` ใน [`ambi_hub.py`](file:///c:/Users/maneepon/Documents/Projects/Ambi%20Climate/ambi_hub.py):
1. **ดักฟังพร้อมกันทั้ง 2 พอร์ต:** TCP `8866` และ TCP `8867`
2. **ระบบตรวจจับ TLS อัตโนมัติ (Auto-TLS Handshake Wrapper):**
   * ใช้ `socket.MSG_PEEK` ตรวจสอบ 2 ไบต์แรกของแพ็กเก็ต
   * หากพบ `\x16\x03` (TLS Client Hello) จะทำการ Wrap Socket ด้วย `ssl.SSLContext` ทันทีโดยใช้ `server_cert.pem` และ `server_key.pem`
3. **ระบบ Auto-Discovery Guard:**
   * ป้องกันบั๊กที่การเชื่อมต่อผ่าน NAT Loopback มี Source IP เป็น `100.112.62.200` แล้วทำให้ `AMBI_IP` ผิดเพี้ยน โดยระบบจะกรองและคงค่า IP จริงของ Ambi (`192.168.1.136`) ไว้เสมอ

---

## 19. ข้อสังเกตสถาปัตยกรรมภายใน: ทำไมไฟหน้าเครื่องยังไม่เป็นสีเขียว (Why LED is Not Green Yet)

จากการเจาะลึก Syslog ของ `aircom[813]` เปรียบเทียบกับคำสั่งที่ส่ง:

### 1. กลไกการทำงานของไฟ LED:
* ไฟ LED ควบคุมโดยชิป **Slave MCU** ไม่ใช่ตัว Linux Host โดยตรง
* ทุกๆ 5 วินาที โปรเซส `aircom` จะส่งสถานะเครือข่ายไปยัง Slave MCU:
  * ถ้าคลาวด์ยังต่อไม่ติด: Slave MCU จะตอบกลับ `000981NCO` (`devcmdres: Error (1NCO)`) และสั่งตั้งไฟเป็น **กะพริบส้ม (Offline Amber)**
  * ถ้าคลาวด์ต่อติดสมบูรณ์: `aircom` จะส่งคำสั่งไปตั้งค่าไฟ `000980NLD` (`devcmdres: LED set`) และ `000980NHS` เพื่อเปลี่ยนสถานะเป็น **ไฟเขียวนิ่ง (Solid Green)**

### 2. สาเหตุที่ตอบกลับแล้วไฟยังไม่เขียว:
1. **คำสั่ง `NPS` บน Port 8866 ต้องการ Response เฉพาะ:**
   * เมื่อ Ambi ส่ง `\x0701NPS\r\n` ตัวเซิร์ฟเวอร์เดิมตอบ `\x07010ACK\r\n` ซึ่งคำว่า `ACK` ไม่มีในพจนานุกรมคำสั่งของ `aircom`
   * ตามมาตรฐานโปรโตคอล Ambi เมื่อส่งคำสั่งอะไรมา การตอบกลับต้องสะท้อนชื่อคำสั่งนั้นกลับไป เช่น `\x07010NPS0\r\n` (Seq=`01`, Status=`0`=OK, Command=`NPS`, Value=`0`) หรือ `\x07010NPS\r\n`
2. **เครื่องเชื่อมต่อทั้ง 8866 และ 8867 สลับกันตามลำดับ Watchdog:**
   * เมื่อ `run_hub.bat` ได้รับการรีสตาร์ตพร้อมโค้ด Auto-TLS และ Response ตรงฟอร์แมต ทั้งสองพอร์ตจะ Handshake ผ่านสมบูรณ์ และทำให้ `aircom` เปลี่ยนสถานะเป็น Connected ทันที

---

## 20. ปรับแต่ง `ambi_hub.py` ให้สะอาด โฟกัสเฉพาะ Mock Server 8866/8867 และขยายการตรวจจับ Domain

### 1. ปัญหา Log รกจาก Raw TCP Sniffer:
* เดิมทีมี Thread `run_raw_sniffer` ดักจับ Raw IP Socket ของ Windows ทำให้เกิดบรรทัด `[RAW TCP] 192.168.1.136:8070 -> ...` ฟลัดหน้าจอทุกวินาทีจากการ Poll เซ็นเซอร์
* มี Generic Sniffer ดักพอร์ต 1883, 8883, 8000, 8001, 8443, 8070, 9001 ที่ไม่ได้ใช้งาน

### 2. สิ่งที่ปรับปรุงและทำไปแล้ว:
1. **ตัด Raw TCP Sniffer และ Generic Sniffer ออก:** หน้าจอ Console และไฟล์ `hub_activity.log` จะไม่โดนฟลัดอีกต่อไป
2. **โฟกัสเฉพาะ Mock Server พอร์ต 8866 และ 8867:**
   * พอร์ต 8866 (Plain TCP): ดักจับ `\x07[seq]CMD\r\n` ตอบกลับด้วย Native Protocol Response (`\x07[seq]0CMD0\r\n` และ `0NPS1`)
   * พอร์ต 8867 (TLS 1.2): ตรวจจับ `\x16\x03` ทำ SSL Handshake อัตโนมัติ
   * หากได้รับข้อมูลขนาดใหญ่ (> 300 ไบต์ เช่น System Log ดัมป์) จะถูกบันทึกแยกเก็บไว้ใน `cloud_dump.log` เพื่อรักษาความสะอาดของหน้าจอ
3. **ขยายรายการ Target Domains ที่ดักจับ:**
   * `ambiclimate.com` (รวมถึง `connect.`, `api.`, `ota.`, `origin-api.`)
   * `smartambi.com` (รวมถึง `connect.`, `api.`)
   * `ambiapis.com`
   * `tryambi.com`
   * `tryambiapis.com`
   * `amazonaws.com` (AWS IoT, API Gateway, S3)
   * `cloudfront.net` (AWS CDN)
   * `globalcache.com` (iTach Global Caché)
4. **เพิ่มระบบ DNS Live Inspection:**
   * หากเครื่อง Ambi Climate (`192.168.1.136`) ร้องขอ DNS โดเมนอื่นที่อยู่นอกเหนือจากรายการ (เช่น `pool.ntp.org` หรือบริการอื่นๆ) ระบบจะแสดงข้อความ `[DNS FORWARD 🌐] <domain> from Ambi -> Forwarded to 8.8.8.8` ทันที ทำให้เรามองเห็นและไม่พลาดทุก Domain ที่ตัวเครื่องเรียกหา

## 21. พัฒนาระบบ Hybrid Local Comfort AI (Auto-Tuning แอร์ Daikin) สำเร็จครบทุกเฟส

ตามที่ผู้ใช้ได้อนุมัติแผนงาน [hybrid_comfort_ai_plan.md](file:///C:/Users/maneepon/.gemini/antigravity/brain/0470c9b8-2482-4148-83e6-fb62b2440bea/hybrid_comfort_ai_plan.md) เราได้ทำการพัฒนาและผนวกระบบ Local AI เข้าสู่ [ambi_hub.py](file:///c:/Users/maneepon/Documents/Projects/Ambi%20Climate/ambiclimate/ambi_hub.py) สำเร็จครบถ้วน 4 เฟส

---

## 22. ย้ายพื้นที่พัฒนาหลักสู่โฟลเดอร์ Git Repository: `ambiclimate/` (จดบันทึกเป็นกฎถาวร)

* **กฎสำคัญ (Project Rule):** **นับจากนี้เป็นต้นไป การพัฒนา แก้ไข ทดสอบ และ Commit โค้ดทั้งหมดจะกระทำภายในโฟลเดอร์ [`ambiclimate/`](file:///c:/Users/maneepon/Documents/Projects/Ambi%20Climate/ambiclimate) นี้เท่านั้น**
* **Repository:** `https://github.com/Weerawit/ambiclimate.git`
* **โครงสร้าง:** แยกไฟล์ Source Code, Dockerfile, และ CI/CD ออกจากไฟล์ขยะ/APK ดิบขนาด 240MB ในโฟลเดอร์วิจัยภายนอก เพื่อให้ Git มีขนาดเบาและรองรับ Auto Deploy ได้อย่างสมบูรณ์แบบ
:

### 1. Phase 1: สมองคำนวณสภาวะความสบายสด (Canadian Humidex Engine)
* **สูตรฟิสิกส์ Humidex:** คำนวณความรู้สึกจริง (Feels-Like Temperature) จากอุณหภูมิห้อง $T$ และความชื้นสัมพัทธ์ $RH$:
  $$v = 6.112 \times 10^{\left(\frac{7.5 \times T}{237.7 + T}\right)} \times \frac{RH}{100}, \quad \text{Humidex} = T + \frac{5}{9} \times (v - 10)$$
* **Comfort Index Scale (-3 ถึง +3):**
  * เทียบกับจุดสบายฐาน $26.0^\circ\text{C}$ Humidex (พร้อมค่าชดเชยความชอบส่วนบุคคล `user_offset`)
  * แบ่งเป็น 7 ระดับสี: `หนาวมาก (Freezing)`, `หนาวเกินไป (Too Cold)`, `เริ่มเย็น (Cool)`, `กำลังสบาย (Comfortable)`, `เริ่มอุ่น (Warm)`, `ร้อนเกินไป (Too Warm)`, `ร้อนมาก (Hot)`

### 2. Phase 2: ระบบจดจำความชอบและการสอน AI (Personal Preference Learning)
* จัดเก็บข้อมูลลงไฟล์ [user_comfort_profile.json](file:///c:/Users/maneepon/Documents/Projects/Ambi%20Climate/user_comfort_profile.json) แบบเรียลไทม์:
  * `user_offset`: ค่าความขี้หนาว/ขี้ร้อนของผู้ใช้ (เริ่มต้นที่ `0.0°C`)
  * `auto_tune_enabled`: สวิตช์เปิด/ปิดการปรับจูนอัตโนมัติ
  * `min_temp` (22°C) และ `max_temp` (27°C) เพื่อความปลอดภัย
  * `cooldown_minutes` (10 นาที) ป้องกันแอร์ตัด-ต่อบ่อยเกินไป
  * `history`: บันทึกประวัติการปรับจูนและการกด Feedback ย้อนหลัง 25 รายการ
* **ปุ่มสอน AI (Interactive Teaching):**
  * **หนาวไป (Too Cold):** ปรับ `user_offset += 0.5` และสั่งแอร์ขึ้นทันที +1°C หรือลดพัดลม
  * **สบายดี (Comfortable):** บันทึกสภาพอากาศห้องปัจจุบันเป็นจุดเป้าหมายความสบาย
  * **ร้อนไป (Too Warm):** ปรับ `user_offset -= 0.5` และสั่งแอร์ลงทันที -1°C หรือเพิ่มพัดลม

### 3. Phase 3: กลไก Auto-Tuning แอร์จริง (Daikin IR Actuator บนพอร์ต 4998)
* เพิ่ม Background Thread `auto_tuning_worker()` ทำงานทุก 30 วินาที:
  * **Deadband Safety Zone:** สภาวะความสบายอยู่ในช่วง `-0.8 ถึง +0.8` ถือว่ากำลังสบาย และจะไม่สั่งแอร์
  * **Spike Noise Filtering:** สภาพอากาศต้องหลุดโซนติดต่อกัน 2 รอบเพื่อป้องกันความผิดพลาดชั่วคราว
  * **Cooldown Protection:** ระบบจะพัก 10 นาทีหลังจากสั่งแอร์แต่ละครั้ง เพื่อให้ลมเย็นกระจายตัวเต็มที่
  * **Daikin Transmission:** ยิงสัญญาณ Protocol B (216-bit) ควบคุมอุณหภูมิ, ความแรงลม (Auto, Quiet, Low, Med, High), และเปิด/ปิด

### 4. Phase 4: หน้าจอ Web Dashboard v2 ใหม่ล่าสุด (`http://localhost:8080`)
* พัฒนา Web Dashboard แบบโมเดิร์น (Slate & Emerald Dark Theme) รองรับทั้งสมาร์ทโฟนและคอมพิวเตอร์:
  * แสดงอุณหภูมิห้อง, ความชื้น, และความรู้สึกจริง (Humidex)
  * แถบป้ายสถานะความสบายเปลี่ยนสีสดตามคะแนน
  * สวิตช์เปิด/ปิด Auto-Tuning พร้อมแสดงเวลานับถอยหลัง Cooldown (เช่น `⏳ พักรออุณหภูมิกระจาย อีก 7 น. 15 วิ`)
  * 3 ปุ่มฟีดแบ็กขนาดใหญ่สำหรับสอน AI (`หนาวไป`, `สบายดี`, `ร้อนไป`)
  * แผงรีโมทแอร์ Daikin เต็มรูปแบบ (+/- อุณหภูมิ, พัดลม 5 ระดับ, ปุ่มปิดแอร์)
  * ตารางประวัติการทำงานของ AI และ Feedback ย้อนหลัง
  * ทำงานแบบ Asynchronous (AJAX fetch `/api/state`) ทุก 3 วินาที ลื่นไหลโดยไม่ต้อง Refresh หน้าเว็บ

---

## 24. การวินิจฉัยและแก้ไขข้อผิดพลาดใน Log (Error Diagnosis & Hardening)

จากการตรวจสอบไฟล์ `hub_activity.log` และ `ambi_system_dump.log`:

### สาเหตุของ Errors ที่พบ:
1. **`TypeError: str, bytes or bytearray expected, not NoneType`**:
   * **สาเหตุ:** ในขั้นตอนเริ่มต้น `AMBI_IP` มีค่าเป็น `None` จนกว่าเครื่อง Ambi จะส่ง DNS Query เข้ามา หากเปิด Web Dashboard หรือกดปุ่ม Console `[1]`, `[5]`, `[L]` ระบบจะพยายาม `socket.connect((None, 8070))` ส่งผลให้เกิด TypeError
   * **การแก้ไข:** เพิ่ม Guard Clause `if not ip: return None` ในทุกฟังก์ชันคำสั่ง (`send_ambi_cmd`, `get_cloud_server_setting`, `change_cloud_server`, `fetch_ambi_system_log`, `send_daikin_ir`) ป้องกันการ Crash โดยเด็ดขาด
2. **`HTTP/S :80 - code 400, message Bad request version`**:
   * **สาเหตุ:** มีการส่ง TLS Client Hello เข้ามายัง HTTP Port 80 (Plain HTTP) ทำให้ `BaseHTTPRequestHandler` ไม่สามารถ Parse เวอร์ชัน HTTP ได้
   * **การแก้ไข:** เพิ่ม Peek ตรวจจับ TLS (`0x16`) และตัดการเชื่อมต่อทันที พร้อมกรอง Error 400 ไม่ให้พ่นข้อความรกใน Log
3. **`Error fetching system log: timed out` และ `No log data returned from device`**:
   * **สาเหตุ:** เกิดความขัดแย้งของ Socket Port 8070 เมื่อ `poll_live_sensors` และ `fetch_ambi_system_log` พยายามเชื่อมต่อ Port 8070 พร้อมกันบนตัว Ambi ที่เป็น Single-Connection
   * **การแก้ไข:**
     * เพิ่ม Thread Lock `AMBI_PORT_8070_LOCK = threading.Lock()` ป้องกันการแย่งใช้งานพอร์ต 8070
     * ขยาย Timeout ของคำสั่งดึง Log (NSL) เป็น 7.0 วินาที พร้อม Buffer Loop ที่เสถียร
     * เพิ่ม `finally: s.close()` ใน `test_daikin.py` ป้องกัน Socket ค้าง
4. **DNS Redirection & Cloud Targeting**:
   * ปรับ DNS Redirection ชี้มาที่ `HOST_IP` (`192.168.1.138`) โดยตรงสำหรับโดเมน Ambi ทุกโดเมน

---

## 25. ปิด Active Polling และเปิดระบบ Passive Push + สั่งไฟเขียว (Solid Green) อัตโนมัติ

### 1. ปิด Active Sensor Poller:
* ปิด Thread `poll_live_sensors` จากการยิงพอร์ต 8070 ทุก 20 วินาที เพื่อไม่ให้ไปแย่ง Socket และรอรับข้อมูลที่ Ambi Push เข้ามาเอง
* เพิ่มตัวตรวจจับ Telemetry Push ทั้งบน Cloud Mock (TCP 8866 / TLS 8867) และ HTTP POST/PUT

### 2. ระบบสั่งไฟเขียว (Solid Green) ทันทีที่ได้ IP:
* พัฒนาฟังก์ชัน `set_ambi_led_green(target_ip)` ใน `ambi_hub.py`:
  * ส่ง `\x0700NSD\r` (Setup Done)
  * ส่ง `\x0700NCD1\r` (Stop Offline Blink Loop)
  * ส่ง `\x0700NLL1 5730\r` (Enable PWM Brightness)
  * ส่ง `\x0700NLD00\r` + `NLD19\r` + `NLD20\r` (Red OFF, Green ON Level 9, Blue OFF)
* เชื่อมโยงให้ยิงทันทีที่:
  1. ล็อค IP จาก DNS สำเร็จ
  2. กดปุ่ม `[6]` หรือ `[G]` ใน Console CLI (พร้อมระบบ Fallback IP `192.168.1.156`)
  3. กดปุ่มสีเขียว `🟢 สั่งไฟหน้าเครื่องเป็นสีเขียว (Solid Green)` บน Web Dashboard
* **ผลการทดสอบจริง:** ยิงคำสั่งสำเร็จ 100% ตัวเครื่องตอบรับและไฟหน้าเครื่องเปลี่ยนเป็น **สีเขียวนิ่ง (Solid Green)** เรียบร้อย!

---

## 26. การวิเคราะห์ความคงอยู่ (Persistence) ของ Cloud IP และเหตุผลที่เครื่องยังต่อ smartambi

### 1. การเปลี่ยน Cloud IP จะ Permanent (ถาวร) หรือไม่?
* **คำตอบ: ไม่ถาวรในระดับฮาร์ดแวร์ (Non-Persistent Across Reboot)**
* **เหตุผลทางสถาปัตยกรรม:**
  1. ตัวเครื่อง Ambi Climate รันระบบปฏิบัติการ Linux OpenWrt บนชิป MIPS โดยมี Flash ROM แบบ Read-Only (`SquashFS`) สำหรับไฟล์ระบบหลัก
  2. โดเมนหลักสำหรับเชื่อมต่อคลาวด์ (`connect.smartambi.com` และ `connect.ambiclimate.com`) เป็นค่า **Factory Hardcoded Defaults** ภายในไบนารี `aircom`
  3. คำสั่งผ่านพอร์ต 8070 (เช่น `NCA`, `NCE`, `NCD`) เป็นการปรับแต่งค่าใน **RAM Runtime Memory** ของโพรเซส `aircom` เท่านั้น
  4. เมื่อเครื่อง Ambi ถูกดึงปลั๊กไฟออก หรือรีบูต ค่าคอนฟิกใน RAM จะถูกรีเซ็ตกลับเป็น Factory Defaults ทันที

### 2. ทำไมเมื่อส่งคำสั่งเปลี่ยน Cloud แล้ว ตัวเครื่องยังพยายามวิ่งไปหา `connect.smartambi.com`?
จากการวิเคราะห์เชิงลึกผ่าน System Log Dump (`ambi_system_dump.log`) พบข้อเท็จจริงสำคัญ 3 ประการ:
1. **คำสั่ง `NCE` ถูก Reject ด้วย Error Code 2 (Invalid Parameter):**
   * บันทึกใน Syslog:
     ```text
     aircom[813]: devparse: 01NCE192.168.1.138:8867
     aircom[813]: devparse: command type CE -> devs: Cloud Envrionment
     aircom[813]: devcmdres: Error (status 2: Invalid Parameter)
     ```
   * ตัวเครื่องตอบกลับมาว่า `\x07012NCE` โดยเลข `2` คือรหัสข้อผิดพลาด เพราะคำสั่ง `NCE` ย่อมาจาก **Cloud Environment** (รับค่า Environment เช่น dev/staging/prod หรือโหมดตัวเลข) ไม่ได้สร้างมาสำหรับรับ IP Address
   * คำสั่งที่ใช้สำหรับ Override Server Address จริงๆ ตามโค้ด `aircom` คือ **`NCA` (Cloud Server Address Override)**
   * ผลลัพธ์: การส่ง `NCE192.168.1.138:8867` จึงไม่ถูกนำไปบันทึกเป็นที่อยู่เซิร์ฟเวอร์
2. **การส่ง `NCD` บังคับให้ `aircom` Reconnect กลับไปหา Factory Domain:**
   * เมื่อค่า Server Address ใหม่ไม่ถูกตั้งค่า พอคำสั่ง `NCD` ถูกส่งไป โพรเซส `aircom` จึงตัดการเชื่อมต่อเดิมแล้วเปิด Socket เชื่อมต่อไปยัง Default Server ทันที:
     ```text
     aircom[813]: cloudc: cloud client open socket to server connect.smartambi.com:8867
     aircom[813]: sockGen: gethostbyname connect.smartambi.com
     ```
3. **ระบบป้องกัน DNS-Rebind Attack ของตัวเครื่อง (`dnsmasq`):**
   * ในตัว Ambi รัน `dnsmasq` ซึ่งเปิดออปชัน `--stop-dns-rebind` ไว้
   * เมื่อ Fake DNS ส่ง IP วง Local (`192.168.1.138`) กลับไปเป็นคำตอบของโดเมนสาธารณะ `dnsmasq` ของ Ambi จะทิ้งคำตอบนั้นเป็นบางครั้ง

### 3. สถาปัตยกรรม Local Hub ถาวร 100% (Permanent Bulletproof Architecture):
* ด้วยเหตุนี้ เราจึง**ไม่จำเป็นต้องและไม่ควรแก้ไข Flash ROM ของ Ambi** (เพื่อป้องกันความเสี่ยงฮาร์ดแวร์เสียหาย)
* แต่ใช้สถาปัตยกรรม **Auto-Catch & Auto-Restore แบบอัตโนมัติบน Local Hub**:
  1. **DNS Interception (Port 53):** ดักจับชื่อโดเมน `connect.*` ทันทีที่ Ambi เปิดเครื่อง
  2. **Instant Green LED Activation:** ทันทีที่ล็อก IP Ambi ได้ Hub จะยิงชุดคำสั่งหยุดไฟส้มและเปิดไฟเขียวนิ่ง (Solid Green) อัตโนมัติในระดับมิลลิวินาที
  3. **Mock Cloud Listener (Port 8866 & 8867):** รองรับแพ็กเก็ต Push จากตัวเครื่อง
  4. **IR Appliance Controller (Port 4998):** ควบคุมแอร์ Daikin ได้ตลอดเวลาแบบ 100% Offline
* **สรุป:** ไม่ว่าผู้ใช้จะถอดปลั๊ก ย้ายห้อง หรือไฟดับ เมื่อเสียบปลั๊ก Ambi ใหม่ Ambi จะถูก Local Hub ปรับเป็นไฟเขียวและพร้อมใช้งานได้ทันทีโดยไม่ต้องตั้งค่าใดๆ เพิ่มเติมทั้งสิ้น

---

## 27. เพิ่มระบบ Solid Green LED Keep-Alive Watchdog

### 1. ความจำเป็นในการมี Keep-Alive:
* ภายในตัวเครื่อง Ambi daemon `aircom` มี watchdog คอยส่งคำสั่ง `1NCO` ทุกๆ 5 วินาที
* หากตรวจพบว่าคลาวด์ไม่ได้เชื่อมต่อเป็นเวลานาน ชิป Slave MCU อาจรีเซ็ตสถานะของหลอดไฟกลับไปกะพริบสีส้ม (Offline Amber Blink) ตามรอบการทำงาน
* เพื่อให้ไฟหน้าเครื่องคงสถานะ **สีเขียวนิ่ง (Solid Green)** ตลอด 24 ชั่วโมง จึงเพิ่ม background worker ที่ทำงานแบบอัตโนมัติ

### 2. การทำงานของ `led_keepalive_worker`:
* ทำงานเป็น Background Daemon Thread ทุกๆ 120 วินาที
* ตรวจสอบว่าเครื่อง Ambi ได้รับการล็อก IP และพร้อมทำงานแล้ว (`AMBI_READY_EVENT.is_set()`)
* ทำงานภายใต้ `AMBI_PORT_8070_LOCK` เพื่อความปลอดภัย ไม่ให้เกิดการชนกันของ socket
* ยิงคำสั่ง `set_ambi_led_green()` ย้ำการปิด offline blink loop และคงค่า PWM สีเขียว (`NLD19`) อย่างต่อเนื่อง ทำให้ไฟหน้าเครื่องไม่กลับไปกะพริบสีส้มอีกเลย

---

## 29. ปรับปรุง Web UI ให้ตรงตามคู่มือ Ambi Climate App (User Manual) และเพิ่มฟังก์ชันควบคุมไฟ LED / ปุ่ม Query เซ็นเซอร์

### 1. การถอดแบบ UI จากคู่มือทางการ (`ambi - manual.pdf` หน้า 10, 11, 14, 15):
ถอดแบบดีไซน์ของหน้าจอควบคุมหลักจากคู่มือผู้ใช้งาน Ambi Climate App มาสร้างเป็น **`web_dashboard.html`** อย่างสมบูรณ์:
1. **Top Navigation Bar (หน้า 10):**
   * ชื่อห้อง `Living Room` พร้อมแท็กตำแหน่ง `Home • Ambi Climate 2`
   * แถบแสดงสภาพอากาศจริงของห้อง (Actual Conditions Bar): แสดงอุณหภูมิห้อง `🌡️ XX°C`, ความชื้น `💧 XX%`, และแถบสถานะความสบาย (Comfort Pill เช่น `comfortable`, `too cold`, `too warm`)
   * ปุ่มรีเฟรชด่วน `🔄` (Instant Refresh) ที่มุมขวาบน สำหรับกด Query เซ็นเซอร์สดจากตัวเครื่องได้ทันที
2. **กราฟเส้นแสดงแนวโน้มสภาพอากาศย้อนหลัง 4 ชั่วโมง (4-Hour Climate Curve - หน้า 10):**
   * แสดงค่าสูงสุด/ต่ำสุดของความชื้น (`H 57%`, `L 45%`)
   * เส้นกราฟ 2 ชั้น: เส้นสีฟ้าอมฟ้าอ่อน (Cyan) สำหรับความชื้น และเส้นสีส้มแดง (Coral) สำหรับอุณหภูมิห้อง พร้อมไทม์ไลน์ `4h`, `3h`, `2h`, `1h`, `Now`
3. **Hero Control - วงแหวนควบคุมความสบาย (Ambi Comfort Dial / Bubble - หน้า 10):**
   * วงแหวนฟองแก้วเรืองแสง (Glassmorphic Bubble) ปรับเปลี่ยนสีตามดัชนีความสบาย (Comfort Index / Humidex)
   * โหมด Comfort: แสดงสถานะการประเมินของ AI เช่น `comfortable`, `Feels 25°C`, และ `Target 26°C`
   * โหมด Temperature / Manual: แสดงตัวเลขอุณหภูมิเป้าหมายขนาดใหญ่ `24°C`
   * โหมด OFF: แสดงสถานะปิดแอร์
4. **Interactive AI Comfort Feedback Chips (หน้า 10):**
   * ชิปตัวเลือกสอน AI 5 ระดับ: `🥶 หนาวมาก`, `❄️ หนาวไป (+1°)`, `😊 สบายดี`, `🌤️ ร้อนไป (-1°)`, `🥵 ร้อนมาก` แตะเพื่อสอนโมเดล AI และปรับแอร์ Daikin ได้ทันที
5. **แถบเมนู 4 แท็บเอกลักษณ์ของ Ambi Climate (หน้า 10) พร้อม Bottom Drawers (หน้า 14):**
   * **[📊 Analytics]:** ประวัติการปรับจูนของ AI (History Table) และข้อมูลเชิงลึก
   * **[🎚️ AC Settings]:** ถอดแบบหน้าจอตั้งค่าแอร์ตามหน้า 14 ของคู่มือ มีแถบปรับความเร็วพัดลม (Fan: Quiet, Low, Med, High, Auto), บานสวิง (Louver / Swing: Off, Down, Mid, Up, Auto), ตัวปรับอุณหภูมิ Stepper, และปุ่มเปิด/ปิดแอร์
   * **[📱 Device]:** หน้าตั้งค่าตัวเครื่อง Ambi Climate 2:
     * **เมนูสไลเดอร์ปรับความสว่างหลอดไฟ LED หน้าเครื่อง (PWM 0-10000)** พร้อมปุ่มทางลัด 4 ระดับ: `🌑 ปิดไฟ (0%)`, `🌙 หรี่ (25%)`, `🟢 ปกติ (57%)`, `☀️ สว่างสุด (100%)` และปุ่ม `🟢 ยืนยันไฟเขียว (Solid Green)`
     * **ปุ่ม Query อุณหภูมิและความชื้นสดจาก Ambi (:8070)** ตามคำขอ
     * เมนูสลับ Cloud Server (NCE / NCD) และตัวเปิดดู System Dump Log (NSL)
   * **[⚡ Modes]:** หน้าสลับโหมด 5 โหมดหลักตามหน้า 11 ของคู่มือ:
     1. `Comfort Mode` (Local AI Auto-Tuning)
     2. `Temperature Mode` (คุมอุณหภูมิคงที่)
     3. `Manual Mode` (คุมรีโมทตรงไม่ผ่าน AI)
     4. `Away Mode` (ประหยัดพลังงานเมื่อไม่อยู่บ้าน)
     5. `OFF Mode` (ปิดแอร์)

### 2. การอัปเดต Backend API และ Console CLI:
* **เพิ่ม Endpoint `/api/mode`:** รองรับการสลับโหมด Comfort, Temperature, Manual, Away, Off ผ่าน HTTP GET
* **เพิ่ม Endpoint `/api/led/brightness`:** รองรับการปรับระดับ PWM แสงไฟ LED หน้าเครื่อง
* **เพิ่ม Endpoint `/api/sensors/query` (และ `/api/sensors/refresh`):** รองรับการ Query ค่าเซ็นเซอร์สดจาก Ambi Port 8070 เมื่อกดปุ่มบน Web UI
* **เพิ่มคำสั่ง Console CLI:**
  * `[5]` : อ่านค่าเซ็นเซอร์สดทันที (Manual Query NTP / NHM / NLU)
  * `[6]` : สั่งไฟ LED หน้าเครื่องเป็นสีเขียว (Solid Green)
  * `[7]` : ปรับความสว่างหลอดไฟ LED (0=OFF, 1000-10000)
  * `[P]` : สลับเปิด/ปิดการดึงเซนเซอร์อัตโนมัติ (Auto Pull Query ทุก 20 วิ)
  * `[M]` : สลับโหมด Ambi Climate (Comfort, Temperature, Manual, Away, Off)

---

## 30. นำระบบ Pull Query เซ็นเซอร์อัตโนมัติกลับมาทำงาน (Live Sensor Polling)

### 1. เหตุผลและความสำคัญ:
* การนำ Background Poller (Pull Query) กลับมาทำงานควบคู่กัน ทำให้ระบบมีข้อมูลสภาพอากาศห้องที่เป็นปัจจุบัน (Live Real-Time) ทุกๆ 20 วินาทีอย่างต่อเนื่อง ไม่ขาดช่วง
* การคำนวณ Humidex และการตัดสินใจปรับจูนแอร์ของ Local Comfort AI จะทำงานได้อย่างแม่นยำตลอดเวลา ไม่ต้องคอยข้อมูล Push เพียงอย่างเดียว

### 2. การปรับปรุงและการป้องกัน:
* **เปิดใช้งานเธรด `poll_live_sensors` ทุก 20 วินาที:** เริ่มทำงานอัตโนมัติเมื่อรัน `ambi_hub.py`
* **ระบบความปลอดภัย `AMBI_PORT_8070_LOCK`:** ป้องกันการแย่งใช้ Socket พอร์ต 8070 ระหว่างการดึงค่าเซ็นเซอร์กับการสั่งเปลี่ยนไฟ LED หรือการกด Query สด
* **เพิ่ม Endpoint `/api/sensors/polling`:** สามารถตรวจสอบสถานะ หรือสลับเปิด/ปิดการ Polling ได้อย่างยืดหยุ่น (`?enable=1` หรือ `0`)
* **เพิ่มปุ่มสลับ Auto Pull บน Web UI:** ในลิ้นชัก Device Settings มีป้ายสถานะ `🔄 Auto Pull: ON (20s)` ที่สามารถกดสลับเปิด/ปิดได้ทันที
* **เพิ่มคำสั่ง Console CLI `[P]`:** กด `P` บนหน้าต่างคอนโซลเพื่อสลับเปิด/ปิด Auto Polling ได้ทันที

---

## 31. ระบบตรวจจับเครือข่ายอัตโนมัติ (Network Auto-Detection) และการ Deploy Docker Server จาก Git

### 1. ระบบตรวจจับเครือข่ายอัตโนมัติ (Host IP, Gateway, Router WAN IP):
* **Host LAN IP (`detect_local_ip`):** ตรวจสอบ IP ของเครื่องเซิร์ฟเวอร์โดยอัตโนมัติผ่าน UDP socket routing probe (`8.8.8.8:80`) โดยไม่ต้องส่งแพ็กเก็ตออกนอกเครื่องจริง ทำให้ได้ Local IP จริงของ Host หรือคอนเทนเนอร์ในโหมด host
* **Router Gateway IP (`detect_gateway_ip`):** ตรวจหา Default Gateway ของเราเตอร์อัตโนมัติ:
  * บน Linux / Docker: อ่านจากตาราง `/proc/net/route` (Destination `00000000`) หรือคำสั่ง `ip route`
  * บน Windows: ตรวจสอบผ่าน `route print 0.0.0.0`
  * Fallback อัตโนมัติ: ดึง Subnet จาก Host IP แล้วเติม `.1` (เช่น `192.168.1.1`)
* **Router WAN IP (`detect_wan_ip`):** ตรวจจับ Public / CGNAT WAN IP ของเราเตอร์อัตโนมัติผ่าน Lightweight Web API (`api.ipify.org`, `ifconfig.me/ip`, `icanhazip.com`, `checkip.amazonaws.com`)
* **DNS Redirect Target IP (`DNS_REDIRECT_IP`):** เชื่อมโยงกับ `ROUTER_WAN_IP` อัตโนมัติ เพื่อป้องกันไม่ให้ฟังก์ชัน `--stop-dns-rebind` ของ OpenWrt / dnsmasq ปฏิเสธ DNS Redirect Response
* **Web UI & CLI:**
  * เพิ่มการ์ด **🌐 การเชื่อมต่อเครือข่าย (Auto Detected)** ในลิ้นชัก Device Settings บน Web Dashboard พร้อมปุ่ม `🔄 Auto Detect`
  * เพิ่มคำสั่ง `[N]` ใน Interactive Console CLI เพื่อสั่ง Refresh Network Settings ได้ตลอดเวลา
  * เพิ่ม Endpoint `/api/network/detect` สำหรับเรียกตรวจจับและอัปเดตแบบ Dynamic

### 2. การ Deploy บน Docker Server ผ่าน Git:
* เพิ่ม `.dockerignore` ป้องกันการ build ไฟล์ที่ไม่เกี่ยวข้อง
* อัปเดต `docker-compose.yml` ให้รองรับ `network_mode: "host"` สำหรับ Linux / Raspberry Pi เพื่อให้รับ DNS UDP 53 และ Beacon UDP 9131 ได้อย่างสมบูรณ์แบบ พร้อม fallback port mappings สำหรับสภาพแวดล้อมอื่นๆ
* สามารถ Clone จาก GitHub (`git clone https://github.com/Weerawit/ambiclimate.git`) และสั่ง `docker compose up -d --build` เพื่อรันได้ทันทีโดยไม่ต้องแก้ไขค่า IP ด้วยตนเอง









