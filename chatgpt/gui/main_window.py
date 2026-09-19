import sys
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QTextEdit, QProgressBar, QTabWidget, QSplitter
)
from PyQt6.QtCore import QTimer, QDateTime, Qt

# VISUAL SOURCE OF TRUTH: yraa99/gui
from gui.tabs.main_tab import MainTab
from gui.tabs.userarea_tab import UserAreaTab
from gui.tabs.adb_fastboot_tab import ADBFastbootTab
from gui.tabs.factory_image_tab import FactoryImageTab

# FUNCTIONAL SOURCE OF TRUTH: pico-emmc-beta
from gui.identify import IdentifyTab
from gui.boot_extcsd import BootExtCSDTab
from gui.userarea import UserAreaTab as BetaUserAreaTab
from gui.health import HealthTab
from gui.special_task import SpecialTaskTab
from gui.isp_test import ISPTestTab
from gui.adb_fastboot import ADBFastbootTab as BetaADBFastbootTab
from gui.factory_image import FactoryImageTab as BetaFactoryImageTab


class ConsoleLogger:
    def __init__(self, text_widget):
        self.widget = text_widget

    def log(self, message):
        timestamp = QDateTime.currentDateTime().toString("hh:mm:ss")
        self.widget.append(f"[{timestamp}] {message}")


