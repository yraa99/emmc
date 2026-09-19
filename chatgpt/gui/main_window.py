from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QSplitter, QGroupBox, QComboBox, QProgressBar,
    QSizePolicy, QGridLayout
)
from PyQt6.QtCore import Qt, QTimer

from gui.console import Console
from gui.identify import IdentifyTab
from gui.boot_extcsd import BootExtCSDTab
from gui.userarea import UserAreaTab
from gui.health import HealthTab
from gui.special_task import SpecialTaskTab
from gui.isp_test import ISPTestTab
from gui.adb_fastboot import ADBFastbootTab
from gui.factory_image import FactoryImageTab


class MainWindow(QMainWindow):
    """Professional eMMC service dashboard.

    The outer layout follows the user's sketch:
      MAIN | FLASH | ADB FASTBOOT
      left console/log + right service workspace
      partition map is presented by USER AREA.
    """

    def __init__(self, emmc, serial):
        super().__init__()
        self.emmc = emmc
        self.serial = serial
        self.last_pico_device = None
        self.identify_sequence = False

        self.operation_timer = QTimer(self)
        self.operation_timer.setSingleShot(True)
        self.operation_timer.timeout.connect(self.operation_timeout)

        self.setWindowTitle("RP2040 eMMC PROGRAMMER By YADITAMA")
        self.resize(1280, 800)
        self.setMinimumSize(1000, 650)

        self.console = Console()
        self.setupUI()

        self.serial.set_disconnect_callback(self.on_serial_disconnect)
        self.refresh_device(auto_connect=True)

        self.watchdog = QTimer(self)
        self.watchdog.timeout.connect(self.check_connection)
        self.watchdog.start(1000)

        # One central rule for the log: a new user command starts a fresh
        # result block. Automatic follow-up commands (IDENTIFY -> GPT) do not
        # clear the log because they are part of the same operation.
        self._install_command_log_reset()

    def setupUI(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        title = QLabel("RP2040 eMMC PROGRAMMER")
        title.setObjectName("title")
        subtitle = QLabel("eMMC Service Tool • YADITAMA")
        subtitle.setObjectName("subtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()

        self.rp_status = QLabel("RP2040 : DISCONNECTED")
        self.rp_status.setObjectName("status_disconnected")
        header.addWidget(self.rp_status)
        root.addLayout(header)

        connection = QGroupBox("PICO eMMC CONNECTION")
        conn = QHBoxLayout(connection)
        conn.setContentsMargins(8, 6, 8, 6)
        conn.setSpacing(6)
        conn.addWidget(QLabel("PORT"))
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(180)
        self.port_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_refresh = QPushButton("REFRESH")
        self.btn_connect = QPushButton("CONNECT")
        self.connection_status = QLabel("DISCONNECTED")
        self.connection_status.setObjectName("status_disconnected")
        conn.addWidget(self.port_combo)
        conn.addWidget(self.btn_refresh)
        conn.addWidget(self.btn_connect)
        conn.addWidget(self.connection_status)
        self.btn_refresh.clicked.connect(self.refresh_device)
        self.btn_connect.clicked.connect(self.toggle_connection)
        root.addWidget(connection)

        # The three large sections in the sketch.
        self.category_tabs = QTabWidget()
        self.category_tabs.setObjectName("categoryTabs")

        self.main_page = self._build_main_page()
        self.flash_page = self._build_flash_page()
        self.adb_page = self._build_adb_page()

        self.category_tabs.addTab(self.main_page, "MAIN")
        self.category_tabs.addTab(self.flash_page, "FLASH")
        self.category_tabs.addTab(self.adb_page, "ADB FASTBOOT")
        root.addWidget(self.category_tabs, 1)

        operation = QGroupBox("PROCESS")
        op = QHBoxLayout(operation)
        op.setContentsMargins(8, 5, 8, 5)
        self.operation_label = QLabel("Ready")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.btn_cancel = QPushButton("CANCEL")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setMinimumWidth(100)
        op.addWidget(self.operation_label)
        op.addWidget(self.progress, 1)
        op.addWidget(self.btn_cancel)
        self.btn_cancel.clicked.connect(self.cancel_operation)
        root.addWidget(operation)

        footer = QHBoxLayout()
        self.footer_status = QLabel("Ready")
        self.theme_button = QPushButton("Dark / Light")
        self.theme_button.setMinimumWidth(110)
        self.theme_button.clicked.connect(self.toggle_theme)
        footer.addWidget(self.footer_status)
        footer.addStretch()
        footer.addWidget(QLabel("Special task"))
        footer.addSpacing(12)
        footer.addWidget(self.theme_button)
        root.addLayout(footer)

        self.apply_style()

    def _button(self, text, min_width=110):
        b = QPushButton(text)
        b.setObjectName("serviceButton")
        b.setMinimumHeight(32)
        b.setMinimumWidth(min_width)
        b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return b

    def _build_main_page(self):
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(4, 4, 4, 4)
        page_layout.setSpacing(6)

        work = QSplitter(Qt.Orientation.Horizontal)
        work.setChildrenCollapsible(False)
        work.setHandleWidth(6)

        log_box = QGroupBox("LOG / RESULT")
        log_layout = QVBoxLayout(log_box)
        log_layout.setContentsMargins(5, 5, 5, 5)
        log_layout.addWidget(self.console)
        log_box.setMinimumWidth(260)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        quick = QGroupBox("eMMC MAIN")
        grid = QGridLayout(quick)
        grid.setContentsMargins(8, 7, 8, 7)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(5)

        self.btn_main_identify = self._button("IDENTIFY")
        self.btn_main_gpt = self._button("READ GPT")
        self.btn_main_user = self._button("USER AREA")
        self.btn_main_boot1 = self._button("BOOT 1")
        self.btn_main_boot2 = self._button("BOOT 2")
        self.btn_main_ext = self._button("EXT_CSD")
        self.btn_main_health = self._button("HEALTH CHECK")
        self.btn_main_special = self._button("SPECIAL TASK")

        buttons = [
            self.btn_main_identify, self.btn_main_boot1, self.btn_main_boot2,
            self.btn_main_ext, self.btn_main_user, self.btn_main_gpt,
            self.btn_main_health, self.btn_main_special
        ]
        for idx, button in enumerate(buttons):
            grid.addWidget(button, idx // 4, idx % 4)

        self.btn_main_identify.clicked.connect(self.main_identify)
        self.btn_main_gpt.clicked.connect(self.main_gpt)
        self.btn_main_user.clicked.connect(lambda: self.service_tabs.setCurrentWidget(self.userarea))
        self.btn_main_boot1.clicked.connect(lambda: self.service_tabs.setCurrentWidget(self.boot))
        self.btn_main_boot2.clicked.connect(lambda: self.service_tabs.setCurrentWidget(self.boot))
        self.btn_main_ext.clicked.connect(lambda: self.service_tabs.setCurrentWidget(self.boot))
        self.btn_main_health.clicked.connect(lambda: self.service_tabs.setCurrentWidget(self.identify))
        self.btn_main_special.clicked.connect(lambda: self.service_tabs.setCurrentWidget(self.special))

        right_layout.addWidget(quick)

        self.service_tabs = QTabWidget()
        self.service_tabs.setObjectName("serviceTabs")

        self.identify = IdentifyTab(self.emmc, self.console)
        self.boot = BootExtCSDTab(self.emmc, self.console)
        self.userarea = UserAreaTab(self.emmc, self.console)
        self.health = HealthTab(self.emmc, self.console)
        self.special = SpecialTaskTab(self.emmc, self.console)
        self.isp = ISPTestTab(self.emmc, self.console)

        self.service_tabs.addTab(self.identify, "IDENTIFY")
        self.service_tabs.addTab(self.boot, "BOOT / EXT_CSD")
        self.service_tabs.addTab(self.userarea, "USER AREA")
        self.service_tabs.addTab(self.health, "HEALTH")
        self.service_tabs.addTab(self.special, "SPECIAL TASK")
        self.service_tabs.addTab(self.isp, "ISP TEST")

        right_layout.addWidget(self.service_tabs, 1)

        work.addWidget(log_box)
        work.addWidget(right)
        work.setSizes([340, 740])
        work.setStretchFactor(0, 3)
        work.setStretchFactor(1, 7)

        page_layout.addWidget(work, 1)
        return page

    def _build_flash_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(FactoryImageTab(self.console))
        return page

    def _build_adb_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        self.adb_fastboot = ADBFastbootTab(self.console)
        layout.addWidget(self.adb_fastboot)
        return page

    def _install_command_log_reset(self):
        # pressed() fires before clicked(), so the result generated by the
        # command remains the only content in the console.
        for button in self.findChildren(QPushButton):
            if button is self.btn_cancel or button is self.theme_button:
                continue
            button.pressed.connect(self._clear_log_for_new_command)

    def _clear_log_for_new_command(self):
        sender = self.sender()
        if isinstance(sender, QPushButton):
            text = sender.text().upper()
            # Pure navigation controls do not represent a new hardware read.
            if text in {"USER AREA", "BOOT 1", "BOOT 2", "EXT_CSD", "SPECIAL TASK", "DARK / LIGHT"}:
                return
        self.console.clear()

    def apply_style(self):
        self.setStyleSheet("""
        QMainWindow, QWidget {
            background: #111417;
            color: #d7dde2;
            font-family: Segoe UI;
            font-size: 10pt;
        }
        QLabel { color: #d7dde2; }
        QLabel#title {
            color: #f0f3f5;
            font-size: 19pt;
            font-weight: bold;
        }
        QLabel#subtitle {
            color: #7f8a93;
            font-size: 9pt;
        }
        QLabel#status_disconnected {
            color: #d66a6a;
            font-weight: bold;
        }
        QGroupBox {
            border: 1px solid #30373d;
            border-radius: 5px;
            margin-top: 8px;
            padding-top: 7px;
            font-weight: bold;
            color: #aeb8c0;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 9px;
            padding: 0 5px;
            color: #9da8b0;
        }
        QPushButton {
            background: #20262b;
            border: 1px solid #3b444b;
            border-radius: 4px;
            padding: 5px 10px;
            color: #dce2e6;
            min-height: 29px;
            max-height: 34px;
        }
        QPushButton#serviceButton {
            font-weight: bold;
        }
        QPushButton:hover {
            background: #2b3339;
            border-color: #68757e;
        }
        QPushButton:pressed { background: #171c20; }
        QPushButton:disabled {
            color: #596168;
            background: #171b1e;
            border-color: #292e32;
        }
        QComboBox {
            background: #181d21;
            border: 1px solid #3a434a;
            border-radius: 4px;
            padding: 5px 8px;
            min-height: 27px;
        }
        QTabWidget::pane {
            border: 1px solid #30373d;
            background: #151a1e;
        }
        QTabBar::tab {
            background: #1b2024;
            border: 1px solid #30373d;
            padding: 8px 14px;
            margin-right: 2px;
            color: #8f9aa3;
        }
        QTabBar::tab:selected {
            background: #30383f;
            color: #ffffff;
        }
        QSplitter::handle { background: #30383e; }
        QSplitter::handle:hover { background: #59656e; }
        QProgressBar {
            border: 1px solid #30373d;
            border-radius: 4px;
            background: #181d21;
            text-align: center;
            min-height: 19px;
        }
        QProgressBar::chunk {
            background: #46535d;
            border-radius: 3px;
        }
        QTableWidget {
            background: #151a1e;
            alternate-background-color: #1b2024;
            gridline-color: #30373d;
            selection-background-color: #303c45;
        }
        QHeaderView::section {
            background: #20272c;
            color: #cdd5da;
            padding: 6px;
            border: 1px solid #30373d;
            font-weight: bold;
        }
        """)

    def toggle_theme(self):
        # Keep the service-tool palette stable; this is a deliberate UI
        # toggle for future light theme work rather than changing controls
        # unexpectedly during hardware operations.
        self.console.log("Theme: dark service-tool mode")

    def refresh_device(self, auto_connect=True):
        self.port_combo.clear()
        try:
            import serial.tools.list_ports
            ports = list(serial.tools.list_ports.comports())
            pico_port = self.serial.find_pico_port(ports)
            for port in ports:
                description = port.description or "Unknown Device"
                is_pico = pico_port is not None and port.device == pico_port.device
                prefix = "PICO USB - " if is_pico else ""
                self.port_combo.addItem(f"{prefix}{port.device} - {description}", port.device)
            if pico_port:
                self.last_pico_device = pico_port.device
                self.port_combo.setCurrentIndex(self.port_combo.findData(pico_port.device))
                if auto_connect and not self.serial.is_connected():
                    self.connect_rp2040()
            if self.port_combo.count() == 0:
                self.port_combo.addItem("No COM port detected", None)
                self.last_pico_device = None
        except Exception as e:
            self.console.log(f"PORT SCAN ERROR: {e}")

    def toggle_connection(self):
        if self.serial.is_connected():
            self.disconnect_rp2040()
        else:
            self.connect_rp2040()

    def connect_rp2040(self):
        if self.serial.is_connected():
            return
        port = self.port_combo.currentData()
        if not port:
            try:
                port = self.serial.auto_detect()
            except Exception as e:
                self.console.log(f"AUTO DETECT ERROR: {e}")
                port = None
        if not port:
            self.set_disconnected("RP2040 not found")
            return
        try:
            connected = self.serial.connect(port)
        except Exception as e:
            self.console.log(f"CONNECT ERROR: {e}")
            connected = False
        if connected:
            self.set_connected(port)
        else:
            self.set_disconnected(f"Cannot open {port}")

    def disconnect_rp2040(self):
        try:
            self.serial.disconnect(silent=True)
        except Exception as e:
            self.console.log(f"DISCONNECT ERROR: {e}")
        self.set_disconnected()

    def set_connected(self, port):
        self.rp_status.setText(f"RP2040 : CONNECTED ({port})")
        self.connection_status.setText("CONNECTED")
        self.connection_status.setObjectName("status_connected")
        self.connection_status.setStyleSheet("color:#72c48b;font-weight:bold;")
        self.btn_connect.setText("DISCONNECT")
        self.footer_status.setText(f"Connected to {port}")

    def set_disconnected(self, message=None):
        self.rp_status.setText("RP2040 : DISCONNECTED")
        self.connection_status.setText("DISCONNECTED")
        self.connection_status.setObjectName("status_disconnected")
        self.connection_status.setStyleSheet("color:#d66a6a;font-weight:bold;")
        self.btn_connect.setText("CONNECT")
        self.footer_status.setText("Ready")
        if message:
            self.console.log(message)
        self.operation_timer.stop()
        self.btn_cancel.setEnabled(False)
        try:
            self.isp.finish()
        except Exception:
            pass

    def check_connection(self):
        try:
            if self.serial.is_connected() and not self.serial.port_exists():
                self.serial.disconnect()
                return
            if not self.serial.is_connected():
                if self.connection_status.text() != "DISCONNECTED":
                    self.set_disconnected()
                self.detect_new_pico()
        except Exception:
            pass

    def detect_new_pico(self):
        pico_port = self.serial.find_pico_port()
        pico_device = pico_port.device if pico_port else None
        if not pico_device:
            self.last_pico_device = None
            return
        if pico_device != self.last_pico_device:
            self.last_pico_device = pico_device
            self.refresh_device(auto_connect=True)

    def on_serial_disconnect(self):
        self.set_disconnected("RP2040 disconnected")

    def start_operation(self, timeout_ms=5000):
        self.btn_cancel.setEnabled(True)
        self.progress.setValue(0)
        self.operation_label.setText("Operation running...")
        self.footer_status.setText("Operation running")
        self.operation_timer.start(timeout_ms)

    def operation_timeout(self):
        self.operation_label.setText("Operation timeout")
        self.footer_status.setText("Timeout")
        self.btn_cancel.setEnabled(False)

    def cancel_operation(self):
        try:
            self.emmc.stop_tests()
        except Exception:
            pass
        self.operation_timer.stop()
        self.btn_cancel.setEnabled(False)
        self.operation_label.setText("Operation cancelled")
        self.footer_status.setText("Ready")
        try:
            self.isp.finish()
        except Exception:
            pass

    def command_init(self):
        self.start_operation()
        try:
            self.emmc.init()
        except Exception as e:
            self.operation_timer.stop()
            self.btn_cancel.setEnabled(False)
            self.console.log(f"INIT ERROR: {e}")

    def command_detect(self):
        self.service_tabs.setCurrentWidget(self.identify)

    def command_identify(self):
        self.main_identify()

    def command_read_cid(self):
        self.service_tabs.setCurrentWidget(self.identify)

    def main_identify(self):
        if not self.serial.is_connected():
            self.console.log("IDENTIFY: RP2040 is not connected")
            return
        self.identify_sequence = True
        self.service_tabs.setCurrentWidget(self.identify)
        try:
            self.emmc.identify()
            self.operation_label.setText("Reading eMMC identification...")
            self.footer_status.setText("Identify")
        except Exception as e:
            self.identify_sequence = False
            self.console.log(f"IDENTIFY ERROR: {e}")

    def main_gpt(self):
        if not self.serial.is_connected():
            self.console.log("READ GPT: RP2040 is not connected")
            return
        self.service_tabs.setCurrentWidget(self.userarea)
        try:
            self.userarea.scanGPT()
            self.operation_label.setText("Reading GPT + system information...")
            self.footer_status.setText("GPT / System")
        except Exception as e:
            self.console.log(f"READ GPT ERROR: {e}")

    def main_health(self):
        self.service_tabs.setCurrentWidget(self.identify)
        self.identify.health_check_clicked()

    def handle_serial_data(self, obj):
        if not isinstance(obj, dict):
            return
        typ = obj.get("type")
        if typ == "emmc.identify.result":
            self.operation_label.setText("Identify complete" if obj.get("ok") else "Identify failed")
            self.footer_status.setText("Ready")
            if self.identify_sequence:
                self.identify_sequence = False
                if obj.get("ok", False):
                    self.main_gpt()
        elif typ == "emmc.gpt.end":
            self.operation_label.setText("GPT + system information complete" if obj.get("ok", True) else "GPT failed")
            self.footer_status.setText("Ready")
        elif typ == "emmc.layout.result":
            self.operation_label.setText("eMMC health / EXT_CSD complete" if obj.get("ok") else "Health read failed")

    def closeEvent(self, event):
        try:
            self.operation_timer.stop()
            self.watchdog.stop()
        except Exception:
            pass
        try:
            if self.serial.is_connected():
                self.serial.disconnect()
        except Exception:
            pass
        event.accept()
