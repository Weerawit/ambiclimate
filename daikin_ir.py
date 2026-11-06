"""
Daikin Air Conditioner IR Protocol Encoder for Global Caché / Ambi Climate 2
=============================================================================
Supports:
1. Daikin ARC433 / ARC480 Protocol A (from YSYouJack/Daikin-ir-control-rpi):
   - 2-Frame: 8-byte Header Frame (11 DA 27 F0 00 00 00 02) + 19-byte Command Frame
2. Daikin Protocol B (Standard 216-bit):
   - 2-Frame: 8-byte Header Frame (11 DA 27 00 C5 00 00 D7) + 19-byte Command Frame
3. Daikin Protocol C (152-bit / Daikin152):
   - 1-Frame: 19-byte Command Frame only
"""

FREQ = 38000
US_PER_CYCLE = 1000000.0 / FREQ

def us_to_cycles(us):
    return round(us / US_PER_CYCLE)

# Timing in carrier cycles at 38kHz
# Daikin Pulse-Distance timings:
HDR_MARK = us_to_cycles(3400)    # ~129 cycles
HDR_SPACE = us_to_cycles(1750)   # ~67 cycles
BIT_MARK = us_to_cycles(430)     # ~16 cycles
ZERO_SPACE = us_to_cycles(430)   # ~16 cycles
ONE_SPACE = us_to_cycles(1300)   # ~49 cycles
INTER_GAP = us_to_cycles(29000)  # ~1102 cycles (space between Frame 1 and Frame 2)
STOP_SPACE = us_to_cycles(32000) # ~1216 cycles (trailing space)

# Operation Modes (upper nibble of byte 5)
MODE_AUTO = 0x00
MODE_DRY  = 0x20
MODE_COOL = 0x30
MODE_HEAT = 0x40
MODE_FAN  = 0x60

# Fan Speeds (upper nibble of byte 8)
FAN_AUTO   = 0xA0
FAN_QUIET  = 0xB0
FAN_1      = 0x30
FAN_2      = 0x40
FAN_3      = 0x50
FAN_4      = 0x60
FAN_5      = 0x70

# Swing Modes (lower nibble of byte 8)
SWING_OFF  = 0x00
SWING_ON   = 0x0F

def encode_frame(byte_list, is_last_frame=True):
    """
    Encodes a single frame of bytes (LSB first) into alternating mark/space cycle pulses.
    """
    pulses = [HDR_MARK, HDR_SPACE]
    for b in byte_list:
        for bit in range(8):
            pulses.append(BIT_MARK)
            if (b >> bit) & 1:
                pulses.append(ONE_SPACE)
            else:
                pulses.append(ZERO_SPACE)
    # Stop bit mark
    pulses.append(BIT_MARK)
    # Gap space
    if is_last_frame:
        pulses.append(STOP_SPACE)
    else:
        pulses.append(INTER_GAP)
    return pulses

