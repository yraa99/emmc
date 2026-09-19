from PyQt6.QtWidgets import *
from PyQt6.QtCore import Qt
import os


class BootExtCSDTab(QWidget):
    """Professional boot/EXT_CSD/RPMB workspace.

    Safe READ/WRITE support is exposed only when the firmware provides the
    corresponding protocol. The current firmware is intentionally read-only
    for BOOT and RPMB.
    """

    FIELDS = [
        "PARTITION_CONFIG", "BOOT_SIZE_MULT", "RPMB_SIZE_MULT", "BOOT_BUS_WIDTH",
        "RST_N_FUNCTION", "DEVICE_LIFE_TIME_A", "DEVICE_LIFE_TIME_B", "PRE_EOL_INFO"
    ]

    def __init__(self, emmc, console):
        super().__init__()
        self.emmc = emmc
        self.console = console
        self.ext_csd = None
        self.boot_size_sectors = 0
        self.boot_file_handle = None
        self.boot_expected = 0
        self.boot_received = 0
        self.boot_partition = 0
        self.pending_ext_backup = None
        self.setup()

    def _button(self, text):
        b = QPushButton(text)
        b.setObjectName("serviceButton")
        b.setMinimumHeight(32)
        b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return b

    def setup(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        boot_box = QGroupBox("BOOT 1 / BOOT 2")
        boot = QGridLayout(boot_box)
        boot.setSpacing(8)

        self.readBoot1 = self._button("READ / BACKUP BOOT1")
        self.readBoot2 = self._button("READ / BACKUP BOOT2")
        self.writeBoot1 = self._button("WRITE BOOT1")
        self.writeBoot2 = self._button("WRITE BOOT2")

        self.writeBoot1.setEnabled(False)
        self.writeBoot2.setEnabled(False)
        self.writeBoot1.setToolTip("Write protocol is not implemented.")
        self.writeBoot2.setToolTip("Write protocol is not implemented.")

        self.readBoot1.clicked.connect(lambda: self.bootRead(1))
        self.readBoot2.clicked.connect(lambda: self.bootRead(2))
        self.writeBoot1.clicked.connect(lambda: self.bootWrite(1))
        self.writeBoot2.clicked.connect(lambda: self.bootWrite(2))

        boot.addWidget(self.readBoot1, 0, 0)
        boot.addWidget(self.readBoot2, 0, 1)
        boot.addWidget(self.writeBoot1, 1, 0)
        boot.addWidget(self.writeBoot2, 1, 1)

        self.boot_file = QLineEdit()
        self.boot_file.setReadOnly(True)
        self.boot_file.setPlaceholderText("Backup / write image file")
        self.boot_select = self._button("SELECT FILE")
        self.boot_select.clicked.connect(self.select_boot_file)
        boot.addWidget(self.boot_file, 2, 0)
        boot.addWidget(self.boot_select, 2, 1)

        rpmb_box = QGroupBox("RPMB")
        rpmb = QHBoxLayout(rpmb_box)
        self.readRpmb = self._button("READ / BACKUP RPMB")
        self.writeRpmb = self._button("WRITE RPMB")
        for b in (self.readRpmb, self.writeRpmb):
            b.setEnabled(False)
            b.setToolTip("Disabled: RPMB requires authenticated protocol support.")
        rpmb.addWidget(self.readRpmb)
        rpmb.addWidget(self.writeRpmb)

        ext_box = QGroupBox("EXT_CSD")
        ext = QVBoxLayout(ext_box)
        self.extTable = QTableWidget(len(self.FIELDS), 2)
        self.extTable.setHorizontalHeaderLabels(["FIELD", "VALUE"])
        self.extTable.horizontalHeader().setStretchLastSection(True)
        self.extTable.verticalHeader().setVisible(False)
        self.extTable.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for i, field in enumerate(self.FIELDS):
            self.extTable.setItem(i, 0, QTableWidgetItem(field))

        actions = QHBoxLayout()
        self.readExt = self._button("READ EXT_CSD")
        self.saveExt = self._button("SAVE EXT_CSD")
        self.writeExt = self._button("WRITE EXT_CSD")
        self.saveExt.setEnabled(False)
        self.writeExt.setEnabled(False)
        self.writeExt.setToolTip("Disabled: EXT_CSD write protocol is not active.")
        self.readExt.clicked.connect(self.readExtCSD)
        self.saveExt.clicked.connect(self.saveExtCSD)
        actions.addWidget(self.readExt)
        actions.addWidget(self.saveExt)
        actions.addWidget(self.writeExt)
        ext.addWidget(self.extTable, 1)
        ext.addLayout(actions)

        layout.addWidget(boot_box)
        layout.addWidget(rpmb_box)
        layout.addWidget(ext_box, 1)

    def select_boot_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select BOOT image", "", "Boot image (*.bin *.img);;All Files (*)"
        )
        if path:
            self.boot_file.setText(path)
            self.console.log(f"BOOT file selected: {path}")

    def readExtCSD(self):
        self.readExt.setEnabled(False)
        try:
            self.emmc.extcsd()
        except Exception as e:
            self.console.log(f"EXT_CSD ERROR: {e}")
            self.readExt.setEnabled(True)

    def handle_layout_data(self, obj):
        if obj.get("type") != "emmc.layout.result":
            return
        self.readExt.setEnabled(True)
        if not obj.get("ok", False):
            self.console.log("EXT_CSD ERROR: " + str(obj.get("msg", "unknown error")))
            return

        try:
            self.ext_csd = bytes.fromhex(str(obj.get("ext_csd_hex", "")))
        except ValueError:
            self.ext_csd = None

        self.boot_size_sectors = int(obj.get("boot_bytes_each", 0)) // 512
        self.readBoot1.setEnabled(self.boot_size_sectors > 0)
        self.readBoot2.setEnabled(self.boot_size_sectors > 0)

        vals = {            "PARTITION_CONFIG": obj.get("partition_config", "-"),
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
        if self.pending_ext_backup and self.ext_csd and len(self.ext_csd) == 512:
            path = self.pending_ext_backup
            self.pending_ext_backup = None
            try:
                with open(path, "wb") as f:
                    f.write(self.ext_csd)
                self.console.log(f"EXT_CSD BACKUP COMPLETE: {path}")
            except OSError as e:
                self.console.log(f"EXT_CSD BACKUP ERROR: {e}")
        self.console.log("EXT_CSD READ OK")

    def backupExtCSD(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save EXT_CSD backup", "ext_csd.bin",
            "Binary (*.bin);;All Files (*)"
        )
        if not path:
            return
        self.pending_ext_backup = path
        self.readExtCSD()

    def saveExtCSD(self):
        if not self.ext_csd:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save EXT_CSD", "ext_csd.bin", "Binary (*.bin);;All Files (*)"
        )
        if not path:
            return
        try:
            with open(path, "wb") as f:
                f.write(self.ext_csd)
            self.console.log(f"EXT_CSD SAVED: {path}")
        except OSError as e:
            self.console.log(f"EXT_CSD SAVE ERROR: {e}")

    def bootRead(self, part):
        if self.boot_size_sectors <= 0:
            self.console.log("BOOT READ: EXT_CSD has not reported BOOT partition size")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, f"Save BOOT{part} backup", f"boot{part}.bin",
            "Binary image (*.bin *.img);;All Files (*)"
        )
        if not path:
            return
        try:
            if self.boot_file_handle:
                self.boot_file_handle.close()
            self.boot_file_handle = open(path, "w+b")
            self.boot_file_handle.truncate(self.boot_size_sectors * 512)
        except OSError as e:
            self.boot_file_handle = None
            self.console.log(f"BOOT{part} FILE ERROR: {e}")
            return
        self.boot_partition = int(part)
        self.boot_expected = self.boot_size_sectors * 512
        self.boot_received = 0
        self.readBoot1.setEnabled(False)
        self.readBoot2.setEnabled(False)
        try:
            self.emmc.dump_start(0, self.boot_size_sectors, 512, True, 3, self.boot_partition)
            self.console.log(f"BOOT{part} BACKUP START: {path}")
        except Exception as e:
            self.console.log(f"BOOT{part} READ ERROR: {e}")
            self._finish_boot(False)

    def handle_binary_data(self, frame):
        if not self.boot_file_handle or len(frame) < 8 or frame[0] != 0xB0:
            return
        ch = frame[1]
        offset = int.from_bytes(frame[2:6], "little")
        count = int.from_bytes(frame[6:8], "little")
        if ch == 0x04:
            payload = frame[8:8 + count]
        elif ch == 0x05 and len(frame) >= 9:
            payload = bytes([frame[8]]) * count
        else:
            return
        if len(payload) != count:
            return
        self.boot_file_handle.seek(offset)
        self.boot_file_handle.write(payload)
        self.boot_received = max(self.boot_received, offset + count)

    def handle_serial_data(self, obj):
        if obj.get("type") == "emmc.dump.status" and self.boot_file_handle:
            state = str(obj.get("state", ""))
            if state == "complete":
                self._finish_boot(True)
                return
            if state in ("error", "stopped"):
                self._finish_boot(False)
                return
        self.handle_layout_data(obj)

    def _finish_boot(self, success):
        path = getattr(self.boot_file_handle, "name", None) if self.boot_file_handle else None
        if self.boot_file_handle:
            try:
                self.boot_file_handle.flush()
                self.boot_file_handle.close()
            except OSError:
                pass
        self.boot_file_handle = None
        self.boot_partition = 0
        self.readBoot1.setEnabled(self.boot_size_sectors > 0)
        self.readBoot2.setEnabled(self.boot_size_sectors > 0)
        if success and self.boot_received >= self.boot_expected:
            self.console.log(f"BOOT BACKUP COMPLETE: {path}")
        elif path:
            self.console.log(f"BOOT BACKUP FAILED: {path}")

    def bootWrite(self, part):
        self.console.log(f"WRITE BOOT{part}: write protocol is not implemented")