class MainWindow(QMainWindow):
    """
    Active visual widgets are the yraa99/gui widgets, in the same four-tab
    structure and layout.

    All RP2040/eMMC protocol handling is retained from pico-emmc-beta through
    the beta service objects kept behind this visual shell.
    """

    def __init__(self, emmc_core=None, serial_core=None):
        super().__init__()
        self.emmc = emmc_core
        self.serial = serial_core

        # Beta functional objects. These are the protocol/service handlers;
        # they are deliberately not added as extra top-level tabs.
        self.identify = IdentifyTab(self.emmc, None)
        self.boot = BootExtCSDTab(self.emmc, None)
        self.userarea = BetaUserAreaTab(self.emmc, None)
        self.health = HealthTab(self.emmc, None)
        self.special = SpecialTaskTab(self.emmc, None)
        self.isp = ISPTestTab(self.emmc, None)
        self.adb_backend = BetaADBFastbootTab(None)
        self.factory_backend = BetaFactoryImageTab(None)

        self.setWindowTitle("Pico eMMC Tool - Service Console")
        self.resize(1024, 620)

        self.init_ui()
        self.start_clock_timer()

        # All beta service objects use the same log sink as the active GUI.
        for service in (
            self.identify, self.boot, self.userarea, self.health,
            self.special, self.isp, self.adb_backend, self.factory_backend
        ):
            service.console = self.console

        if self.serial:
            try:
                self.serial.set_disconnect_callback(self.on_serial_disconnect)
            except Exception:
                pass

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # ----------------------------------------------------
        # TOP HEADER — yraa99/gui
        # ----------------------------------------------------
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

        # ----------------------------------------------------
        # SPLITTER — yraa99/gui
        # ----------------------------------------------------
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

        self.console = ConsoleLogger(self.log_text)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Operation Progress: %p%")

        self.lbl_bottom_time = QLabel("Jam sekarang: --:--:--")
        self.lbl_bottom_time.setStyleSheet("font-size: 11px; color: #444;")

        log_layout.addWidget(lbl_log)
        log_layout.addWidget(self.log_text)
        log_layout.addWidget(self.progress_bar)
        log_layout.addWidget(self.lbl_bottom_time)

        # ----------------------------------------------------
        # ACTIVE TOP-LEVEL WIDGETS — yraa99/gui
        # ----------------------------------------------------
        self.tabs = QTabWidget()

        self.tab_main = MainTab(self.emmc)
        self.tab_main.log_signal.connect(self.console.log)
        self.tab_main.progress_signal.connect(self.progress_bar.setValue)

        self.tab_userarea = UserAreaTab()
        self.tab_adb = ADBFastbootTab()
        self.tab_factory = FactoryImageTab()

        self.tabs.addTab(self.tab_main, "MAIN")
        self.tabs.addTab(self.tab_userarea, "USER AREA")
        self.tabs.addTab(self.tab_adb, "ADB Fastboot")
        self.tabs.addTab(self.tab_factory, "Factory Image")

        splitter.addWidget(log_panel)
        splitter.addWidget(self.tabs)
        splitter.setSizes([380, 620])
        main_layout.addWidget(splitter)

        self._wire_beta_functions_to_gui_tabs()
        self.refresh_ports(auto_connect=True)
        self.console.log("Pico eMMC Tool initialized successfully.")

    def _wire_beta_functions_to_gui_tabs(self):
        # MAIN tab: keep the exact yraa99/gui widgets, but route their actions
        # to the beta service implementation instead of placeholder logging.
        try:
            self.tab_main.btn_write.clicked.disconnect()
        except Exception:
            pass
        self.tab_main.btn_write.clicked.connect(self._beta_write)

        button_map = {
            "cmd_emmc_health": self.identify.health_check_clicked,
            "cmd_extcsd_info": self.boot.readExtCSD,
        }
        for name, slot in button_map.items():
            button = getattr(self.tab_main, name, None)
            if button is None:
                continue

            try:
                button.clicked.disconnect()
            except Exception:
                pass
            button.clicked.connect(slot)

        # The beta branch has these SPECIAL TASK controls but they are
        # intentionally disabled because the active firmware does not expose
        # safe implementations. Preserve that state rather than inventing a
        # fake operation.
        for name in (
            "cmd_set_boot_partition", "cmd_partition_config",
            "cmd_rpmb_info", "cmd_factory_reset",
            "cmd_factory_reset_safe", "cmd_frp_reset", "cmd_frp_samsung"
        ):
            button = getattr(self.tab_main, name, None)
            if button is not None:
                button.setEnabled(False)
                button.setToolTip(
                    "Disabled: pico-emmc-beta firmware does not expose this safe protocol."
                )

        # USER AREA: exact visual widget remains active. Its actual GPT/read
        # engine is the beta UserAreaTab. Serial results are mirrored into the
        # visible text box.
        self._userarea_backend_handler = self.userarea.handle_serial_data

        # ADB/FASTBOOT: route the visible yraa99/gui buttons to the beta
        # ADB/Fastboot implementation.
        adb_pairs = (
            ("btn_adb_devices", "scan_adb"),
            ("btn_reboot_bootloader", "bootloader"),
            ("btn_fastboot_devices", "scan_fastboot"),
        )
        for visible_name, backend_name in adb_pairs:
            button = getattr(self.tab_adb, visible_name, None)
            method = getattr(self.adb_backend, backend_name, None)
            if button is not None and method is not None:
                try:
                    button.clicked.disconnect()
                except Exception:
                    pass
                button.clicked.connect(method)

        # FACTORY IMAGE: use the beta factory backend for the actual action.
        # The yraa99/gui file picker remains the visible widget.
        try:
            self.tab_factory.btn_flash.clicked.disconnect()
        except Exception:
            pass
        self.tab_factory.btn_flash.clicked.connect(
            lambda: self.factory_backend.flash_disabled()
        )

    def _beta_write(self):
        # yraa99/gui exposes WRITE; pico-emmc-beta has no active safe write
        # protocol. Do not report a false success.
        self.console.log("WRITE disabled: pico-emmc-beta has no active safe eMMC write protocol.")

    def refresh_ports(self, auto_connect=True):
        self.combo_port.clear()
        try:
            import serial.tools.list_ports
            ports = list(serial.tools.list_ports.comports())
            pico = self.serial.find_pico_port(ports) if self.serial else None

            for p in ports:
                self.combo_port.addItem(p.device, p.device)

            if pico:
                index = self.combo_port.findData(pico.device)
                if index >= 0:
                    self.combo_port.setCurrentIndex(index)
                self.console.log(f"Pico USB automatically selected: {pico.device}")
                if auto_connect and self.serial and not self.serial.is_connected():
                    self.console.log(f"Pico USB automatically connecting: {pico.device}")
                    self.toggle_connect()
        except Exception as e:
            self.console.log(f"Serial port scan error: {e}")

        self.console.log("Serial port list refreshed.")

    def toggle_connect(self):
        if self.serial and self.serial.is_connected():
            self.serial.disconnect()
            self.btn_connect.setText("CONNECT")
            self.btn_connect.setStyleSheet(
                "background-color: #388e3c; color: white; font-weight: bold;"
            )
            self.console.log("Disconnected from port.")
            return

        port = self.combo_port.currentData() or (
            self.serial.auto_detect() if self.serial else None
        )
        if not port:
            self.console.log("RP2040 not found")
            return

        if self.serial and self.serial.connect(port):
            self.btn_connect.setText("CONNECTED")
            self.btn_connect.setStyleSheet(
                "background-color: #d32f2f; color: white; font-weight: bold;"
            )
            self.console.log(f"RP2040 connected : {port}")
        else:
            self.console.log(f"Connection failed: {port}")

    def on_serial_disconnect(self):
        self.btn_connect.setText("CONNECT")
        self.btn_connect.setStyleSheet(
            "background-color: #388e3c; color: white; font-weight: bold;"
        )

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

    def handle_serial_data(self, packet):
        if not isinstance(packet, dict):
            return

        # Keep beta IDENTIFY -> GPT behavior.
        kind = packet.get("type", "")
        if kind == "emmc.identify.result":
            if packet.get("ok", False):
                self.console.log("IDENTIFY OK - beta service result received")
            else:
                self.console.log(
                    "IDENTIFY ERROR: " + str(packet.get("msg", "unknown error"))
                )

        # Mirror useful beta USER AREA data into the active GUI tab without
        # replacing its widgets.
        if kind in (
            "emmc.gpt.begin", "emmc.gpt.partition", "emmc.gpt.end",
            "emmc.buildprop.begin", "emmc.buildprop.result",
            "emmc.buildprop.end"
        ):
            text = self._format_userarea_packet(packet)
            if text:
                self.tab_userarea.text.append(text)

    def _format_userarea_packet(self, packet):
        kind = packet.get("type", "")
        if kind == "emmc.gpt.begin":
            return "Reading GPT..."
        if kind == "emmc.gpt.partition":
            return (
                f"GPT: {packet.get('name', '')} | "
                f"LBA={packet.get('start_lba', 0)} | "
                f"sectors={packet.get('sectors', 0)}"
            )
        if kind == "emmc.gpt.end":
            return "GPT scan complete."
        if kind == "emmc.buildprop.begin":
            return f"build.prop: reading {packet.get('partition', 'Android')}..."
        if kind == "emmc.buildprop.result":
            return "build.prop: found."
        if kind == "emmc.buildprop.end":
            return "build.prop: read complete. Details are available in LOG."
        return ""

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
