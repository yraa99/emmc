from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy,
    QSpinBox
)
from PyQt6.QtCore import pyqtSignal


class MainTab(QWidget):
    """Professional MAIN dashboard.

    Visible controls call the same pico-emmc-beta service methods.  Operations
    that beta intentionally disables remain disabled instead of being replaced
    by fake placeholder success messages.
    """

    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)

    def __init__(self, emmc_core=None):
        super().__init__()
        self.emmc = emmc_core
        self.callbacks = {}
        self.init_ui()

    def set_callbacks(self, **callbacks):
        self.callbacks.update(callbacks)

    def _button(self, text, enabled=True, primary=False):
        b = QPushButton(text)
        b.setMinimumHeight(34)
        b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        b.setEnabled(enabled)
        if primary:
            b.setObjectName("mainAction")
        return b

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel("eMMC SERVICE TOOL")
        title.setObjectName("section_title")
        layout.addWidget(title)

        info_box = QGroupBox("eMMC IDENTIFICATION")
        info_layout = QVBoxLayout(info_box)
        self.info = QTableWidget(8, 2)
        self.info.setHorizontalHeaderLabels(["PARAMETER", "VALUE"])
        self.info.verticalHeader().setVisible(False)
        self.info.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.info.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.info.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for i, name in enumerate([
            "Manufacturer", "Model", "CID", "CSD",
            "OCR / RCA", "Capacity", "EXT_CSD Revision", "Status"
        ]):
            self.info.setItem(i, 0, QTableWidgetItem(name))
        info_layout.addWidget(self.info)
        layout.addWidget(info_box)

        ops = QGroupBox("eMMC OPERATIONS")
        grid = QGridLayout(ops)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)

        self.btn_health = self._button("eMMC Health Check", primary=True)
        self.btn_extcsd = self._button("READ EXT_CSD")
        self.btn_cancel = self._button("CANCEL")

        grid.addWidget(self.btn_health, 0, 0)
        grid.addWidget(self.btn_extcsd, 0, 1)
        grid.addWidget(self.btn_cancel, 1, 0)
        layout.addWidget(ops)

        special = QGroupBox("SPECIAL TASK")
        sgrid = QGridLayout(special)
        self.special_buttons = {}
        for i, label in enumerate((
            "FFU MODE", "SET BOOT PARTITION", "PARTITION CONFIG",
            "RPMB INFO", "SECURITY TASK"
        )):
            b = self._button(label, enabled=True)
            b.setToolTip("Run the corresponding pico-emmc-beta SPECIAL TASK handler.")
            self.special_buttons[label] = b
            sgrid.addWidget(b, i // 2, i % 2)
        layout.addWidget(special)

        isp = QGroupBox("ISP / SIGNAL TEST")
        igrid = QGridLayout(isp)
        self.isp_frequency = QSpinBox()
        self.isp_frequency.setRange(1000, 4000000)
        self.isp_frequency.setSingleStep(1000)
        self.isp_frequency.setValue(400000)
        self.isp_frequency.setSuffix(" Hz")
        self.btn_isp_monitor = self._button("START MONITOR")
        self.btn_isp_stop = self._button("STOP MONITOR", enabled=False)
        self.btn_isp_cmd = self._button("CMD / CLK TEST")
        self.btn_isp_clk = self._button("CLK WAVE TEST")
        self.btn_isp_pins = self._button("CHECK PINS")
        self.btn_isp_cmd1 = self._button("CMD1 RESPONSE TEST")
        igrid.addWidget(QLabel("Monitor frequency"), 0, 0)
        igrid.addWidget(self.isp_frequency, 0, 1)
        igrid.addWidget(self.btn_isp_monitor, 0, 2)
        igrid.addWidget(self.btn_isp_stop, 0, 3)
        igrid.addWidget(self.btn_isp_cmd, 1, 0)
        igrid.addWidget(self.btn_isp_clk, 1, 1)
        igrid.addWidget(self.btn_isp_pins, 1, 2)
        igrid.addWidget(self.btn_isp_cmd1, 1, 3)
        layout.addWidget(isp)
        layout.addStretch()

        self.btn_health.clicked.connect(lambda: self._call("health"))
        self.btn_extcsd.clicked.connect(lambda: self._call("extcsd"))
        self.btn_cancel.clicked.connect(lambda: self._call("cancel"))
        for label, button in self.special_buttons.items():
            command = {
                "FFU MODE": "FFU",
                "SET BOOT PARTITION": "SET_BOOT",
                "PARTITION CONFIG": "PARTITION_CONFIG",
                "RPMB INFO": "RPMB_INFO",
                "SECURITY TASK": "SECURITY",
            }[label]
            button.clicked.connect(lambda checked=False, cmd=command: self._call("special", cmd))
        self.btn_isp_monitor.clicked.connect(lambda: self._call("isp_monitor_start", self.isp_frequency.value()))
        self.btn_isp_stop.clicked.connect(lambda: self._call("isp_monitor_stop"))
        self.btn_isp_cmd.clicked.connect(lambda: self._call("isp_cmd"))
        self.btn_isp_clk.clicked.connect(lambda: self._call("isp_clk"))
        self.btn_isp_pins.clicked.connect(lambda: self._call("isp_pins"))
        self.btn_isp_cmd1.clicked.connect(lambda: self._call("isp_cmd1"))

    def _call(self, name, *args):
        cb = self.callbacks.get(name)
        if cb:
            try:
                cb(*args)
            except Exception as e:
                self.log_signal.emit(f"[ERROR] {name}: {e}")
        else:
            self.log_signal.emit(f"[ERROR] MAIN action not connected: {name}")

    def set_value(self, name, value):
        for row in range(self.info.rowCount()):
            if self.info.item(row, 0) and self.info.item(row, 0).text() == name:
                self.info.setItem(row, 1, QTableWidgetItem(str(value)))
                return

    def handle_serial_data(self, packet):
        if not isinstance(packet, dict):
            return
        kind = packet.get("type")
        if kind == "emmc.identify.result":
            if not packet.get("ok", False):
                self.set_value("Status", "ERROR")
                return
            cid = str(packet.get("cid", ""))
            csd = str(packet.get("csd", ""))
            ext = str(packet.get("ext_csd", ""))
            self.set_value("CID", cid)
            self.set_value("CSD", csd)
            self.set_value("Manufacturer", self._decode_cid(cid).get("manufacturer", "Unknown"))
            self.set_value("Model", self._decode_cid(cid).get("pnm", ""))
            self.set_value("OCR / RCA", f"0x{int(packet.get('ocr', 0)):08X} / {int(packet.get('rca', 0))}")
            cap = int(packet.get("capacity_bytes", 0))
            if cap:
                self.set_value("Capacity", self._format_capacity(cap))
            self.set_value("EXT_CSD Revision", f"0x{int(packet.get('ext_csd_rev', 0)):02X}")
            self.set_value("Status", "IDENTIFY OK")
        elif kind == "emmc.layout.result":
            self.set_value("Status", "HEALTH / EXT_CSD OK" if packet.get("ok") else "HEALTH ERROR")

    @staticmethod
    def _decode_cid(cid):
        try:
            b = bytes.fromhex(cid)
            mid = b[0]
            pnm = b[3:9].decode("ascii", errors="replace").rstrip(" \\x00")
            manufacturers = {
                0x00: "SanDisk", 0x03: "Toshiba", 0x11: "Toshiba",
                0x13: "Micron", 0x15: "Samsung/SanDisk/LG",
                0x2C: "Kingston", 0x45: "SanDisk Corporation",
                0x70: "Kingston", 0x90: "SK hynix", 0xFE: "Micron",
            }
            return {"manufacturer": manufacturers.get(mid, "Unknown"), "pnm": pnm}
        except Exception:
            return {"manufacturer": "Unknown", "pnm": ""}

    @staticmethod
    def _format_capacity(value):
        if value >= 1024**4:
            return f"{value / 1024**4:.2f} TB"
        if value >= 1024**3:
            return f"{value / 1024**3:.2f} GB"
        if value >= 1024**2:
            return f"{value / 1024**2:.2f} MB"
        return f"{value / 1024:.2f} KB"
