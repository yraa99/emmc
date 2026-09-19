import sys
import json
import queue
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from core.serial_port import SerialPort
from core.protocol import Protocol
from core.emmc import EMMC
from gui.main_window import MainWindow


IMPORTANT_TYPES = {
    "emmc.identify.result",
    "emmc.gpt.result",
    "emmc.gpt.end",
    "emmc.buildprop.result",
    "emmc.buildprop.end",
    "emmc.lp.result",
    "emmc.layout.result",
    "emmc.dump.status",
    "emmc.pin_test.result",
    "signal.started",
    "signal.stopped",
    "firmware.info",
    "error",
}


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

        def dispatch(packet):
            if not isinstance(packet, dict):
                return

            kind = packet.get("type", "")

            # MainWindow coordinates the one-click IDENTIFY -> GPT sequence.
            main_handler = getattr(window, "handle_serial_data", None)
            if main_handler:
                try:
                    main_handler(packet)
                except Exception as e:
                    window.console.log(f"UI MAIN ERROR: {e}")

            # High-rate signal telemetry belongs only to ISP TEST.
            if kind == "signal.status":
                handler = getattr(window.isp, "handle_serial_data", None)
                if handler:
                    try:
                        handler(packet)
                    except Exception as e:
                        window.console.log(f"UI SIGNAL ERROR: {e}")
                return

            for tab in (
                window.identify,
                window.boot,
                window.userarea,
                window.health,
                window.isp,
            ):
                handler = getattr(tab, "handle_serial_data", None)
                if handler:
                    try:
                        handler(packet)
                    except Exception as e:
                        window.console.log(f"UI RX ERROR: {e}")

            # Do not dump every JSON packet into the normal log. Individual
            # tabs format useful results; only unhandled important terminal
            # packets are allowed through here.
            if kind in IMPORTANT_TYPES:
                if kind in {
                    "emmc.identify.result",
                    "emmc.gpt.result",
                    "emmc.buildprop.result",
                    "emmc.buildprop.end",
                    "emmc.layout.result",
                }:
                    return
                if kind == "emmc.dump.status":
                    state = str(packet.get("state", ""))
                    if state in ("complete", "error", "stopped"):
                        window.console.log(
                            f"READ {state}: {packet.get('detail', '')}".strip()
                        )
                    return
                if kind == "emmc.pin_test.result":
                    window.console.log(
                        f"ISP {packet.get('pin', '?')}: "
                        f"{'OK' if packet.get('ok') else 'FAILED'}"
                    )
                    return
                if kind == "firmware.info":
                    window.console.log(
                        f"Firmware: {packet.get('name', 'eMMC Service Tool')} "
                        f"{packet.get('version', '')}".strip()
                    )
                    return
                if kind == "error":
                    window.console.log(str(packet.get("msg", packet)))
            # Unknown/debug JSON is intentionally suppressed from the user log.

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
                raw = text[5:] if text.startswith("[RX] ") else text

                try:
                    obj = json.loads(raw)
                    dispatch(obj)
                    continue
                except Exception:
                    pass

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

                if packets:
                    for packet in packets:
                        if isinstance(packet, dict):
                            dispatch(packet)
                    # Ignore any trailing serial/debug fragment unless it is
                    # clearly an error message.
                    if remainder.startswith("ERROR"):
                        window.console.log(remainder)
                elif raw.startswith(("ERROR", "ERR", "FAILED")):
                    window.console.log(raw)

        window.rx_timer = QTimer()
        window.rx_timer.timeout.connect(process_rx)
        window.rx_timer.start(20)
        self.serial.set_callback(serial_log)
        window.show()
        sys.exit(app.exec())


if __name__ == "__main__":
    App().start()
