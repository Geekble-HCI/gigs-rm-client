import socket
import threading
import time

class TCPHandler:
    def __init__(self, message_callback):
        self.HOST = '192.168.0.2'  # 서버 주소
        self.PORT = 12345
        self.tcp_socket = None
        self.message_callback = message_callback
        self.is_connected = False
        self.setup_thread = None

    def setup(self):
        """TCP 연결 설정"""
        def setup_worker():
            while not self.is_connected:
                try:
                    self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.tcp_socket.connect((self.HOST, self.PORT))
                    print(f"Connected to server at {self.HOST}:{self.PORT}")
                    self.is_connected = True
                    return True
                    
                except Exception as e:
                    print(f"TCP connection failed: {e}")
                    if self.tcp_socket:
                        self.tcp_socket.close()
                    self.tcp_socket = None
                    time.sleep(1)  # 1초 대기 후 재시도

        self.setup_thread = threading.Thread(target=setup_worker, daemon=True)
        self.setup_thread.start()
        return True

    def is_ready(self):
        """TCP 연결이 준비되었는지 확인"""
        return self.is_connected

    def send_message(self, message):
        """TCP 메시지 전송"""
        if self.tcp_socket and self.is_connected:
            try:
                self.tcp_socket.sendall(str(message).encode())
                print(f"[Sent] {message}")
            except Exception as e:
                print(f"Failed to send message: {e}")
                self.is_connected = False

    def start_monitoring(self):
        """TCP 메시지 모니터링"""
        def tcp_monitor():
            while True:
                if self.tcp_socket and self.is_connected:
                    try:
                        data = self.tcp_socket.recv(1024)
                        if data:
                            message = data.decode()
                            self.message_callback(message)
                        else:
                            # 연결이 끊어진 경우
                            self.is_connected = False
                            print("Connection lost")
                    except:
                        self.is_connected = False
                time.sleep(0.1)

        monitor_thread = threading.Thread(target=tcp_monitor, daemon=True)
        monitor_thread.start()

    def cleanup(self):
        """리소스 정리"""
        if self.tcp_socket:
            self.tcp_socket.close()
