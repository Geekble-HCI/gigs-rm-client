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
KCAL_SEND_SCALE = 10  #추가된 배율 파라미터


# ========== DATA STORAGE ==========
raw_rpm_values = deque()
smooth_rpm_values = deque()
time_values = deque()
kcal_time = deque()
kcal_values = deque()
total_kcal = 0.0
previous_kcal = 0.0  # 이전 누적 칼로리 값 저장

# ========== DATA RESET ==========
def reset_data():
    global raw_rpm_values, smooth_rpm_values, time_values
    global kcal_time, kcal_values, total_kcal, previous_kcal
    raw_rpm_values.clear()
    smooth_rpm_values.clear()
    time_values.clear()
    kcal_time.clear()
    kcal_values.clear()
    total_kcal = 0.0
    previous_kcal = 0.0

# ========== SERIAL HANDLER ==========
def handle_serial_data(data):
    print(f"[Received] '{data}' (len={len(data)})")
    print(f"[DEBUG] Data repr: {repr(data)}")
    print(f"[DEBUG] Starts with 'RPM:'? {data.startswith('RPM:')}")
    
    try:
        if float(data) == -1:
            reset_data()
            return
    except ValueError:
        pass
    
    try:
        if data.startswith("RPM:"):
            print(f"[DEBUG] Parsing RPM data: {data}")
            rpm_part = data.split(":")[1].strip()
            print(f"[DEBUG] RPM part after split: '{rpm_part}'")
            rpm_value = float(rpm_part)
            print(f"[DEBUG] Parsed RPM value: {rpm_value}")
            process_rpm_data(rpm_value)
        else:
            print(f"[DEBUG] Data does not start with 'RPM:', skipping")
    except (ValueError, IndexError) as e:
        print(f"[DEBUG] Error parsing RPM data: {e}")

serial_handler = SerialHandler(on_data=handle_serial_data)

# ========== RPM DATA PROCESSING ==========
last_kcal_update = time.time()

def process_rpm_data(rpm_value):
    global total_kcal, previous_kcal, last_kcal_update
    
    print(f"[DEBUG] Processing RPM: {rpm_value}")
    now = time.time()
    raw_rpm_values.append(rpm_value)
    time_values.append(now)

    # Moving average
    window = list(raw_rpm_values)[-MOVING_AVERAGE_WINDOW:]
    smoothed = sum(window) / len(window)
    smooth_rpm_values.append(smoothed)
    
    print(f"[DEBUG] Data lengths - raw: {len(raw_rpm_values)}, smooth: {len(smooth_rpm_values)}, time: {len(time_values)}")

    while len(smooth_rpm_values) > len(time_values):
        smooth_rpm_values.popleft()
    while time_values and (now - time_values[0]) > 60:
        time_values.popleft()
        smooth_rpm_values.popleft()

    # kcal 계산
    time_diff = now - last_kcal_update
    kcal_increment = smoothed * KCAL_PER_RPM_PER_MINUTE * (time_diff / 60)
    total_kcal += kcal_increment

    # 증가한 kcal만 전송
    if serial_handler.is_ready():
        if total_kcal > previous_kcal:
            kcal_diff = total_kcal - previous_kcal
            scaled_value = kcal_diff * KCAL_SEND_SCALE
            serial_handler.send_message(f"{scaled_value:.4f}")

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
        x = [(t - start)/60 for t in kcal_time]
        y = list(kcal_values)
        ax_kcal.plot(x, y, label="kCal Burned")
    ax_kcal.set_title("Cumulative kCal Burned")
    ax_kcal.set_ylabel("kCal")
    ax_kcal.set_xlabel("Time (min)")
    ax_kcal.grid(True)
    ax_kcal.legend()

def animate_text(i):
    ax_text.clear    ()
    ax_text.text(0.5, 0.5, f"{total_kcal:.2f} kCal",
                 fontsize=50, ha='center', va='center', fontweight='bold')
    ax_text.axis("off")

# ========== KEYBOARD EVENT ==========
def on_key(event):
    if event.key == 'a':
        reset_data()

# ========== WINDOWS & PLOTS ==========
fig = plt.figure(figsize=(16, 9))
gs = fig.add_gridspec(2, 2, width_ratios=[2, 1])

ax_rpm = fig.add_subplot(gs[:, 0])
ax_text = fig.add_subplot(gs[0, 1])
ax_kcal = fig.add_subplot(gs[1, 1])

fig.canvas.mpl_connect('key_press_event', on_key)

ani_rpm = FuncAnimation(fig, animate_rpm, interval=PLOT_INTERVAL_MS, cache_frame_data=False)
ani_text = FuncAnimation(fig, animate_text, interval=PLOT_INTERVAL_MS, cache_frame_data=False)
ani_kcal = FuncAnimation(fig, animate_kcal, interval=PLOT_INTERVAL_MS, cache_frame_data=False)

mng = plt.get_current_fig_manager()
try:
    mng.full_screen_toggle()
except:
    try:
        mng.window.state('zoomed')
    except:
        pass

plt.tight_layout()

try:
    plt.show()
finally:
    serial_handler.cleanup()
