from PyQt6.QtWidgets import *


class HealthTab(QWidget):
    FIELDS = ["DEVICE_LIFE_TIME_A", "DEVICE_LIFE_TIME_B", "PRE_EOL_INFO", "RPMB STATUS", "HEALTH STATUS"]

    def __init__(self, emmc, console):
        super().__init__()
        self.emmc = emmc
        self.console = console
        self.setup()

    def setup(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.addWidget(QLabel("eMMC HEALTH REPORT"))
        self.table = QTableWidget(len(self.FIELDS), 2)
        self.table.setHorizontalHeaderLabels(["PARAMETER", "VALUE"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for i, f in enumerate(self.FIELDS):
            self.table.setItem(i, 0, QTableWidgetItem(f))
        layout.addWidget(self.table, 1)
        self.button = QPushButton("READ HEALTH")
        self.button.setObjectName("serviceButton")
        self.button.setMinimumHeight(30)
        self.button.setMinimumWidth(150)
        self.button.clicked.connect(self.readHealth)
        row = QHBoxLayout()
        row.addWidget(self.button)
        row.addStretch()
        layout.addLayout(row)

    def readHealth(self):
        self.button.setEnabled(False)
        try:
            self.emmc.layout()
        except Exception as e:
            self.console.log(f"HEALTH ERROR: {e}")
            self.button.setEnabled(True)

    @staticmethod
    def life_text(v):
        if not isinstance(v, int):
            return "-"
        if v == 0:
            return "0x00 (not defined)"
        if 1 <= v <= 10:
            return f"0x{v:02X} (approximately {v * 10}%–{(v + 1) * 10 - 1}% used)"
        return f"0x{v:02X}"

    @staticmethod
    def pre_eol_text(v):
        return {0x01: "0x01 NORMAL", 0x02: "0x02 WARNING", 0x03: "0x03 URGENT"}.get(v, f"0x{v:02X}")

    def handle_serial_data(self, obj):
        if obj.get("type") != "emmc.layout.result":
            return
        self.button.setEnabled(True)
        if not obj.get("ok", False):
            self.console.log("HEALTH ERROR: " + str(obj.get("msg", "unknown error")))
            return
        try:
            ext = bytes.fromhex(str(obj.get("ext_csd_hex", "")))
        except ValueError:
            ext = b""
        if len(ext) != 512:
            self.console.log("HEALTH ERROR: EXT_CSD payload tidak lengkap")
            return
        a, b, pre, rpmb = ext[268], ext[269], ext[267], ext[168]
        values = [self.life_text(a), self.life_text(b), self.pre_eol_text(pre), f"0x{rpmb:02X} ({rpmb * 128} KiB nominal multiplier)", "NORMAL" if pre == 1 else "WARNING" if pre == 2 else "URGENT" if pre == 3 else "UNKNOWN"]
        for r, value in enumerate(values):
            self.table.setItem(r, 1, QTableWidgetItem(value))
        self.console.log("eMMC HEALTH READ OK")
