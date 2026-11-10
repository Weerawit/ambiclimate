#!/usr/bin/env python3
"""
Ambi Climate Web Dashboard View
-------------------------------
Renders the authentic Ambi Climate responsive web dashboard.
"""

import os
from models.config import DASHBOARD_HTML_FILE

def get_dashboard_html():
    """Returns the authentic Ambi Climate App UI matching user manual, fallback to embedded HTML."""
    if os.path.exists(DASHBOARD_HTML_FILE):
        try:
            with open(DASHBOARD_HTML_FILE, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            pass
    return WEB_DASHBOARD_HTML

WEB_DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ambi Climate Local Hub - Daikin Comfort AI</title>
    <style>
        :root {
            --bg: #0f172a;
            --card-bg: #1e293b;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --border: #334155;
            --blue: #3b82f6;
            --green: #10b981;
            --amber: #f59e0b;
            --red: #ef4444;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        body { background: var(--bg); color: var(--text-main); padding: 16px; min-height: 100vh; display: flex; justify-content: center; }
        .container { width: 100%; max-width: 540px; margin: 0 auto; display: flex; flex-direction: column; gap: 16px; }
        
        .card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 16px; padding: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.3); }
        .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 14px; }
        .title { font-size: 18px; font-weight: 700; color: #fff; display: flex; align-items: center; gap: 8px; }
        .badge { padding: 4px 10px; border-radius: 20px; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
        .badge-live { background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4); }
        .badge-cooldown { background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.4); }
        
        /* Climate Grid */
        .metrics-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 16px 0; }
        .metric-box { background: rgba(255,255,255,0.03); border: 1px solid var(--border); border-radius: 12px; padding: 12px 8px; text-align: center; }
        .metric-label { font-size: 11px; color: var(--text-muted); margin-bottom: 4px; }
        .metric-val { font-size: 22px; font-weight: 700; color: #fff; }
        .metric-unit { font-size: 12px; color: var(--text-muted); font-weight: normal; }

        /* Comfort Banner */
        .comfort-banner { border-radius: 12px; padding: 14px; text-align: center; margin-bottom: 14px; transition: background 0.3s; }
        .comfort-score { font-size: 13px; font-weight: 600; margin-top: 4px; opacity: 0.9; }

        /* Auto-Tune Row */
        .autotune-row { display: flex; justify-content: space-between; align-items: center; background: rgba(255,255,255,0.02); padding: 12px 14px; border-radius: 12px; border: 1px solid var(--border); }
        .switch { position: relative; display: inline-block; width: 44px; height: 24px; }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #475569; transition: .3s; border-radius: 24px; }
        .slider:before { position: absolute; content: ""; height: 18px; width: 18px; left: 3px; bottom: 3px; background-color: white; transition: .3s; border-radius: 50%; }
        input:checked + .slider { background-color: var(--green); }
        input:checked + .slider:before { transform: translateX(20px); }

        /* Feedback Section */
        .feedback-title { font-size: 13px; font-weight: 600; color: var(--text-muted); margin-bottom: 10px; text-align: center; }
        .feedback-btns { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
        .btn-feed { border: none; border-radius: 12px; padding: 14px 8px; cursor: pointer; font-size: 13px; font-weight: 700; display: flex; flex-direction: column; align-items: center; gap: 6px; transition: transform 0.1s, opacity 0.2s; color: white; }
        .btn-feed:active { transform: scale(0.96); }
        .btn-feed:hover { opacity: 0.9; }
        .btn-cold { background: linear-gradient(135deg, #2563eb, #3b82f6); }
        .btn-comfy { background: linear-gradient(135deg, #059669, #10b981); }
        .btn-warm { background: linear-gradient(135deg, #d97706, #f59e0b); }
        .btn-sub { font-size: 10px; font-weight: normal; opacity: 0.85; }

        /* AC Control Card */
        .temp-display { font-size: 54px; font-weight: 800; color: var(--blue); text-align: center; margin: 10px 0; }
        .fan-row { display: flex; justify-content: center; gap: 6px; margin: 12px 0; flex-wrap: wrap; }
        .btn-fan { background: rgba(255,255,255,0.06); border: 1px solid var(--border); color: var(--text-muted); padding: 6px 12px; border-radius: 8px; font-size: 12px; font-weight: 600; cursor: pointer; }
        .btn-fan.active { background: var(--blue); color: white; border-color: var(--blue); }
        .btn-action { background: #334155; color: white; border: none; padding: 12px 20px; border-radius: 10px; font-size: 15px; font-weight: 600; cursor: pointer; }
        .btn-action:hover { background: #475569; }
        .btn-off { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); }
        .btn-off:hover { background: var(--red); color: white; }

        /* History Table */
        .history-list { font-size: 11px; color: var(--text-muted); display: flex; flex-direction: column; gap: 8px; max-height: 180px; overflow-y: auto; }
        .history-item { display: flex; justify-content: space-between; padding: 8px; background: rgba(255,255,255,0.02); border-radius: 6px; border: 1px solid rgba(255,255,255,0.04); }
        
        .toast { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); background: #1e293b; border: 1px solid #3b82f6; color: white; padding: 10px 20px; border-radius: 20px; font-size: 13px; font-weight: 600; opacity: 0; pointer-events: none; transition: opacity 0.3s; box-shadow: 0 4px 15px rgba(0,0,0,0.5); z-index: 99; }
        .toast.show { opacity: 1; }
    </style>
</head>
<body>
    <div class="container">
        <!-- Card 1: Header & Live Metrics -->
        <div class="card">
            <div class="header">
                <div class="title">
                    <span>❄️ Ambi Climate Local AI</span>
                </div>
                <span id="sensorBadge" class="badge badge-live">LIVE (Port 8070)</span>
            </div>

            <div class="metrics-grid">
                <div class="metric-box">
                    <div class="metric-label">อุณหภูมิห้อง</div>
                    <div class="metric-val"><span id="roomTemp">--</span><span class="metric-unit">°C</span></div>
                </div>
                <div class="metric-box">
                    <div class="metric-label">ความชื้น</div>
                    <div class="metric-val"><span id="roomHum">--</span><span class="metric-unit">%</span></div>
                </div>
                <div class="metric-box">
                    <div class="metric-label">ความรู้สึกจริง (Humidex)</div>
                    <div class="metric-val" style="color: #38bdf8;"><span id="roomFeels">--</span><span class="metric-unit">°C</span></div>
                </div>
            </div>

            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; padding: 0 4px;">
                <span id="sensorTimeText" style="font-size: 11px; color: var(--text-muted);">อัปเดตล่าสุด: --</span>
                <button class="btn-action" style="padding: 6px 14px; font-size: 12px; background: #0284c7; display: flex; align-items: center; gap: 4px;" onclick="querySensorsNow()">
                    🔄 อ่านค่าเซนเซอร์สด (Query)
                </button>
            </div>

            <!-- Comfort Badge -->
            <div id="comfortBanner" class="comfort-banner" style="background: rgba(16, 185, 129, 0.2); color: #34d399;">
                <div id="comfortLabel" style="font-size: 16px; font-weight: 700;">กำลังประมวลผล...</div>
                <div id="comfortScore" class="comfort-score">Comfort Index: 0.0</div>
            </div>

            <!-- Auto-Tune Row -->
            <div class="autotune-row">
                <div>
                    <div style="font-size: 13px; font-weight: 700;">🤖 Local AI Auto-Tuning</div>
                    <div id="cooldownText" style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">ตรวจเช็คทุก 30 วินาที</div>
                </div>
                <label class="switch">
                    <input type="checkbox" id="autotuneToggle" onchange="toggleAutoTune(this.checked)">
                    <span class="slider"></span>
                </label>
            </div>
        </div>

        <!-- Card 2: สอน AI (Interactive Feedback) -->
        <div class="card">
            <div class="feedback-title">🎯 ตอนนี้รู้สึกอย่างไร? (แตะเพื่อสอน AI ปรับจูนความชอบ)</div>
            <div class="feedback-btns">
                <button class="btn-feed btn-cold" onclick="sendFeedback('cold')">
                    <span>🥶 หนาวไป</span>
                    <span class="btn-sub">+1°C / ลมเบาลง</span>
                </button>
                <button class="btn-feed btn-comfy" onclick="sendFeedback('comfy')">
                    <span>😊 สบายดี</span>
                    <span class="btn-sub">จำสภาพนี้เป็นเป้าหมาย</span>
                </button>
                <button class="btn-feed btn-warm" onclick="sendFeedback('warm')">
                    <span>🥵 ร้อนไป</span>
                    <span class="btn-sub">-1°C / ลมแรงขึ้น</span>
                </button>
            </div>
            <div id="offsetDesc" style="text-align: center; font-size: 11px; color: var(--text-muted); margin-top: 10px;">
                ค่าชดเชยส่วนบุคคล: 0.0°C | เป้าหมาย Humidex: 26.0°C
            </div>
        </div>

        <!-- Card 3: Daikin Remote Control -->
        <div class="card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <span style="font-size: 14px; font-weight: 700; color: #fff;">📡 แอร์ Daikin (ARC480A46)</span>
                <div>
                    <span id="pendingBadge" style="display: none; background: rgba(245, 158, 11, 0.2); color: #fbbf24; font-size: 11px; padding: 3px 8px; border-radius: 6px; margin-right: 6px; font-weight: 600;">⏳ กำลังรอส่งคำสั่งซ้ำ</span>
                    <span id="powerBadge" class="badge" style="background: rgba(59, 130, 246, 0.2); color: #60a5fa;">COOL</span>
                </div>
            </div>

            <div class="temp-display" id="targetTemp">24°C</div>

            <div style="display: flex; justify-content: center; gap: 10px; margin-bottom: 14px;">
                <button class="btn-action" style="padding: 10px 24px;" onclick="adjustTemp(-1)">- 1°C</button>
                <button class="btn-action" style="padding: 10px 24px;" onclick="adjustTemp(+1)">+ 1°C</button>
            </div>

            <!-- Fan Speeds -->
            <div class="fan-row">
                <button class="btn-fan" id="fan-auto" onclick="setFan('Auto')">Auto</button>
                <button class="btn-fan" id="fan-quiet" onclick="setFan('Quiet')">Quiet</button>
                <button class="btn-fan" id="fan-low" onclick="setFan('Low')">Low</button>
                <button class="btn-fan" id="fan-med" onclick="setFan('med')">Med</button>
                <button class="btn-fan" id="fan-high" onclick="setFan('High')">High</button>
            </div>

            <div style="display: flex; justify-content: center; gap: 10px; margin-top: 14px;">
                <button class="btn-action" style="background: #2563eb;" onclick="setAC({power:'On', temp:24, mode:'Cool'})">Cool 24°C</button>
                <button class="btn-action btn-off" onclick="setAC({power:'Off'})">ปิดแอร์ (OFF)</button>
            </div>
        </div>

        <!-- Card 4: Recent AI Tuning History -->
        <div class="card">
            <div style="font-size: 13px; font-weight: 700; color: var(--text-muted); margin-bottom: 10px;">📜 ประวัติการปรับจูน & Feedback ล่าสุด</div>
            <div id="historyList" class="history-list">
                <div style="text-align: center; padding: 12px; color: #64748b;">ยังไม่มีข้อมูลประวัติ</div>
            </div>
        </div>

        <!-- Card 5: Ambi Cloud Target Manager (NCA / NCE / NCD) -->
        <div class="card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <span style="font-size: 14px; font-weight: 700; color: #fff;">☁️ จัดการ Cloud Server ในตัว Ambi (NCA / NCE)</span>
                <span id="cloudStatusBadge" class="badge" style="background: rgba(168, 85, 247, 0.2); color: #c084fc;">NCA / NCE</span>
            </div>
            <div style="font-size: 12px; color: var(--text-muted); margin-bottom: 8px;">
                Cloud ปลายทางปัจจุบัน: <b id="currentCloudTarget" style="color: #38bdf8;">กำลังตรวจสอบ...</b>
            </div>
            <div style="display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px;">
                <button class="btn-action" style="flex: 1 1 45%; background: #059669; font-size: 12px; padding: 8px 12px;" onclick="changeCloud((window.location.hostname || '192.168.1.199') + ':8867')">
                    🔄 ชี้มาเครื่องนี้ (TLS :8867)
                </button>
                <button class="btn-action" style="flex: 1 1 45%; background: #0284c7; font-size: 12px; padding: 8px 12px;" onclick="changeCloud((window.location.hostname || '192.168.1.199') + ':8866')">
                    🔄 ชี้มาเครื่องนี้ (TCP :8866)
                </button>
                <button class="btn-action" style="flex: 1 1 45%; background: #d97706; font-size: 12px; padding: 8px 12px;" onclick="reconnectCloud()">
                    ⚡ สั่ง Reconnect (NCD)
                </button>
                <button class="btn-action" style="flex: 1 1 45%; background: #475569; font-size: 12px; padding: 8px 12px;" onclick="changeCloud('connect.smartambi.com:8867')">
                    ↩️ คืนค่า Cloud ฮ่องกง
                </button>
            </div>
            <div id="cloudActionOutput" style="font-size: 11px; color: #94a3b8; margin-top: 8px; font-family: monospace;"></div>
            <div style="margin-top: 10px; border-top: 1px solid #334155; padding-top: 10px; display: flex; flex-direction: column; gap: 8px;">
                <button class="btn-action" style="width: 100%; background: #10b981; font-size: 13px; font-weight: 700; padding: 10px;" onclick="setLedGreen()">
                    🟢 สั่งไฟหน้าเครื่องเป็นสีเขียว (Solid Green)
                </button>
                <button class="btn-action" style="width: 100%; background: #4f46e5; font-size: 12px; padding: 9px;" onclick="viewSystemLog()">
                    📋 ดึงดู System Dump Log ของ Ambi (NSL)
                </button>
                <pre id="syslogModal" style="display: none; background: #090d16; padding: 12px; border-radius: 8px; max-height: 250px; overflow-y: auto; font-size: 11px; color: #38bdf8; margin-top: 8px; border: 1px solid #1e293b; white-space: pre-wrap; font-family: monospace;"></pre>
            </div>
        </div>
    </div>

    <div id="toast" class="toast">ส่งสัญญาณเรียบร้อย</div>

    <script>
        let currentState = null;

        function showToast(msg) {
            const t = document.getElementById('toast');
            t.innerText = msg;
            t.classList.add('show');
            setTimeout(() => t.classList.remove('show'), 2500);
        }

        async function updateDashboard() {
            try {
                const res = await fetch('/api/state');
                const data = await res.json();
                currentState = data;

                // 1. Live Metrics
                document.getElementById('roomTemp').innerText = data.ac_state.room_temp !== null ? data.ac_state.room_temp : '--';
                document.getElementById('roomHum').innerText = data.ac_state.room_humidity !== null ? data.ac_state.room_humidity : '--';
                document.getElementById('roomFeels').innerText = data.comfort.humidex !== null ? data.comfort.humidex : '--';

                // 2. Comfort Banner
                const banner = document.getElementById('comfortBanner');
                banner.style.background = data.comfort.badge_color + '25';
                banner.style.color = data.comfort.badge_color;
                banner.style.border = '1px solid ' + data.comfort.badge_color + '55';
                document.getElementById('comfortLabel').innerText = data.comfort.label;
                document.getElementById('comfortScore').innerText = 'Comfort Index: ' + (data.comfort.score > 0 ? '+' : '') + data.comfort.score + ' | เป้าหมาย: ' + data.comfort.target_humidex + '°C';

                // 3. Auto-Tune & Cooldown (Requirement 3: Wait until AC is turned ON)
                document.getElementById('autotuneToggle').checked = data.profile.auto_tune_enabled;
                const cdSec = data.cooldown_remaining_sec;
                const cdText = document.getElementById('cooldownText');
                const isACOn = (data.ac_state.power && data.ac_state.power.toLowerCase() === 'on');

                if (!data.profile.auto_tune_enabled) {
                    cdText.innerText = '⚪ ปิดใช้งาน Auto-Tuning';
                    cdText.style.color = '#94a3b8';
                } else if (!isACOn) {
                    cdText.innerText = '⏸️ แอร์ยังปิดอยู่ (รอเปิดแอร์ก่อนเริ่ม Auto-Tuning)';
                    cdText.style.color = '#f59e0b';
                } else {
                    if (cdSec > 0) {
                        const m = Math.floor(cdSec / 60);
                        const s = cdSec % 60;
                        cdText.innerText = '⏳ พักรออุณหภูมิกระจาย (อีก ' + (m > 0 ? m + ' น. ' : '') + s + ' วิ)';
                        cdText.style.color = '#fbbf24';
                    } else {
                        cdText.innerText = '🟢 พร้อมปรับอัตโนมัติ (แอร์เปิดอยู่ - ตรวจเช็คทุก 30 วินาที)';
                        cdText.style.color = '#34d399';
                    }
                }

                document.getElementById('offsetDesc').innerText = 'ค่าชดเชยส่วนบุคคล: ' + (data.profile.user_offset > 0 ? '+' : '') + data.profile.user_offset + '°C | เป้าหมาย Humidex: ' + data.comfort.target_humidex + '°C';

                // 4. AC Controls
                const pwr = data.ac_state.power;
                document.getElementById('targetTemp').innerText = data.ac_state.temperature + '°C';

                // Pending IR Badge
                const pendBadge = document.getElementById('pendingBadge');
                if (pendBadge) {
                    if (data.pending_ir) {
                        pendBadge.style.display = 'inline-block';
                        pendBadge.innerText = '⏳ รอกระตุ้น IR (' + (data.pending_ir.reason || 'Pending') + ')';
                    } else {
                        pendBadge.style.display = 'none';
                    }
                }

                const pwrBadge = document.getElementById('powerBadge');
                if (pwr.toLowerCase() === 'off') {
                    pwrBadge.innerText = 'OFF';
                    pwrBadge.style.background = 'rgba(239, 68, 68, 0.2)';
                    pwrBadge.style.color = '#f87171';
                } else {
                    pwrBadge.innerText = data.ac_state.mode.toUpperCase();
                    pwrBadge.style.background = 'rgba(59, 130, 246, 0.2)';
                    pwrBadge.style.color = '#60a5fa';
                }

                // Fan active buttons
                const currFan = (data.ac_state.fan || 'Auto').toLowerCase();
                document.querySelectorAll('.btn-fan').forEach(b => b.classList.remove('active'));
                if (currFan === 'auto') document.getElementById('fan-auto')?.classList.add('active');
                else if (currFan === 'quiet' || currFan === 'silent') document.getElementById('fan-quiet')?.classList.add('active');
                else if (currFan === 'low' || currFan === '1') document.getElementById('fan-low')?.classList.add('active');
                else if (currFan === 'med' || currFan === '3') document.getElementById('fan-med')?.classList.add('active');
                else if (currFan === 'high' || currFan === '5') document.getElementById('fan-high')?.classList.add('active');

                // 5. History List
                const hist = data.profile.history || [];
                const histElem = document.getElementById('historyList');
                if (hist.length > 0) {
                    histElem.innerHTML = hist.slice(0, 7).map(item => `
                        <div class="history-item">
                            <div>
                                <span style="font-weight: 600; color: #fff;">${item.action}</span>
                                <div style="font-size: 10px; color: #64748b;">${item.temp}°C | ลม: ${item.fan} | แอร์: ${item.power} | ห้อง: ${item.room_temp || '--'}°C (${item.room_humidity || '--'}%)</div>
                            </div>
                            <div style="text-align: right;">
                                <span style="color: #38bdf8;">${item.time}</span>
                                <div style="font-size: 9px; color: ${item.result && item.result.includes('OK') ? '#34d399' : '#94a3b8'};">${item.result || ''}</div>
                            </div>
                        </div>
                    `).join('');
                }
            } catch (e) {
                console.error("Dashboard poll error:", e);
            }
        }

        async function sendFeedback(choice) {
            showToast('⏳ กำลังสอน AI & ปรับแอร์...');
            try {
                const res = await fetch('/api/feedback?choice=' + encodeURIComponent(choice));
                const json = await res.json();
                showToast('✅ ' + (json.action || 'บันทึกสำเร็จ'));
                updateDashboard();
            } catch (e) {
                showToast('❌ เกิดข้อผิดพลาด');
            }
        }

        async function toggleAutoTune(enabled) {
            try {
                await fetch('/api/autotune?enable=' + enabled);
                showToast(enabled ? '✅ เปิด Auto-Tuning' : '⚪ ปิด Auto-Tuning');
                updateDashboard();
            } catch (e) {}
        }

        async function adjustTemp(delta) {
            if (!currentState) return;
            const newT = currentState.ac_state.temperature + delta;
            await setAC({temp: newT});
        }

        async function setFan(fan) {
            await setAC({fan: fan});
        }

        async function setAC(params) {
            showToast('📡 กำลังยิงสัญญาณ IR...');
            const q = new URLSearchParams(params).toString();
            try {
                const res = await fetch('/api/control?' + q);
                const json = await res.json();
                showToast('✅ สั่งงาน Daikin สำเร็จ: ' + (json.ir_result || 'OK'));
                updateDashboard();
            } catch (e) {
                showToast('❌ ส่งสัญญาณไม่สำเร็จ');
            }
        }

        async function fetchCloudStatus() {
            try {
                const res = await fetch('/api/cloud/status');
                const json = await res.json();
                document.getElementById('currentCloudTarget').innerText = json.cloud_server || 'ไม่สามารถติดต่อได้';
            } catch (e) {
                document.getElementById('currentCloudTarget').innerText = 'Error';
            }
        }

        async function changeCloud(server) {
            showToast('🚀 กำลังยิงคำสั่งเปลี่ยน Cloud Server...');
            document.getElementById('cloudActionOutput').innerText = 'กำลังส่ง NCE' + server + ' และ NCD...';
            try {
                const res = await fetch('/api/cloud/change?server=' + encodeURIComponent(server));
                const json = await res.json();
                showToast('✅ สั่งเปลี่ยน Cloud เรียบร้อย: ' + server);
                document.getElementById('cloudActionOutput').innerText = 'ผลลัพธ์ NCE: ' + json.response_ce + ' | NCD: ' + json.response_cd;
                fetchCloudStatus();
            } catch (e) {
                showToast('❌ ไม่สามารถเปลี่ยน Cloud ได้');
                document.getElementById('cloudActionOutput').innerText = 'เกิดข้อผิดพลาดในการส่งคำสั่ง';
            }
        }

        async function reconnectCloud() {
            showToast('⚡ กำลังสั่ง Ambi ตัดและต่อใหม่ (NCD)...');
            try {
                const res = await fetch('/api/cloud/reconnect');
                const json = await res.json();
                showToast('✅ สั่ง NCD สำเร็จ');
                document.getElementById('cloudActionOutput').innerText = 'ผลลัพธ์ NCD: ' + json.response;
            } catch (e) {
                showToast('❌ ไม่สามารถส่ง NCD ได้');
            }
        }

        async function viewSystemLog() {
            showToast('⏳ กำลังดึง System Dump Log จาก Ambi...');
            const box = document.getElementById('syslogModal');
            box.style.display = 'block';
            box.innerText = 'กำลังส่งคำสั่ง NSL ไปที่ Ambi:8070... กรุณารอสักครู่';
            try {
                const res = await fetch('/api/system_log');
                const text = await res.text();
                box.innerText = text || 'ไม่มีข้อมูล Log ตอบกลับมา';
                showToast('✅ ดึง System Dump Log สำเร็จ');
            } catch (e) {
                box.innerText = 'เกิดข้อผิดพลาดในการดึง Log: ' + e;
                showToast('❌ ไม่สามารถดึง System Log ได้');
            }
        }

        async function setLedGreen() {
            showToast('🟢 กำลังส่งคำสั่งไฟสีเขียวไปที่ Ambi...');
            try {
                const res = await fetch('/api/led/green');
                const json = await res.json();
                if (json.status === 'OK') {
                    showToast('✅ สั่งไฟหน้าเครื่องเป็นสีเขียวแล้ว!');
                } else {
                    showToast('❌ ยังไม่ได้ IP หรือส่งคำสั่งไม่สำเร็จ');
                }
            } catch (e) {
                showToast('❌ เกิดข้อผิดพลาดในการเชื่อมต่อ');
            }
        }

        updateDashboard();
        fetchCloudStatus();
        setInterval(updateDashboard, 3000);
        setInterval(fetchCloudStatus, 15000);
    </script>
</body>
</html>
"""
