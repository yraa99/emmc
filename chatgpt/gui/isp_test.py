from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QSpinBox, QSizePolicy, QGroupBox
)
from PyQt6.QtCore import QTimer


class ISPTestTab(QWidget):
    """Manual ISP tests + realtime RP2040 signal monitor.

    Mapping is fixed to the current project wiring:
      CMD  = GPIO7
      CLK  = GPIO8
      DAT0 = GPIO9

    Realtime packets are handled here and are intentionally not written to the
    normal Console / Log by main.py.
    """

    def __init__(self, emmc, console):
        super().__init__()
        self.emmc = emmc
        self.console = console
        self.busy = False
        self.setup()

    def _make_status_card(self, title):
        box = QGroupBox(title)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(10, 8, 10, 8)
        value = QLabel("—")
        value.setObjectName("isp_signal_value")
        value.setAlignment(__import__('PyQt6.QtCore', fromlist=['Qt']).Qt.AlignmentFlag.AlignCenter)
        value.setMinimumHeight(42)
        layout.addWidget(value)
        return box, value

    def setup(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel("eMMC ISP / SIGNAL MONITOR")
        title.setObjectName("section_title")
        layout.addWidget(title)
        layout.addWidget(QLabel(
            "Realtime pin monitor: CMD=GPIO7, CLK=GPIO8, DAT0=GPIO9. "
            "CLK monitor menggunakan PWM RP2040; CMD/DAT0 dibaca sebagai input."
        ))

        # Realtime status area
        status_grid = QGridLayout()
        status_grid.setHorizontalSpacing(8)
        status_grid.setVerticalSpacing(8)
        cmd_box, self.cmd_state = self._make_status_card("CMD — GPIO7")
        clk_box, self.clk_state = self._make_status_card("CLK — GPIO8")
        dat0_box, self.dat0_state = self._make_status_card("DAT0 — GPIO9")
        status_grid.addWidget(cmd_box, 0, 0)
        status_grid.addWidget(clk_box, 0, 1)
        status_grid.addWidget(dat0_box, 0, 2)
        layout.addLayout(status_grid)

        freq_row = QHBoxLayout()
        freq_row.addWidget(QLabel("CLK monitor frequency:"))
        self.frequency = QSpinBox()
        self.frequency.setRange(1000, 4000000)
        self.frequency.setSingleStep(1000)
        self.frequency.setValue(400000)
        self.frequency.setSuffix(" Hz")
        self.frequency.setMinimumWidth(150)
        freq_row.addWidget(self.frequency)
        self.start_monitor = QPushButton("START MONITOR")
        self.stop_monitor = QPushButton("STOP MONITOR")
        self.stop_monitor.setEnabled(False)
        freq_row.addWidget(self.start_monitor)
        freq_row.addWidget(self.stop_monitor)
        freq_row.addStretch()
        layout.addLayout(freq_row)

        self.frequency_actual = QLabel("Generated frequency: —")
        self.frequency_actual.setObjectName("isp_frequency")
        layout.addWidget(self.frequency_actual)

        # Manual tests
        manual_group = QGroupBox("MANUAL ISP TEST")
        manual_layout = QVBoxLayout(manual_group)
        row = QGridLayout()
        row.setHorizontalSpacing(8)
        row.setVerticalSpacing(8)
        self.cmd_test = QPushButton("CMD / CLK TEST")
        self.clk_wave_test = QPushButton("CLK WAVE TEST")
        self.clk_high = QPushButton("CLK HIGH")
        self.clk_low = QPushButton("CLK LOW")
        self.cmd_high = QPushButton("CMD HIGH")
        self.cmd_low = QPushButton("CMD LOW")
        self.dat0_high = QPushButton("DAT0 HIGH")
        self.dat0_low = QPushButton("DAT0 LOW")
        self.cmd1_test = QPushButton("CMD1 RESPONSE TEST")
        self.pin_test = QPushButton("CHECK PINS")
        self.cancel = QPushButton("CANCEL")
        self.cancel.setEnabled(False)
        buttons = (
            self.cmd_test, self.clk_wave_test, self.clk_high,
            self.clk_low, self.cmd_high, self.cmd_low,
            self.dat0_high, self.dat0_low, self.cmd1_test,
            self.pin_test, self.cancel,
        )
        for index, button in enumerate(buttons):
            button.setMinimumHeight(34)
            button.setMinimumWidth(150)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            row.addWidget(button, index // 3, index % 3)
        manual_layout.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("CMD test cycles:"))
        self.cycles = QSpinBox()
        self.cycles.setRange(1, 64)
        self.cycles.setValue(6)
        row2.addWidget(self.cycles)
        row2.addStretch()
        manual_layout.addLayout(row2)
        layout.addWidget(manual_group)
        layout.addStretch()

        # Signals
        self.start_monitor.clicked.connect(self.run_monitor_start)
        self.stop_monitor.clicked.connect(self.run_monitor_stop)
        self.cmd_test.clicked.connect(self.run_cmd)
        self.clk_wave_test.clicked.connect(self.run_clk_wave)
        self.clk_high.clicked.connect(lambda: self.run_pin_level("HIGH"))
        self.clk_low.clicked.connect(lambda: self.run_pin_level("LOW"))
        self.cmd_high.clicked.connect(lambda: self.run_cmd_level("HIGH"))
        self.cmd_low.clicked.connect(lambda: self.run_cmd_level("LOW"))
        self.dat0_high.clicked.connect(lambda: self.run_dat0_level("HIGH"))
        self.dat0_low.clicked.connect(lambda: self.run_dat0_level("LOW"))
        self.cmd1_test.clicked.connect(self.run_cmd1)
        self.pin_test.clicked.connect(self.run_pins)
        self.cancel.clicked.connect(self.run_cancel)

    def start(self, label):
        self.busy = True
        self.cancel.setEnabled(True)
        self.console.log(label)

    def finish(self):
        self.busy = False
        self.cancel.setEnabled(False)

    def run_monitor_start(self):
        try:
            self.emmc.signal_monitor_start(self.frequency.value())
            self.start_monitor.setEnabled(False)
            self.stop_monitor.setEnabled(True)
        except Exception as e:
            self.console.log(f"ISP ERROR: {e}")

    def run_monitor_stop(self):
        try:
            self.emmc.signal_monitor_stop()
        except Exception as e:
            self.console.log(f"ISP ERROR: {e}")
        self.stop_monitor.setEnabled(False)
        self.start_monitor.setEnabled(True)
        self._set_state(self.cmd_state, None)
        self._set_state(self.clk_state, None)
        self._set_state(self.dat0_state, None)
        self.frequency_actual.setText("Generated frequency: —")

    @staticmethod
    def _set_state(label, value):
        if value is None:
            label.setText("—")
        elif isinstance(value, str):
            label.setText(value)
        else:
            label.setText("HIGH" if value else "LOW")

    def handle_serial_data(self, obj):
        if not isinstance(obj, dict):
            return
        kind = obj.get("type")
        if kind == "signal.status":
            self._set_state(self.cmd_state, obj.get("cmd_state") if obj.get("cmd_state") is not None else obj.get("cmd"))
            self._set_state(self.clk_state, obj.get("clk_state") if obj.get("clk_state") is not None else obj.get("clk"))
            self._set_state(self.dat0_state, obj.get("dat0_state") if obj.get("dat0_state") is not None else obj.get("dat0"))
            freq = int(obj.get("frequency_hz") or 0)
            self.frequency_actual.setText(f"Generated frequency: {freq:,} Hz")
            return
        if kind == "signal.started":
            if obj.get("ok"):
                self.start_monitor.setEnabled(False)
                self.stop_monitor.setEnabled(True)
                freq = int(obj.get("frequency_hz") or 0)
                self.frequency_actual.setText(f"Generated frequency: {freq:,} Hz")
            return
        if kind == "signal.stopped":
            self.start_monitor.setEnabled(True)
            self.stop_monitor.setEnabled(False)
            self._set_state(self.cmd_state, None)
            self._set_state(self.clk_state, None)
            self._set_state(self.dat0_state, None)
            self.frequency_actual.setText("Generated frequency: —")
            return
        if kind == "emmc.pin_test.result":
            pin = obj.get("pin", "?")
            level = obj.get("level", "?")
            readback = obj.get("readback", "?")
            if obj.get("ok"):
                self.console.log(f"ISP: {pin} {level} TEST OK - readback={readback}")
            else:
                self.console.log(f"ISP: {pin} {level} TEST FAILED")
            self.finish()
            return

    def run_cmd(self):
        try:
            self.start("ISP: CMD/CLK TEST REQUEST")
            self.emmc.isp_cmd_test(self.cycles.value())
        except Exception as e:
            self.console.log(f"ISP ERROR: {e}")
            self.finish()

    def run_clk_wave(self):
        try:
            self.start("ISP: CLK WAVE TEST REQUEST (400 kHz / 1000 ms)")
            self.emmc.clk_test(400000, 1000)
        except Exception as e:
            self.console.log(f"ISP ERROR: {e}")
            self.finish()

    def run_pin_level(self, level):
        try:
            self.start(f"ISP: CLK STATIC {level} REQUEST")
            self.emmc.pin_test_clk(level)
        except Exception as e:
            self.console.log(f"ISP ERROR: {e}")
            self.finish()

    def run_cmd_level(self, level):
        try:
            self.start(f"ISP: CMD STATIC {level} REQUEST (eMMC DISCONNECTED)")
            self.emmc.pin_test_cmd(level)
        except Exception as e:
            self.console.log(f"ISP ERROR: {e}")
            self.finish()

    def run_dat0_level(self, level):
        try:
            self.start(f"ISP: DAT0 STATIC {level} REQUEST (eMMC DISCONNECTED)")
            self.emmc.pin_test_dat0(level)
        except Exception as e:
            self.console.log(f"ISP ERROR: {e}")
            self.finish()

    def run_cmd1(self):
        try:
            self.start("ISP: CMD1 RESPONSE TEST REQUEST")
            self.emmc.isp_cmd1_test()
        except Exception as e:
            self.console.log(f"ISP ERROR: {e}")
            self.finish()

    def run_pins(self):
        try:
            self.console.log("ISP: CHECK PINS REQUEST")
            self.emmc.check_pins()
        except Exception as e:
            self.console.log(f"ISP ERROR: {e}")

    def run_cancel(self):
        try:
            self.emmc.stop_tests()
            self.console.log("ISP: CANCEL REQUEST")
        except Exception as e:
            self.console.log(f"CANCEL ERROR: {e}")
        self.finish()
