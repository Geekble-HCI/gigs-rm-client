import socket
import threading
import time

class TCPHandler:
    def __init__(self, message_callback):
        self.HOST = '0.0.0.0'
        self.PORT = 12345
        self.tcp_socket = None
        self.client_socket = None
        self.message_callback = message_callback
        self.is_connected = False
        self.setup_thread = None

    def setup(self):
        """TCP 연결 설정"""
        def setup_worker():
            while not self.is_connected:
                try:
                    self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.tcp_socket.bind((self.HOST, self.PORT))
                    self.tcp_socket.settimeout(5)  # 5초 타임아웃 설정
                    self.tcp_socket.listen(1)
                    print(f"TCP server started. Listening on port {self.PORT}...")
                    
                    # 클라이언트 연결 대기
                    self.client_socket, addr = self.tcp_socket.accept()
                    print(f"[Connected] {addr}")
                    self.is_connected = True
                    return True
                    
                except Exception as e:
                    print(f"TCP server setup failed: {e}")
                    if self.tcp_socket:
                        self.tcp_socket.close()
                    self.tcp_socket = None
                    self.client_socket = None
                    time.sleep(1)  # 1초 대기 후 재시도

        self.setup_thread = threading.Thread(target=setup_worker, daemon=True)
        self.setup_thread.start()
        return True  # 즉시 True 반환하고 백그라운드에서 연결 시도

    def is_ready(self):
        """TCP 연결이 준비되었는지 확인"""
        return self.is_connected

    def send_message(self, message):
        """TCP 메시지 전송"""
        if self.client_socket:
            try:
                self.client_socket.sendall(str(message).encode())
                print(f"[Sent] {message}")
            except Exception as e:
                print(f"Failed to send message: {e}")

    def start_monitoring(self):
        """TCP 메시지 모니터링"""
        def tcp_monitor():
            while True:
                if self.client_socket:
                    try:
                        data = self.client_socket.recv(1024)
                        if data:
                            message = data.decode()
                            self.message_callback(message)
                    except:
                        pass
                time.sleep(0.1)

        monitor_thread = threading.Thread(target=tcp_monitor, daemon=True)
        monitor_thread.start()

    def cleanup(self):
        """리소스 정리"""
        if self.client_socket:
            self.client_socket.close()
        if self.tcp_socket:
            self.tcp_socket.close()
