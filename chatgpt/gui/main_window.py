from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QSplitter,
    QGroupBox,
    QComboBox,
    QProgressBar,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer

from gui.console import Console
from gui.identify import IdentifyTab
from gui.boot_extcsd import BootExtCSDTab
from gui.userarea import UserAreaTab
from gui.health import HealthTab
from gui.special_task import SpecialTaskTab
from gui.adb_fastboot import ADBFastbootTab
from gui.isp_test import ISPTestTab


class MainWindow(QMainWindow):
    def __init__(self, emmc, serial):
        super().__init__()

        self.emmc = emmc
        self.serial = serial
        self.last_pico_device = None

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

    # ==========================================================
    # MAIN UI
    # ==========================================================

    def setupUI(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # ======================================================
        # HEADER
        # ======================================================

        header = QHBoxLayout()

        title_layout = QVBoxLayout()
        title_layout.setSpacing(1)

        title = QLabel("RP2040 eMMC PROGRAMMER By YADITAMA")
        title.setObjectName("title")

        subtitle = QLabel("eMMC Service Tool")
        subtitle.setObjectName("subtitle")

        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)

        header.addLayout(title_layout)
        header.addStretch()

        main_layout.addLayout(header)

        # ======================================================
        # DEVICE CONNECTION
        # ======================================================

        connection_group = QGroupBox("DEVICE CONNECTION")

        connection_layout = QHBoxLayout(connection_group)
        connection_layout.setContentsMargins(10, 8, 10, 8)
        connection_layout.setSpacing(8)

        port_label = QLabel("PORT")

        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(180)
        self.port_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        self.btn_refresh = QPushButton("REFRESH")
        self.btn_connect = QPushButton("CONNECT")
        self.btn_connect.setMinimumWidth(110)

        self.connection_status = QLabel("DISCONNECTED")
        self.connection_status.setObjectName("status_disconnected")

        connection_layout.addWidget(port_label)
        connection_layout.addWidget(self.port_combo)
        connection_layout.addWidget(self.btn_refresh)
        connection_layout.addWidget(self.btn_connect)
        connection_layout.addWidget(self.connection_status)

        connection_layout.addStretch()

        self.btn_refresh.clicked.connect(self.refresh_device)
        self.btn_connect.clicked.connect(self.toggle_connection)

        main_layout.addWidget(connection_group)

        # ======================================================
        # MAIN WORK AREA
        #
        # LEFT  = CONSOLE / LOG 30%
        # RIGHT = SERVICE FUNCTIONS 70%
        #
        # QSplitter dapat digeser manual oleh user.
        # ======================================================

        self.work_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.work_splitter.setChildrenCollapsible(False)
        self.work_splitter.setHandleWidth(8)

        # ------------------------------------------------------
        # LEFT : CONSOLE / LOG
        # ------------------------------------------------------

        console_group = QGroupBox("CONSOLE / LOG")

        console_layout = QVBoxLayout(console_group)
        console_layout.setContentsMargins(6, 6, 6, 6)

        console_layout.addWidget(self.console)

        console_group.setMinimumWidth(250)

        # ------------------------------------------------------
        # RIGHT : eMMC SERVICE FUNCTIONS
        # ------------------------------------------------------

        service_group = QGroupBox("eMMC SERVICE FUNCTIONS")
        service_group.setMinimumWidth(450)

        service_layout = QVBoxLayout(service_group)
        service_layout.setContentsMargins(6, 6, 6, 6)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(False)
        self.tabs.setMovable(False)
        self.tabs.setUsesScrollButtons(True)

        # ------------------------------------------------------
        # ALL EXISTING SERVICE TABS
        # ------------------------------------------------------

        self.identify = IdentifyTab(
            self.emmc,
            self.console,
        )

        self.boot = BootExtCSDTab(
            self.emmc,
            self.console,
        )

        self.userarea = UserAreaTab(
            self.emmc,
            self.console,
        )

        self.health = HealthTab(
            self.emmc,
            self.console,
        )

        self.special = SpecialTaskTab(
            self.emmc,
            self.console,
        )

        self.adb = ADBFastbootTab(
            self.console,
        )

        self.isp = ISPTestTab(
            self.emmc,
            self.console,
        )

        # ------------------------------------------------------
        # ADD TABS
        # ------------------------------------------------------

        self.tabs.addTab(
            self.identify,
            "IDENTIFY",
        )

        self.tabs.addTab(
            self.boot,
            "BOOT / EXT_CSD",
        )

        self.tabs.addTab(
            self.userarea,
            "USER AREA",
        )

        self.tabs.addTab(
            self.health,
            "HEALTH",
        )

        self.tabs.addTab(
            self.special,
            "SPECIAL TASK",
        )

        self.tabs.addTab(
            self.adb,
            "ADB / FASTBOOT",
        )

        self.tabs.addTab(
            self.isp,
            "ISP TEST",
        )

        service_layout.addWidget(self.tabs)

        # ------------------------------------------------------
        # ADD TO SPLITTER
        # ------------------------------------------------------

        self.work_splitter.addWidget(console_group)
        self.work_splitter.addWidget(service_group)

        # Default 30% : 70%
        self.work_splitter.setSizes([300, 700])
        # User can drag the splitter freely, including to 50:50.
        self.work_splitter.setStretchFactor(0, 3)
        self.work_splitter.setStretchFactor(1, 7)


        main_layout.addWidget(
            self.work_splitter,
            1,
        )

        # ======================================================
        # OPERATION / PROGRESS
        # ======================================================

        operation_group = QGroupBox("OPERATION / PROGRESS")

        operation_layout = QHBoxLayout(operation_group)
        operation_layout.setContentsMargins(10, 8, 10, 8)

        self.operation_label = QLabel("Ready")

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)

        operation_layout.addWidget(
            self.operation_label,
        )

        operation_layout.addWidget(
            self.progress,
            1,
        )

        main_layout.addWidget(operation_group)

        # ======================================================
        # FOOTER
        # ======================================================

        footer = QHBoxLayout()

        self.footer_status = QLabel("Ready")

        self.rp_status = QLabel(
            "RP2040 : DISCONNECTED"
        )

        self.btn_cancel = QPushButton("CANCEL")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setMinimumWidth(100)

        footer.addWidget(
            self.footer_status,
        )

        footer.addStretch()

        footer.addWidget(
            self.btn_cancel,
        )

        footer.addSpacing(15)

        footer.addWidget(
            self.rp_status,
        )

        footer.addSpacing(10)

        footer.addWidget(
            QLabel("RP2040 • eMMC"),
        )

        self.btn_cancel.clicked.connect(
            self.cancel_operation
        )

        main_layout.addLayout(footer)

        # ======================================================
        # STYLE
        # ======================================================

        self.apply_style()

    # ==========================================================
    # STYLE
    # ==========================================================

    def apply_style(self):
        self.setStyleSheet(
            """
            QMainWindow {
                background-color: #111417;
                color: #d7dde2;
            }

            QWidget {
                background-color: #111417;
                color: #d7dde2;
                font-family: Segoe UI;
                font-size: 10pt;
            }

            QLabel {
                color: #d7dde2;
            }

            QLabel#title {
                color: #f0f3f5;
                font-size: 20pt;
                font-weight: bold;
            }

            QLabel#subtitle {
                color: #7f8a93;
                font-size: 9pt;
            }

            QLabel#status_disconnected {
                color: #d66a6a;
                font-weight: bold;
                padding-left: 10px;
            }

            QGroupBox {
                border: 1px solid #30373d;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 8px;
                font-weight: bold;
                color: #aeb8c0;
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 6px;
                color: #9da8b0;
            }

            QPushButton {
                background-color: #20262b;
                border: 1px solid #3b444b;
                border-radius: 4px;
                padding: 5px 12px;
                color: #dce2e6;
                min-width: 100px;
                min-height: 30px;
                max-height: 32px;
            }

            QPushButton:hover {
                background-color: #293137;
                border-color: #56616a;
            }

            QPushButton:pressed {
                background-color: #171c20;
            }

            QPushButton:disabled {
                color: #596168;
                background-color: #171b1e;
                border-color: #292e32;
            }

            QComboBox {
                background-color: #181d21;
                border: 1px solid #3a434a;
                border-radius: 4px;
                padding: 6px 8px;
                color: #dce2e6;
                min-height: 28px;
            }

            QComboBox:hover {
                border-color: #56616a;
            }

            QComboBox QAbstractItemView {
                background-color: #181d21;
                color: #dce2e6;
                border: 1px solid #3a434a;
                selection-background-color: #303940;
                selection-color: #ffffff;
            }

            QTabWidget::pane {
                border: 1px solid #30373d;
                background-color: #151a1e;
                top: -1px;
            }

            QTabBar::tab {
                background-color: #1b2024;
                border: 1px solid #30373d;
                border-bottom: none;
                padding: 8px 13px;
                margin-right: 2px;
                color: #8f9aa3;
            }

            QTabBar::tab:hover {
                background-color: #252c31;
                color: #cbd2d7;
            }

            QTabBar::tab:selected {
                background-color: #30383f;
                color: #ffffff;
                border-color: #4a555e;
            }

            QSplitter::handle {
                background-color: #30383e;
            }

            QSplitter::handle:hover {
                background-color: #59656e;
            }

            QSplitter::handle:horizontal {
                width: 5px;
            }

            QProgressBar {
                border: 1px solid #30373d;
                border-radius: 4px;
                background-color: #181d21;
                text-align: center;
                color: #d7dde2;
                min-height: 20px;
            }

            QProgressBar::chunk {
                background-color: #46535d;
                border-radius: 3px;
            }
            """
        )

    # ==========================================================
    # DEVICE REFRESH
    # ==========================================================

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

                self.port_combo.addItem(
                    f"{prefix}{port.device} - {description}",
                    port.device,
                )

            if pico_port:
                self.last_pico_device = pico_port.device
                pico_index = self.port_combo.findData(pico_port.device)
                self.port_combo.setCurrentIndex(pico_index)
                self.console.log(
                    f"Pico USB automatically selected: {pico_port.device}"
                )
                if auto_connect and not self.serial.is_connected():
                    self.console.log(
                        f"Pico USB automatically connecting: {pico_port.device}"
                    )
                    self.connect_rp2040()

            if self.port_combo.count() == 0:
                self.port_combo.addItem(
                    "No COM port detected",
                    None,
                )
                self.last_pico_device = None

        except Exception as e:
            self.console.log(
                f"PORT SCAN ERROR: {e}"
            )

    # ==========================================================
    # CONNECT RP2040
    # ==========================================================

    def toggle_connection(self):
        if self.serial.is_connected():
            self.disconnect_rp2040()
        else:
            self.connect_rp2040()

    def disconnect_rp2040(self):
        """Disconnect the selected Pico without closing the application."""
        try:
            self.serial.disconnect(silent=True)
        except Exception as e:
            self.console.log(f"DISCONNECT ERROR: {e}")
        self.set_disconnected("RP2040 disconnected by user")

    def connect_rp2040(self):
        if self.serial.is_connected():
            return

        self.console.log(
            "Scanning RP2040..."
        )

        # ------------------------------------------------------
        # First try selected COM port.
        # ------------------------------------------------------

        port = self.port_combo.currentData()

        # ------------------------------------------------------
        # If no valid selected port, use existing auto_detect()
        # ------------------------------------------------------

        if not port:
            try:
                port = self.serial.auto_detect()
            except Exception as e:
                self.console.log(
                    f"AUTO DETECT ERROR: {e}"
                )
                port = None

        if not port:
            self.set_disconnected(
                "RP2040 not found"
            )
            return

        self.console.log(
            f"Opening {port}..."
        )

        try:
            connected = self.serial.connect(
                port
            )
        except Exception as e:
            self.console.log(
                f"CONNECT ERROR: {e}"
            )
            connected = False

        if connected:
            self.set_connected(port)

            self.console.log(
                "RP2040 connected : " + port
            )

        else:
            self.set_disconnected(
                f"Cannot open {port}"
            )

    # ==========================================================
    # CONNECTED STATE
    # ==========================================================

    def set_connected(self, port):
        self.rp_status.setText(
            f"RP2040 : CONNECTED ({port})"
        )

        self.connection_status.setText(
            "CONNECTED"
        )

        self.connection_status.setObjectName(
            "status_connected"
        )

        self.connection_status.setStyleSheet(
            """
            color: #72c48b;
            font-weight: bold;
            padding-left: 10px;
            """
        )

        self.btn_connect.setText(
            "DISCONNECT"
        )

        self.btn_connect.setEnabled(True)

        self.footer_status.setText(
            f"Connected to {port}"
        )

    # ==========================================================
    # CONNECTION WATCHDOG
    # ==========================================================

    def check_connection(self):
        try:
            if (
                self.serial.is_connected()
                and not self.serial.port_exists()
            ):
                self.serial.disconnect()
                return

            if not self.serial.is_connected():
                if (
                    self.connection_status.text()
                    != "DISCONNECTED"
                ):
                    self.set_disconnected()
                self.detect_new_pico()

        except Exception:
            pass

    def detect_new_pico(self):
        """Connect automatically when a new Pico USB device is plugged in."""
        pico_port = self.serial.find_pico_port()
        pico_device = pico_port.device if pico_port else None

        if not pico_device:
            self.last_pico_device = None
            return

        if pico_device != self.last_pico_device:
            self.console.log(f"New Pico USB detected: {pico_device}")
            self.refresh_device(auto_connect=True)

    # ==========================================================
    # SERIAL DISCONNECT CALLBACK
    # ==========================================================

    def on_serial_disconnect(self):
        self.set_disconnected(
            "RP2040 disconnected"
        )

    # ==========================================================
    # DISCONNECTED STATE
    # ==========================================================

    def set_disconnected(self, message=None):
        self.rp_status.setText(
            "RP2040 : DISCONNECTED"
        )

        self.connection_status.setText(
            "DISCONNECTED"
        )

        self.connection_status.setObjectName(
            "status_disconnected"
        )

        self.connection_status.setStyleSheet(
            """
            color: #d66a6a;
            font-weight: bold;
            padding-left: 10px;
            """
        )

        self.btn_connect.setText(
            "CONNECT"
        )

        self.btn_connect.setEnabled(True)

        self.footer_status.setText(
            "Ready"
        )

        if message:
            self.console.log(
                message
            )

        self.operation_timer.stop()

        self.btn_cancel.setEnabled(
            False
        )

        try:
            self.isp.finish()
        except Exception:
            pass

    # ==========================================================
    # OPERATION CONTROL
    # ==========================================================

    def start_operation(self, timeout_ms=5000):
        self.btn_cancel.setEnabled(
            True
        )

        self.progress.setValue(
            0
        )

        self.operation_label.setText(
            "Operation running..."
        )

        self.footer_status.setText(
            "Operation running"
        )

        self.operation_timer.start(
            timeout_ms
        )

    # ==========================================================
    # OPERATION TIMEOUT
    # ==========================================================

    def operation_timeout(self):
        self.console.log(
            "OPERATION TIMEOUT - no response from RP2040"
        )

        self.operation_label.setText(
            "Operation timeout"
        )

        self.footer_status.setText(
            "Timeout"
        )

        self.btn_cancel.setEnabled(
            False
        )

    # ==========================================================
    # CANCEL OPERATION
    # ==========================================================

    def cancel_operation(self):
        try:
            self.emmc.stop_tests()

            self.console.log(
                "CANCEL REQUEST SENT"
            )

        except Exception as e:
            self.console.log(
                f"CANCEL ERROR: {e}"
            )

        self.operation_timer.stop()

        self.btn_cancel.setEnabled(
            False
        )

        self.operation_label.setText(
            "Operation cancelled"
        )

        self.footer_status.setText(
            "Ready"
        )

        try:
            self.isp.finish()
        except Exception:
            pass

    # ==========================================================
    # COMMAND HELPERS
    #
    # These remain compatible with the previous main_window.py.
    # They do not invent new EMMC backend commands.
    # ==========================================================

    def command_init(self):
        self.console.log(
            "INIT eMMC requested"
        )

        try:
            self.start_operation()

            self.emmc.init()

        except Exception as e:
            self.console.log(
                f"INIT ERROR: {e}"
            )

            self.operation_timer.stop()
            self.btn_cancel.setEnabled(
                False
            )

    def command_detect(self):
        self.console.log(
            "DETECT requested"
        )

        self.tabs.setCurrentWidget(
            self.identify
        )

    def command_identify(self):
        self.console.log(
            "IDENTIFY requested"
        )

        self.tabs.setCurrentWidget(
            self.identify
        )

    def command_read_cid(self):
        self.console.log(
            "READ CID requested"
        )

        self.tabs.setCurrentWidget(
            self.identify
        )

    # ==========================================================
    # WINDOW CLOSE
    # ==========================================================

    def closeEvent(self, event):
        try:
            self.operation_timer.stop()
        except Exception:
            pass

        try:
            self.watchdog.stop()
        except Exception:
            pass

        try:
            if self.serial.is_connected():
                self.serial.disconnect()
        except Exception:
            pass

        event.accept()