def build_daikin_command(temp=24, mode="cool", fan="auto", swing="off", power=True, protocol_type="B"):
    """
    Constructs Daikin IR frames and returns (frame1_bytes, frame2_bytes).
    protocol_type:
      'B': 2-Frame with C5 header (Standard Daikin - VERIFIED WORKING!)
      'A': 2-Frame with F0 header (ARC433/ARC480 from YSYouJack)
      'C': 1-Frame (19 bytes only)
    """
    mode_map = {
        "auto": MODE_AUTO,
        "cool": MODE_COOL,
        "dry": MODE_DRY,
        "heat": MODE_HEAT,
        "fan": MODE_FAN,
    }
    fan_map = {
        "auto": FAN_AUTO,
        "quiet": FAN_QUIET,
        "silent": FAN_QUIET,
        "1": FAN_1,
        "2": FAN_2,
        "3": FAN_3,
        "4": FAN_4,
        "5": FAN_5,
        "low": FAN_1,
        "med": FAN_3,
        "high": FAN_5,
    }
    swing_map = {
        "off": SWING_OFF,
        "on": SWING_ON,
        "auto": SWING_ON,
        "vert": SWING_ON,
    }

    m_val = mode_map.get(str(mode).lower(), MODE_COOL)
    f_val = fan_map.get(str(fan).lower(), FAN_AUTO)
    s_val = swing_map.get(str(swing).lower(), SWING_OFF)

    # Temperature clamp (18°C - 30°C for Daikin)
    temp = max(18, min(30, int(temp)))

    # Frame 1 (8 bytes)
    if protocol_type == "A":
        # YSYouJack / ARC433A59 / ARC480 variant
        # 11 DA 27 F0 00 00 00 02
        frame1 = [0x11, 0xDA, 0x27, 0xF0, 0x00, 0x00, 0x00, 0x00]
        frame1[7] = sum(frame1[0:7]) & 0xFF  # = 0x02
    elif protocol_type == "B":
        # Standard Daikin 216-bit
        # 11 DA 27 00 C5 00 00 D7
        frame1 = [0x11, 0xDA, 0x27, 0x00, 0xC5, 0x00, 0x00, 0x00]
        frame1[7] = sum(frame1[0:7]) & 0xFF  # = 0xD7
    else:
        frame1 = None  # Single-frame (Daikin152)

    # Frame 2 (19 bytes)
    p_bit = 0x01 if power else 0x00
    byte5 = (m_val & 0xF0) | (p_bit & 0x0F)
    byte6 = (temp * 2) & 0xFF
    byte8 = (f_val & 0xF0) | (s_val & 0x0F)

    frame2 = [
        0x11, 0xDA, 0x27, 0x00, 0x00,  # Bytes 0-4: Fixed Header
        byte5,                         # Byte 5: Mode & Power
        byte6,                         # Byte 6: Temp * 2
        0x00,                          # Byte 7: Fixed 00
        byte8,                         # Byte 8: Fan & Swing
        0x00,                          # Byte 9: Fixed 00
        0x00,                          # Byte 10: Timer
        0x00,                          # Byte 11: Timer
        0x00,                          # Byte 12: Timer
        0x00,                          # Byte 13: Powerful (00 = Off)
        0x00,                          # Byte 14: Fixed 00
        0xC0,                          # Byte 15: Fixed C0
        0x00,                          # Byte 16: Econo (00 = Off)
        0x00,                          # Byte 17: Fixed 00
        0x00                           # Byte 18: Checksum placeholder
    ]
    frame2[18] = sum(frame2[0:18]) & 0xFF

    return frame1, frame2

def frames_to_sendir(frame1, frame2, connector="1:1", cmd_id=1):
    """
    Converts frame1 and frame2 into a single Global Caché sendir command.
    """
    pulses = []
    if frame1 is not None:
        pulses.extend(encode_frame(frame1, is_last_frame=False))
    pulses.extend(encode_frame(frame2, is_last_frame=True))

    pulse_str = ",".join(str(p) for p in pulses)
    return f"sendir,{connector},{cmd_id},{FREQ},1,1,{pulse_str}\r"

if __name__ == "__main__":
    print("=" * 65)
    print("Testing Daikin IR Protocol Encoder (ARC480 / ARC433)")
    print("=" * 65)

    for ptype in ["A", "B", "C"]:
        f1, f2 = build_daikin_command(temp=24, mode="cool", fan="auto", swing="off", power=True, protocol_type=ptype)
        f1_str = ' '.join(f'{b:02X}' for b in f1) if f1 else "(None - Single Frame)"
        f2_str = ' '.join(f'{b:02X}' for b in f2)
        sendir = frames_to_sendir(f1, f2)
        print(f"\n[Protocol {ptype}]")
        print(f"  Frame 1: {f1_str}")
        print(f"  Frame 2: {f2_str}")
        print(f"  sendir length: {len(sendir)} chars, sample: {sendir[:60]}...")
