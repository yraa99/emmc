from PyQt6.QtWidgets import *
from PyQt6.QtCore import QTimer


class BootExtCSDTab(QWidget):
    """EXT_CSD viewer. Boot read/write stays disabled until firmware has safe partition switching support."""

    FIELDS = [
        "PARTITION_CONFIG", "BOOT_SIZE_MULT", "RPMB_SIZE_MULT", "BOOT_BUS_WIDTH",
        "RST_N_FUNCTION", "DEVICE_LIFE_TIME_A", "DEVICE_LIFE_TIME_B", "PRE_EOL_INFO"
    ]

    def __init__(self, emmc, console):
        super().__init__()
        self.emmc = emmc
        self.console = console
        self.ext_csd = None
        self.setup()

    def setup(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        boot_box = QGroupBox("BOOT PARTITION")
        boot = QGridLayout(boot_box)
        boot.setSpacing(8)
        self.readBoot1 = QPushButton("READ BOOT1")
        self.readBoot2 = QPushButton("READ BOOT2")
        self.writeBoot1 = QPushButton("WRITE BOOT1")
        self.writeBoot2 = QPushButton("WRITE BOOT2")
        for b in (self.readBoot1, self.readBoot2, self.writeBoot1, self.writeBoot2):
            b.setObjectName("serviceButton")
            b.setMinimumHeight(30)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.readBoot1.clicked.connect(lambda: self.bootRead(1))
        self.readBoot2.clicked.connect(lambda: self.bootRead(2))
        self.writeBoot1.clicked.connect(lambda: self.bootWrite(1))
        self.writeBoot2.clicked.connect(lambda: self.bootWrite(2))
        boot.addWidget(self.readBoot1, 0, 0)
        boot.addWidget(self.readBoot2, 0, 1)
        boot.addWidget(self.writeBoot1, 1, 0)
        boot.addWidget(self.writeBoot2, 1, 1)
        for b in (self.readBoot1, self.readBoot2, self.writeBoot1, self.writeBoot2):
            b.setEnabled(False)
            b.setToolTip("Belum diaktifkan: firmware belum memiliki partition-switch + boot transfer yang aman.")

        ext_box = QGroupBox("EXT_CSD INFORMATION")
        ext = QVBoxLayout(ext_box)
        ext.setSpacing(8)
        self.extTable = QTableWidget(len(self.FIELDS), 2)
        self.extTable.setHorizontalHeaderLabels(["FIELD", "VALUE"])
        self.extTable.horizontalHeader().setStretchLastSection(True)
        self.extTable.verticalHeader().setVisible(False)
        self.extTable.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for i, field in enumerate(self.FIELDS):
            self.extTable.setItem(i, 0, QTableWidgetItem(field))

        self.readExt = QPushButton("READ EXT_CSD")
        self.saveExt = QPushButton("SAVE EXT_CSD")
        self.writeExt = QPushButton("WRITE EXT_CSD")
        for b in (self.readExt, self.saveExt, self.writeExt):
            b.setObjectName("serviceButton")
            b.setMinimumHeight(30)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.saveExt.setEnabled(False)
        self.writeExt.setEnabled(False)
        self.saveExt.setToolTip("Aktif setelah EXT_CSD berhasil dibaca.")
        self.writeExt.setToolTip("Belum diaktifkan: EXT_CSD write memerlukan CMD6 + safety checks.")
        self.readExt.clicked.connect(self.readExtCSD)
        self.saveExt.clicked.connect(self.saveExtCSD)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addWidget(self.readExt, 1)
        actions.addWidget(self.saveExt, 1)
        actions.addWidget(self.writeExt, 1)
        ext.addWidget(self.extTable, 1)
        ext.addLayout(actions)

        layout.addWidget(boot_box)
        layout.addWidget(ext_box, 1)

    def readExtCSD(self):
        self.console.log("READ EXT_CSD REQUEST")
        self.readExt.setEnabled(False)
        try:
            self.emmc.extcsd()
        except Exception as e:
            self.console.log(f"EXT_CSD ERROR: {e}")
            self.readExt.setEnabled(True)

    def handle_serial_data(self, obj):
        if obj.get("type") != "emmc.layout.result":
            return
        self.readExt.setEnabled(True)
        if not obj.get("ok", False):
            self.console.log("EXT_CSD ERROR: " + str(obj.get("msg", "unknown error")))
            return
        self.ext_csd = bytes.fromhex(str(obj.get("ext_csd_hex", ""))) if obj.get("ext_csd_hex") else None
        vals = {
            "PARTITION_CONFIG": obj.get("partition_config", "-"),
            "BOOT_SIZE_MULT": obj.get("boot_size_mult", "-"),
            "RPMB_SIZE_MULT": self.ext_csd[168] if self.ext_csd and len(self.ext_csd) > 168 else "-",
            "BOOT_BUS_WIDTH": ((self.ext_csd[177] & 0x07) if self.ext_csd and len(self.ext_csd) > 177 else "-"),
            "RST_N_FUNCTION": self.ext_csd[162] if self.ext_csd and len(self.ext_csd) > 162 else "-",
            "DEVICE_LIFE_TIME_A": self.ext_csd[268] if self.ext_csd and len(self.ext_csd) > 268 else "-",
            "DEVICE_LIFE_TIME_B": self.ext_csd[269] if self.ext_csd and len(self.ext_csd) > 269 else "-",
            "PRE_EOL_INFO": self.ext_csd[267] if self.ext_csd and len(self.ext_csd) > 267 else "-",
        }
        for row, field in enumerate(self.FIELDS):
            value = vals[field]
            if isinstance(value, int):
                value = f"0x{value:02X} ({value})"
            self.extTable.setItem(row, 1, QTableWidgetItem(str(value)))
        self.saveExt.setEnabled(bool(self.ext_csd and len(self.ext_csd) == 512))
        self.console.log("EXT_CSD READ OK")

    def saveExtCSD(self):
        if not self.ext_csd:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save EXT_CSD", "ext_csd.bin", "Binary (*.bin);;All Files (*)")
        if not path:
            return
        try:
            with open(path, "wb") as f:
                f.write(self.ext_csd)
            self.console.log(f"EXT_CSD SAVED: {path}")
        except OSError as e:
            self.console.log(f"EXT_CSD SAVE ERROR: {e}")

    def bootRead(self, part):
        self.console.log(f"READ BOOT{part} is not enabled yet")

    def bootWrite(self, part):
        self.console.log(f"WRITE BOOT{part} is not enabled yet")
