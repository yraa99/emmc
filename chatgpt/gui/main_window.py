import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QTextEdit, QProgressBar, QTabWidget, QSplitter
)
from PyQt6.QtCore import QTimer, QDateTime, Qt

# VISUAL SOURCE OF TRUTH: yraa99/gui
from gui.tabs.main_tab import MainTab
from gui.userarea import UserAreaTab
from gui.adb_fastboot import ADBFastbootTab
from gui.factory_image import FactoryImageTab

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
        self.identify_sequence = False
        self.dark_theme = True

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

        self.setWindowTitle("RP2040 eMMC PROGRAMMER • eMMC Service Tool")
        self.resize(1280, 800)
        self.setMinimumSize(1050, 680)

        self.init_ui()

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
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(4)

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

        self.btn_identify = QPushButton("IDENTIFY")
        self.btn_identify.setObjectName("mainAction")
        self.btn_identify.setToolTip("Run the same IDENTIFY operation used by pico-emmc-beta")
        self.btn_identify.clicked.connect(self.main_identify)

        self.btn_connect.setStyleSheet(
            "background-color: #388e3c; color: white; font-weight: bold;"
        )
        self.btn_connect.clicked.connect(self.toggle_connect)

        self.btn_theme = QPushButton("☀ LIGHT")
        self.btn_theme.clicked.connect(self.toggle_theme)

        header_layout.addWidget(lbl_port)
        header_layout.addWidget(self.combo_port)
        header_layout.addWidget(self.btn_refresh)
        header_layout.addWidget(self.btn_connect)
        header_layout.addWidget(self.btn_identify)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_theme)
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

        log_layout.addWidget(lbl_log)
        log_layout.addWidget(self.log_text)
        log_layout.addWidget(self.progress_bar)

        # ----------------------------------------------------
        # ACTIVE TOP-LEVEL WIDGETS — yraa99/gui
        # ----------------------------------------------------
        self.tabs = QTabWidget()

        self.tab_main = MainTab(self.emmc)
        self.tab_main.log_signal.connect(self.console.log)
        self.tab_main.progress_signal.connect(self.progress_bar.setValue)
        self.tab_main.set_callbacks(
            health=self.main_health,
            extcsd=self.main_extcsd,
            cancel=self.cancel_operation,
            special=self.run_special_task,
            isp_monitor_start=self.main_isp_monitor_start,
            isp_monitor_stop=self.main_isp_monitor_stop,
            isp_cmd=self.main_isp_cmd,
            isp_clk=self.main_isp_clk,
            isp_pins=self.main_isp_pins,
            isp_cmd1=self.main_isp_cmd1,
        )

        # The four visible tabs use the complete beta service widgets.
        self.tab_userarea = BetaUserAreaTab(self.emmc, self.console)
        self.tab_adb = BetaADBFastbootTab(self.console)
        self.tab_factory = BetaFactoryImageTab(self.console)

        self.tabs.addTab(self.tab_main, "MAIN")
        self.tabs.addTab(self.tab_userarea, "USER AREA")
        self.tabs.addTab(self.tab_adb, "ADB Fastboot")
        self.tabs.addTab(self.tab_factory, "Factory Image")

        splitter.addWidget(log_panel)
        splitter.addWidget(self.tabs)
        splitter.setSizes([360, 920])
        main_layout.addWidget(splitter)

        self._wire_beta_functions_to_gui_tabs()
        self.refresh_ports(auto_connect=True)
        self.console.log("Pico eMMC Tool initialized successfully.")

    def _wire_beta_functions_to_gui_tabs(self):
        """Bind visible controls to the same service objects used by beta."""
        # MAIN callbacks are connected explicitly during UI construction.
        # USER AREA / ADB / FACTORY are already the full beta widgets.
        return

    def _beta_write(self):
        self.console.log("WRITE disabled: pico-emmc-beta has no active safe eMMC write protocol.")

    def main_identify(self):
        if not self.serial or not self.serial.is_connected():
            self.console.log("IDENTIFY: RP2040 is not connected")
            return
        self.identify_sequence = True
        self.console.log("IDENTIFY requested")
        try:
            self.identify.identify()
        except Exception as e:
            self.identify_sequence = False
            self.console.log(f"IDENTIFY ERROR: {e}")

    def main_gpt(self):
        if not self.serial or not self.serial.is_connected():
            self.console.log("READ GPT: RP2040 is not connected")
            return
        self.console.log("READ GPT requested")
        try:
            self.progress_bar.setValue(max(self.progress_bar.value(), 70))
            self.operation_label.setText("Scanning GPT / build.prop...")
            self.userarea.scanGPT()
        except Exception as e:
            self.console.log(f"READ GPT ERROR: {e}")

    def main_extcsd(self):
        if not self.serial or not self.serial.is_connected():
            self.console.log("EXT_CSD: RP2040 is not connected")
            return
        self.begin_command("READ EXT_CSD")
        try:
            self.boot.readExtCSD()
            self.progress_bar.setValue(20)
        except Exception as e:
            self.console.log(f"EXT_CSD ERROR: {e}")
            self.finish_operation(False)

    def main_isp_monitor_start(self, frequency):
        self.begin_command("ISP MONITOR")
        try:
            self.isp.frequency.setValue(int(frequency))
            self.isp.run_monitor_start()
        except Exception as e:
            self.console.log(f"ISP ERROR: {e}")
            self.finish_operation(False)

    def main_isp_monitor_stop(self):
        try:
            self.isp.run_monitor_stop()
        finally:
            self.finish_operation(True)

    def main_isp_cmd(self):
        self.begin_command("ISP CMD/CLK TEST")
        try: self.isp.run_cmd()
        except Exception as e: self.console.log(f"ISP ERROR: {e}"); self.finish_operation(False)

    def main_isp_clk(self):
        self.begin_command("ISP CLK WAVE TEST")
        try: self.isp.run_clk_wave()
        except Exception as e: self.console.log(f"ISP ERROR: {e}"); self.finish_operation(False)

    def main_isp_pins(self):
        self.begin_command("ISP CHECK PINS")
        try: self.isp.run_pins()
        except Exception as e: self.console.log(f"ISP ERROR: {e}"); self.finish_operation(False)

    def main_isp_cmd1(self):
        self.begin_command("ISP CMD1 RESPONSE TEST")
        try: self.isp.run_cmd1()
        except Exception as e: self.console.log(f"ISP ERROR: {e}"); self.finish_operation(False)

    def main_health(self):
        if not self.serial or not self.serial.is_connected():
            self.console.log("eMMC HEALTH: RP2040 is not connected")
            return
        self.begin_command("eMMC HEALTH CHECK")
        try:
            self.health.readHealth()
            self.progress_bar.setValue(20)
            self.operation_label.setText("Reading EXT_CSD health...")
            self.footer_status.setText("Health check running")
        except Exception as e:
            self.console.log(f"HEALTH ERROR: {e}")
            self.finish_operation(False)

    def cancel_operation(self):
        try:
            if self.emmc:
                self.emmc.stop_tests()
            self.console.log("CANCEL REQUEST SENT")
        except Exception as e:
            self.console.log(f"CANCEL ERROR: {e}")
        try:
            self.identify.cancel_identify()
        except Exception:
            pass
        try:
            self.isp.finish()
        except Exception:
            pass
        self.identify_sequence = False

    def refresh_ports(self, auto_connect=True):
        self.combo_port.clear()
        try:
            import serial.tools.list_ports
            ports = list(serial.tools.list_ports.comports())
            pico = self.serial.find_pico_port(ports) if self.serial else None

            for p in ports:
                description = p.description or "Unknown Device"
                prefix = "PICO USB - " if pico and p.device == pico.device else ""
                self.combo_port.addItem(f"{prefix}{p.device} - {description}", p.device)

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

    def handle_serial_data(self, packet):
        if not isinstance(packet, dict):
            return

        # Keep the visible dashboard synchronized with beta results.
        self.tab_main.handle_serial_data(packet)

        # Keep beta IDENTIFY -> GPT behavior.
        kind = packet.get("type", "")
        if kind == "emmc.identify.result":
            if packet.get("ok", False):
                self.console.log("IDENTIFY OK - beta service result received")
                if self.identify_sequence:
                    self.identify_sequence = False
                    self.progress_bar.setValue(70)
                    self.operation_label.setText("IDENTIFY OK — reading GPT...")
                    self.main_gpt()
            else:
                self.console.log(
                    "IDENTIFY ERROR: " + str(packet.get("msg", "unknown error"))
                )

    def begin_command(self, label):
        self.log_text.clear()
        self.progress_bar.setValue(0)
        self.operation_label.setText(f"{label} running...")
        self.footer_status.setText(label)
        self.btn_cancel.setEnabled(True)
        self.operation_timer.start(120000)

    def finish_operation(self, success=True):
        self.operation_timer.stop()
        self.btn_cancel.setEnabled(False)
        self.progress_bar.setValue(100 if success else 0)
        self.operation_label.setText("Operation complete" if success else "Operation failed")
        self.footer_status.setText("Ready" if success else "Error")

    def run_special_task(self, command):
        self.begin_command(f"SPECIAL TASK: {command}")
        try:
            self.special.command(command)
            self.finish_operation(True)
        except Exception as e:
            self.console.log(f"SPECIAL TASK ERROR: {e}")
            self.finish_operation(False)

    def toggle_theme(self):
        self.dark_theme = not self.dark_theme
        self.apply_theme()
        self.btn_theme.setText("☀ LIGHT" if self.dark_theme else "🌙 DARK")

    def apply_theme(self):
        if self.dark_theme:
            self.setStyleSheet("QMainWindow,QWidget{background:#111417;color:#d7dde2;font-family:Segoe UI;font-size:10pt;}QLabel{color:#d7dde2;}QGroupBox{border:1px solid #30373d;border-radius:5px;margin-top:7px;padding-top:5px;font-weight:bold;color:#aeb8c0;}QGroupBox::title{subcontrol-origin:margin;left:8px;padding:0 5px;color:#9da8b0;}QPushButton{background:#20262b;border:1px solid #3b444b;border-radius:4px;padding:4px 10px;color:#dce2e6;min-height:28px;}QPushButton:hover{background:#293137;}QPushButton:disabled{color:#596168;background:#171b1e;}QComboBox,QSpinBox{background:#181d21;border:1px solid #3a434a;border-radius:4px;padding:4px 7px;color:#dce2e6;min-height:24px;}QTabWidget::pane{border:1px solid #30373d;background:#151a1e;}QTabBar::tab{background:#1b2024;border:1px solid #30373d;padding:7px 12px;color:#8f9aa3;}QTabBar::tab:selected{background:#30383f;color:#fff;}QSplitter::handle{background:#30383e;width:4px;}QProgressBar{border:1px solid #30373d;border-radius:4px;background:#181d21;text-align:center;color:#d7dde2;min-height:18px;}QProgressBar::chunk{background:#46535d;}")
        else:
            self.setStyleSheet("QMainWindow,QWidget{background:#f2f4f6;color:#20252a;font-family:Segoe UI;font-size:10pt;}QLabel{color:#20252a;}QGroupBox{border:1px solid #c6ccd2;border-radius:5px;margin-top:7px;padding-top:5px;font-weight:bold;color:#4b545c;}QGroupBox::title{subcontrol-origin:margin;left:8px;padding:0 5px;color:#4b545c;background:#f2f4f6;}QPushButton{background:#fff;border:1px solid #b8c0c7;border-radius:4px;padding:4px 10px;color:#20252a;min-height:28px;}QPushButton:hover{background:#e8edf1;}QPushButton:disabled{color:#9aa2a9;background:#e6e9ec;}QComboBox,QSpinBox{background:#fff;border:1px solid #b8c0c7;border-radius:4px;padding:4px 7px;color:#20252a;min-height:24px;}QTabWidget::pane{border:1px solid #c6ccd2;background:#fff;}QTabBar::tab{background:#e6e9ec;border:1px solid #c6ccd2;padding:7px 12px;color:#4b545c;}QTabBar::tab:selected{background:#fff;color:#111;}QSplitter::handle{background:#c1c7cc;width:4px;}QProgressBar{border:1px solid #c6ccd2;border-radius:4px;background:#fff;text-align:center;color:#20252a;min-height:18px;}QProgressBar::chunk{background:#7b8791;}")
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonPress and isinstance(obj, QPushButton) and obj.isEnabled():
            self.log_text.clear()
            self.progress_bar.setValue(0)
        return super().eventFilter(obj, event)

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
