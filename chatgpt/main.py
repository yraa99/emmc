import sys
import json
import queue
from PyQt6.QtWidgets import QApplication
from core.serial_port import SerialPort
from core.protocol import Protocol
from core.emmc import EMMC
from gui.main_window import MainWindow


class App:
    def __init__(self):
        self.serial = SerialPort()
        self.protocol = Protocol(self.serial)
        self.emmc = EMMC(self.protocol)

    def start(self):
        app = QApplication(sys.argv)
        window = MainWindow(self.emmc, self.serial)
        rx_queue = queue.Queue()

        def serial_log(data):
            rx_queue.put(data)

        def process_rx():
            while True:
                try:
                    data = rx_queue.get_nowait()
                except queue.Empty:
                    break
                if isinstance(data, (bytes, bytearray)):
                    for tab in (window.userarea, window.boot, window.health):
                        handler = getattr(tab, "handle_binary_data", None)
                        if handler:
                            try:
                                handler(bytes(data))
                            except Exception as e:
                                window.console.log(f"UI BINARY ERROR: {e}")
                    continue

                text = data.rstrip("\r\n")
                raw = text
                if raw.startswith("[RX] "):
                    raw = raw[5:]
                try:
                    obj = json.loads(raw)
                except Exception:
                    # Firmware debug text can be concatenated with one or more
                    # JSON packets in the same CDC delivery. Recover every
                    # complete JSON value instead of dropping valid responses.
                    decoder = json.JSONDecoder()
                    remainder = raw.lstrip()
                    packets = []
                    while remainder:
                        try:
                            value, end = decoder.raw_decode(remainder)
                        except json.JSONDecodeError:
                            break
                        packets.append(value)
                        remainder = remainder[end:].lstrip()
                    if not packets:
                        window.console.log(text)
                        continue
                    for packet in packets:
                        if isinstance(packet, dict) and packet.get("type") == "signal.status":
                            handler = getattr(window.isp, "handle_serial_data", None)
                            if handler:
                                try:
                                    handler(packet)
                                except Exception as e:
                                    window.console.log(f"UI SIGNAL ERROR: {e}")
                            continue
                        window.console.log(json.dumps(packet, ensure_ascii=False))
                        for tab in (window.identify, window.boot, window.userarea, window.health, window.isp):
                            handler = getattr(tab, "handle_serial_data", None)
                            if handler:
                                try:
                                    handler(packet)
                                except Exception as e:
                                    window.console.log(f"UI RX ERROR: {e}")
                    if remainder:
                        window.console.log(remainder)
                    continue

                # Realtime signal packets belong exclusively to ISP TEST.
                # Do not pollute the normal Console / Log with high-rate status.
                if isinstance(obj, dict) and obj.get("type") == "signal.status":
                    handler = getattr(window.isp, "handle_serial_data", None)
                    if handler:
                        try:
                            handler(obj)
                        except Exception as e:
                            window.console.log(f"UI SIGNAL ERROR: {e}")
                    continue

                window.console.log(text)
                for tab in (window.identify, window.boot, window.userarea, window.health, window.isp):
                    handler = getattr(tab, "handle_serial_data", None)
                    if handler:
                        try:
                            handler(obj)
                        except Exception as e:
                            window.console.log(f"UI RX ERROR: {e}")

        window.rx_timer = __import__('PyQt6.QtCore', fromlist=['QTimer']).QTimer()
        window.rx_timer.timeout.connect(process_rx)
        window.rx_timer.start(20)
        self.serial.set_callback(serial_log)
        window.show()
        sys.exit(app.exec())


if __name__ == "__main__":
    App().start()
