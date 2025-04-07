import serial
import serial.tools.list_ports
import threading
import time
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from collections import deque
import numpy as np
from Module.tcp_handler import TCPHandler

# ========== CONFIG ==========
BAUD_RATE = 115200
MOVING_AVERAGE_WINDOW = 5
PLOT_INTERVAL_MS = 500
MAX_RPM_Y = 1200

# ========== AUTO-DETECT SERIAL PORT ==========
def find_serial_port():
    ports = list(serial.tools.list_ports.comports())
    for p in ports:
        if any(x in p.device for x in ["ttyUSB", "ttyACM", "serial", "AMA", "USB"]):
            return p.device
    return None

SERIAL_PORT = find_serial_port()
if not SERIAL_PORT:
    print("❌ No serial device found.")
    exit()

# ========== DATA STORAGE ==========
raw_rpm_values = deque()
smooth_rpm_values = deque()
time_values = deque()
kcal_time = deque()
kcal_values = deque()
total_kcal = 0.0

# ========== TCP HANDLER ==========
def handle_tcp_message(message):
    print(f"[Received] {message}")

tcp_handler = TCPHandler(handle_tcp_message)

# ========== SERIAL READER THREAD ==========
def read_serial():
    global total_kcal
    # TCP 연결 시도
    tcp_handler.setup()
    tcp_handler.start_monitoring()
    
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    except Exception as e:
        print("❌ Serial error:", e)
        return

    print(f"✅ Connected to {SERIAL_PORT}")

    while True:
        try:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if line.startswith("RPM:"):
                try:
                    value = float(line.split(":")[1].strip())
                    # TCP로 RPM 데이터 전송
                    now = time.time()
                    raw_rpm_values.append(value)
                    time_values.append(now)

                    # Apply moving average
                    window = list(raw_rpm_values)[-MOVING_AVERAGE_WINDOW:]
                    smoothed = sum(window) / len(window)
                    smooth_rpm_values.append(smoothed)

                    # Keep only matching timestamps
                    while len(smooth_rpm_values) > len(time_values):
                        smooth_rpm_values.popleft()
                    while time_values and (now - time_values[0]) > 60:
                        time_values.popleft()
                        smooth_rpm_values.popleft()
                except ValueError:
                    pass

            elif line.startswith("PULSE:"):
                # Ignore if kcal isn't provided
                pass

            elif line.startswith("kCal:"):
                try:
                    total_kcal = float(line.split(":")[1].strip())
                    # TCP로 kCal 데이터 전송
                    if tcp_handler.is_ready():
                        tcp_handler.send_message(str(total_kcal/30))
                    kcal_time.append(time.time())
                    kcal_values.append(total_kcal)
                except ValueError:
                    pass
        except Exception as e:
            print("⚠️ Serial read error:", e)

# ========== PLOTS ==========

def animate_rpm(i):
    ax_rpm.clear()
    if time_values:
        x = np.array([t - time_values[0] for t in time_values])
        y = list(smooth_rpm_values)

        # sine wave-like interpolation
        if len(x) > 3:
            xnew = np.linspace(x[0], x[-1], 200)
            ynew = np.interp(xnew, x, y)
            ynew = np.array(ynew)
            ynew = np.convolve(ynew, np.ones(5)/5, mode='same')
            ax_rpm.plot(xnew, ynew, label="RPM")
        else:
            ax_rpm.plot(x, y, label="RPM")

    ax_rpm.set_ylim(0, MAX_RPM_Y)
    ax_rpm.set_title("Real-Time Average RPM")
    ax_rpm.set_ylabel("RPM")
    ax_rpm.set_xlabel("Time (s)")
    ax_rpm.grid(True)
    ax_rpm.legend()

def animate_kcal(i):
    ax_kcal.clear()
    if kcal_time:
        start = kcal_time[0]
        x = [(t - start)/60 for t in kcal_time]  # Convert to minutes
        y = list(kcal_values)
        ax_kcal.plot(x, y, label="kCal Burned", color='darkorange')

    ax_kcal.set_title("Cumulative kCal Burned")
    ax_kcal.set_ylabel("kCal")
    ax_kcal.set_xlabel("Time (min)")
    ax_kcal.grid(True)
    ax_kcal.legend()

def animate_text(i):
    ax_text.clear()
    ax_text.text(0.5, 0.5, f"{total_kcal:.2f} kCal",
                 fontsize=50, ha='center', va='center', fontweight='bold')
    ax_text.axis("off")

# ========== WINDOWS ==========
fig = plt.figure(figsize=(16, 9))
gs = fig.add_gridspec(2, 2, width_ratios=[2, 1])

ax_rpm = fig.add_subplot(gs[:, 0])
ax_text = fig.add_subplot(gs[0, 1])
ax_kcal = fig.add_subplot(gs[1, 1])

ani_rpm = FuncAnimation(fig, animate_rpm, interval=PLOT_INTERVAL_MS, cache_frame_data=False)
ani_text = FuncAnimation(fig, animate_text, interval=PLOT_INTERVAL_MS, cache_frame_data=False)
ani_kcal = FuncAnimation(fig, animate_kcal, interval=PLOT_INTERVAL_MS, cache_frame_data=False)

# ========== START THREAD ==========
serial_thread = threading.Thread(target=read_serial, daemon=True)
serial_thread.start()

# Fullscreen and resizable layout
mng = plt.get_current_fig_manager()
try:
    mng.full_screen_toggle()
except:
    try:
        mng.window.state('zoomed')  # For TkAgg on Windows
    except:
        pass

plt.tight_layout()

# 프로그램 종료 시 TCP 연결 정리
try:
    plt.show()
finally:
    tcp_handler.cleanup()
