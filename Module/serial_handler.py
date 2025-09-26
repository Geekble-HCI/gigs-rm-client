from sched import Event
from .events import GameEvent, EventType, InputSource
from typing import Callable, Optional
import serial
import serial.tools.list_ports
import threading
import time

class SerialHandler:
    def __init__(self, gigs_instance=None, on_event: Optional[Callable[[Event], None]] = None):
        self.serial_ports = {}  # 여러 시리얼 포트를 저장하는 딕셔너리
        self.excluded_ports = [
            '/dev/cu.debug-console',
            '/dev/cu.Bluetooth-Incoming-Port',
            '/dev/cu.iPhone-WirelessiAP',
            '/dev/tty.Bluetooth-Incoming-Port',
            '/dev/tty.debug-console',
            '/dev/cu.BT-RY'
        ]
        self.is_connected = False
        self.setup_thread = None
        self._gigs = gigs_instance  # GIGS 인스턴스 참조
        self._on_event = on_event  # 외부 이벤트 전달

        # 객체 생성 시 자동으로 포트 연결 시도
        self.setup()

    def setup(self):
        def setup_worker():
            while not self.is_connected:
                try:
                    ports = list(serial.tools.list_ports.comports())
                    connected_count = 0
                    
                    for port in ports:
                        if port.device in self.excluded_ports:
                            continue
                        if port.device not in self.serial_ports:
                            try:
                                new_port = serial.Serial(port.device, 115200, timeout=1)
                                self.serial_ports[port.device] = new_port
                                print(f"Connected to {port.device}")
                                connected_count += 1
                                # 각 포트마다 모니터링 시작
                                self.start_port_monitoring(port.device, new_port)
                            except:
                                print(f"Failed to connect to {port.device}")
                    
                    if connected_count > 0:
                        self.is_connected = True

                        # 연결된 모든 포트를 즉시 리셋 & 재연결
                        for dev in list(self.serial_ports.keys()):
                            self.reset_and_reconnect_port(dev)

                        return
                    
                    print("No suitable serial ports found, retrying...")
                except Exception as e:
                    print(f"Serial port error: {e}")
                time.sleep(1)

        self.setup_thread = threading.Thread(target=setup_worker, daemon=True)
        self.setup_thread.start()
        return True

    def start_port_monitoring(self, port_device, port):
        """각 포트별 모니터링 스레드 시작"""
        def port_monitor():
            while True:
                try:
                     if port.is_open and port.in_waiting:
                        raw = port.readline().decode(errors="ignore").strip()
                        print(f"[SERIAL] Input from {port_device}: {raw}")
                        self._dispatch_serial_input(raw)
                except Exception as e:
                    print(f"Error reading from {port_device}: {e}")
                    break
                time.sleep(0.1)

        threading.Thread(target=port_monitor, daemon=True).start()
    
    # 시리얼 분기 -> 메서드 추출
    def _dispatch_serial_input(self, received_data: str):
        ev = self._parse_serial_data(received_data)
        if ev and self._on_event:
            self._on_event(ev)

    # 파싱만 책임 (상태 전환 X)
    def _parse_serial_data(self, s: str):
        if not s:
            return None
        # 8자리 영숫자 → RFID
        if len(s) == 8 and s.isalnum():
            return GameEvent(kind=EventType.RFID_DETECTED, source=InputSource.SERIAL, raw=s)
        # 레거시 'a' → RFID
        if s == 'a':
            return GameEvent(kind=EventType.RFID_DETECTED, source=InputSource.SERIAL, raw=s)
        # 숫자 (정수 또는 소수점) → 점수
        try:
            score_value = float(s)
            return GameEvent(kind=EventType.SCORE_RECEIVED, source=InputSource.SERIAL, raw=s, score=score_value)
        except ValueError:
            pass
        return GameEvent(kind=EventType.UNKNOWN, source=InputSource.SERIAL, raw=s)

    def is_ready(self):
        """하나 이상의 시리얼 연결이 준비되었는지 확인"""
        return self.is_connected

    def start_monitoring(self):
        """이제 개별 포트 모니터링은 setup 과정에서 처리"""
        pass

    def cleanup(self):
        """모든 시리얼 포트 정리"""
        for port in self.serial_ports.values():
            if port and port.is_open:
                port.close()

    def reset_and_reconnect_port(self, device: str):
        """특정 포트를 DTR 신호로 리셋 후 재연결"""
        port = self.serial_ports.get(device)
        if not port:
            print(f"No active port found for {device}")
            return False

        try:
            if port.is_open:
                print(f"Resetting {device}...")
                # 아두이노 리셋 (DTR 신호 토글)
                port.setDTR(False)
                time.sleep(0.5)
                port.setDTR(True)
                port.close()
                time.sleep(1)  # 아두이노 재부팅 대기

                # 재연결
                new_port = serial.Serial(device, 115200, timeout=1)
                self.serial_ports[device] = new_port
                print(f"Reconnected to {device}")
                # 다시 모니터링 시작
                self.start_port_monitoring(device, new_port)
                return True
        except Exception as e:
            print(f"Failed to reset {device}: {e}")
            return False

    def reset_and_reconnect_ports(self):
        """등록된 모든 포트 순회하며 reset/reconnect"""
        for device in list(self.serial_ports.keys()):
            self.reset_and_reconnect_port(device)

    def send_message(self, message):
        """연결된 모든 시리얼 포트로 메시지 전송"""
        if not self.is_connected:
            print(f"[SERIAL] Send skipped: not connected - {message}")
            return
        
        sent_count = 0
        for device, port in self.serial_ports.items():
            try:
                if port and port.is_open:
                    port.write(f"{message}\n".encode())
                    port.flush()
                    sent_count += 1
                    print(f"[SERIAL] Sent '{message}' to {device}")
            except Exception as e:
                print(f"[SERIAL] Failed to send '{message}' to {device}: {e}")
        
        if sent_count == 0:
            print(f"[SERIAL] No active ports available to send: {message}")
