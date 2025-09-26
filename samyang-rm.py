import time
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from collections import deque
import numpy as np
from Module.serial_handler import SerialHandler

# ========== CONFIG ==========
MOVING_AVERAGE_WINDOW = 5
PLOT_INTERVAL_MS = 500
MAX_RPM_Y = 1200
KCAL_PER_RPM_PER_MINUTE = 0.15


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

# ========== SERIAL HANDLER ==========
def handle_serial_data(data):
    print(f"[Received] {data}")
    try:
        # 리셋 명령 처리
        if float(data) == -1:
            reset_data()
            return
        
        # RPM 데이터 처리
        if data.startswith("RPM:"):
            rpm_value = float(data.split(":")[1].strip())
            process_rpm_data(rpm_value)
    except (ValueError, AttributeError):
        pass

serial_handler = SerialHandler(on_data=handle_serial_data)

# ========== RPM DATA PROCESSING ==========
last_kcal_update = time.time()

def process_rpm_data(rpm_value):
    global total_kcal, previous_kcal, last_kcal_update
    
    now = time.time()
    raw_rpm_values.append(rpm_value)
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

    # Serial로 증가된 kCal 데이터 전송
    if serial_handler.is_ready():
        if kcal_increment > 0:
            serial_handler.send_message(str(kcal_increment))

    previous_kcal = total_kcal
    kcal_time.append(now)
    kcal_values.append(total_kcal)
    last_kcal_update = now

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

# ========== SERIAL HANDLER INITIALIZATION ==========
# SerialHandler는 생성 시 자동으로 포트 연결 및 모니터링 시작

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

# 프로그램 종료 시 Serial 연결 정리
try:
    plt.show()
finally:
    serial_handler.cleanup()
