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
KCAL_PER_RPM_PER_MINUTE = 0.15  # 칼로리 계산 계수 추가

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
previous_kcal = 0.0  # 이전 칼로리 값 저장 변수 추가

# ========== DATA RESET ==========
def reset_data():
    global raw_rpm_values, smooth_rpm_values, time_values, kcal_time, kcal_values, total_kcal, previous_kcal
    raw_rpm_values.clear()
    smooth_rpm_values.clear()
    time_values.clear()
    kcal_time.clear()
    kcal_values.clear()
    total_kcal = 0.0
    previous_kcal = 0.0

# ========== TCP HANDLER ==========
def handle_tcp_message(message):
    print(f"[Received] {message}")
    try:
        if float(message) == -1:
            reset_data()
    except ValueError:
        pass

tcp_handler = TCPHandler(handle_tcp_message)

# ========== SERIAL READER THREAD ==========
def read_serial():
    global total_kcal, previous_kcal
    # TCP 연결 시도
    tcp_handler.setup()
    tcp_handler.start_monitoring()
    
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    except Exception as e:
        print("❌ Serial error:", e)
        return

    print(f"✅ Connected to {SERIAL_PORT}")
    last_kcal_update = time.time()  # 마지막 칼로리 업데이트 시간

    while True:
        try:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if line.startswith("RPM:"):
                try:
                    value = float(line.split(":")[1].strip())
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

                    # Calculate calories based on RPM
                    time_diff = now - last_kcal_update
                    kcal_increment = smoothed * KCAL_PER_RPM_PER_MINUTE * (time_diff / 60)
                    total_kcal += kcal_increment

                    # TCP로 증가된 kCal 데이터 전송
                    if tcp_handler.is_ready():
                        if kcal_increment > 0:
                            tcp_handler.send_message(str(kcal_increment))

                    previous_kcal = total_kcal
                    kcal_time.append(now)
                    kcal_values.append(total_kcal)
                    last_kcal_update = now

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

# ========== KEYBOARD EVENT HANDLER ==========
def on_key(event):
    if event.key == 'a':
        reset_data()

# ========== WINDOWS ==========
fig = plt.figure(figsize=(16, 9))
gs = fig.add_gridspec(2, 2, width_ratios=[2, 1])

ax_rpm = fig.add_subplot(gs[:, 0])
ax_text = fig.add_subplot(gs[0, 1])
ax_kcal = fig.add_subplot(gs[1, 1])

# 키보드 이벤트 리스너 추가
fig.canvas.mpl_connect('key_press_event', on_key)

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
