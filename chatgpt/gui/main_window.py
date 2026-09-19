from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QTextEdit, QProgressBar, QTabWidget, QSplitter
)
from PyQt6.QtCore import QTimer, QDateTime, Qt

from gui.console import Console
from gui.identify import IdentifyTab
from gui.userarea import UserAreaTab
from gui.adb_fastboot import ADBFastbootTab
from gui.factory_image import FactoryImageTab


class MainWindow(QMainWindow):
    """
    GUI shell follows yraa99/gui exactly at the window/layout level.
    Existing pico-emmc-beta service implementations remain the backend.
    """

    def __init__(self, emmc_core=None, serial_core=None):
        super().__init__()
        self.emmc = emmc_core
        self.serial = serial_core
        self.identify_sequence = False
        self.last_pico_device = None

        self.setWindowTitle("Pico eMMC Tool - Service Console")
        self.resize(1024, 620)

        self.init_ui()
        self.start_clock_timer()

        if self.serial:
            try:
                self.serial.set_disconnect_callback(self.on_serial_disconnect)
            except Exception:
                pass
            self.refresh_ports(auto_connect=True)

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # ====================================================
        # TOP HEADER — exact gui repo structure
        # ====================================================
        header_layout = QHBoxLayout()

        lbl_port = QLabel("PORT:")
        lbl_port.setStyleSheet("font-weight: bold;")

        self.combo_port = QComboBox()
        self.combo_port.setMinimumWidth(200)

        self.btn_refresh = QPushButton("REFRESH")
        self.btn_refresh.clicked.connect(self.refresh_ports)

        self.btn_connect = QPushButton("CONNECT")
        self.btn_connect.setStyleSheet(
            "background-color: #388e3c; color: white; font-weight: bold;"
        )
        self.btn_connect.clicked.connect(self.toggle_connect)

        self.lbl_datetime = QLabel()
        self.lbl_datetime.setStyleSheet(
            "font-weight: bold; color: #1565c0; margin-left: 15px;"
        )

        header_layout.addWidget(lbl_port)
        header_layout.addWidget(self.combo_port)
        header_layout.addWidget(self.btn_refresh)
        header_layout.addWidget(self.btn_connect)
        header_layout.addStretch()
        header_layout.addWidget(self.lbl_datetime)
        main_layout.addLayout(header_layout)

        # ====================================================
        # SPLITTER — exact gui repo structure
        # ====================================================
        splitter = QSplitter(Qt.Orientation.Horizontal)

        log_panel = QWidget()
        log_layout = QVBoxLayout(log_panel)
        log_layout.setContentsMargins(0, 0, 0, 0)

        lbl_log = QLabel("LOG")
        lbl_log.setStyleSheet(
            "font-weight: bold; background-color: #d0d0d0; "
            "padding: 4px; font-size: 13px;"
        )

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet(
            "background-color: #1b1b1b; color: #00ff66; "
            "font-family: Consolas, Monospace; font-size: 12px;"
        )

        self.console = Console()
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Operation Progress: %p%")

        self.lbl_bottom_time = QLabel("Jam sekarang: --:--:--")
        self.lbl_bottom_time.setStyleSheet("font-size: 11px; color: #444;")

        log_layout.addWidget(lbl_log)
        log_layout.addWidget(self.log_text)
        log_layout.addWidget(self.progress_bar)
        log_layout.addWidget(self.lbl_bottom_time)

        # Keep the beta Console backend while rendering the gui repo console.
        self.console_widget_log = self.log_text
        original_log = getattr(self.console, "log", None)

        def gui_log(message):
            if original_log:
                try:
                    original_log(message)
                except Exception:
                    pass
            timestamp = QDateTime.currentDateTime().toString("hh:mm:ss")
            self.log_text.append(f"[{timestamp}] {message}")

        self.console.log = gui_log

        # ====================================================
        # RIGHT TABS — exact gui repo tab order/names.
        # Backend functionality is retained in the beta tab
        # implementations rather than replacing it with stubs.
        # ====================================================
        self.tabs = QTabWidget()

        self.identify = IdentifyTab(self.emmc, self.console)
        self.userarea = UserAreaTab(self.emmc, self.console)
        self.adb_fastboot = ADBFastbootTab(self.console)
        self.factory_image = FactoryImageTab(self.console)

        # Compatibility names used by pico-emmc-beta dispatch.
        self.tab_main = self.identify
        self.tab_userarea = self.userarea
        self.tab_adb = self.adb_fastboot
        self.tab_factory = self.factory_image

        # Keep beta service objects available for protocol dispatch.
        # They are attached to MainWindow without changing the four-tab shell.
        self.boot = None
        self.health = None
        self.special = None
        self.isp = None

        self.tabs.addTab(self.tab_main, "MAIN")
        self.tabs.addTab(self.tab_userarea, "USER AREA")
        self.tabs.addTab(self.tab_adb, "ADB Fastboot")
        self.tabs.addTab(self.tab_factory, "Factory Image")

        splitter.addWidget(log_panel)
        splitter.addWidget(self.tabs)
        splitter.setSizes([380, 620])
        main_layout.addWidget(splitter)

        self.console.log("Pico eMMC Tool initialized successfully.")

    def start_clock_timer(self):
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_datetime)
        self.clock_timer.start(1000)
        self.update_datetime()

    def update_datetime(self):
        now = QDateTime.currentDateTime()
        date_str = now.toString("dd-MM-yyyy hh:mm:ss")
        time_str = now.toString("hh:mm:ss")
        self.lbl_datetime.setText(f"Tanggal / Jam: {date_str}")
        self.lbl_bottom_time.setText(f"Jam sekarang: {time_str}")

    def refresh_ports(self, auto_connect=False):
        self.combo_port.clear()
        try:
            import serial.tools.list_ports
            ports = list(serial.tools.list_ports.comports())
            pico = self.serial.find_pico_port(ports) if self.serial else None

            for p in ports:
                self.combo_port.addItem(
                    p.device,
                    p.device
                )

            if pico:
                index = self.combo_port.findData(pico.device)
                if index >= 0:
                    self.combo_port.setCurrentIndex(index)
                if auto_connect and not self.serial.is_connected():
                    self.connect_rp2040()
        except Exception as e:
            self.console.log(f"PORT SCAN ERROR: {e}")

    def toggle_connect(self):
        if self.serial and self.serial.is_connected():
            self.disconnect_rp2040()
        else:
            self.connect_rp2040()

    def connect_rp2040(self):
        if not self.serial:
            return
        port = self.combo_port.currentData() or self.serial.auto_detect()
        if not port:
            self.console.log("RP2040 not found")
            return

        self.console.log(f"Opening {port}...")
        try:
            ok = self.serial.connect(port)
        except Exception as e:
            self.console.log(f"CONNECT ERROR: {e}")
            ok = False

        if ok:
            self.btn_connect.setText("CONNECTED")
            self.btn_connect.setStyleSheet(
                "background-color: #d32f2f; color: white; font-weight: bold;"
            )
            self.console.log(f"RP2040 connected : {port}")
        else:
            self.btn_connect.setText("CONNECT")
            self.btn_connect.setStyleSheet(
                "background-color: #388e3c; color: white; font-weight: bold;"
            )

    def disconnect_rp2040(self):
        try:
            self.serial.disconnect(silent=True)
        except Exception:
            try:
                self.serial.disconnect()
            except Exception:
                pass
        self.btn_connect.setText("CONNECT")
        self.btn_connect.setStyleSheet(
            "background-color: #388e3c; color: white; font-weight: bold;"
        )

    def on_serial_disconnect(self):
        self.btn_connect.setText("CONNECT")
        self.btn_connect.setStyleSheet(
            "background-color: #388e3c; color: white; font-weight: bold;"
        )

    def main_identify(self):
        if self.serial and not self.serial.is_connected():
            self.console.log("IDENTIFY: RP2040 is not connected")
            return
        self.identify_sequence = True
        self.tabs.setCurrentWidget(self.identify)
        try:
            self.emmc.identify()
        except Exception as e:
            self.identify_sequence = False
            self.console.log(f"IDENTIFY ERROR: {e}")

    def main_gpt(self):
        if self.serial and not self.serial.is_connected():
            self.console.log("READ GPT: RP2040 is not connected")
            return
        self.tabs.setCurrentWidget(self.userarea)
        try:
            self.userarea.scanGPT()
        except Exception as e:
            self.console.log(f"READ GPT ERROR: {e}")

    def main_main_read_gpt(self):
        self.main_gpt()

    def handle_serial_data(self, packet):
        if not isinstance(packet, dict):
            return

        kind = packet.get("type", "")

        if kind == "emmc.identify.result":
            if self.identify_sequence:
                self.identify_sequence = False
                if packet.get("ok", False):
                    self.main_gpt()
                else:
                    self.console.log("IDENTIFY failed - GPT not started")

        if kind == "emmc.health.result":
            self.console.log(f"[HEALTH DATA] {packet.get('data', 'OK')}")

    def closeEvent(self, event):
        try:
            self.clock_timer.stop()
        except Exception:
            pass
        try:
            if self.serial and self.serial.is_connected():
                self.serial.disconnect()
        except Exception:
            pass
        event.accept()
