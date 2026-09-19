from PyQt6.QtWidgets import *
from PyQt6.QtCore import QTimer


class UserAreaTab(QWidget):
    """Real GPT view plus real streamed READ through the firmware dump protocol."""

    BIN_MAGIC = 0xB0
    CH_DUMP_DATA = 0x04
    CH_DUMP_RUN = 0x05

    def __init__(self, emmc, console):
        super().__init__()
        self.emmc = emmc
        self.console = console
        self.partitions = []
        self.gpt_busy = False
        self.dump_file = None
        self.dump_expected = 0
        self.dump_received = 0
        self.dump_start_lba = 0
        self.dump_total = 0
        self.reading = False
        self.setup()

    def setup(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.addWidget(QLabel("USER AREA PARTITION MANAGER"))
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Partition", "Start LBA", "Sectors", "Size", "Status"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        btn = QHBoxLayout()
        btn.setSpacing(8)
        self.scan = QPushButton("SCAN GPT")
        self.read = QPushButton("READ")
        self.write = QPushButton("WRITE")
        self.verify = QPushButton("VERIFY")
        self.stop = QPushButton("STOP")
        self.write.setEnabled(False)   # No WRITE command exists in current RP2040 firmware.
        self.verify.setEnabled(False)  # Enabled after a completed READ; compares against a user-selected reference image.
        self.stop.setEnabled(False)
        for b in (self.scan, self.read, self.write, self.verify, self.stop):
            b.setObjectName("serviceButton")
            b.setMinimumHeight(30)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.addWidget(b, 1)
        layout.addLayout(btn)

        self.scan.clicked.connect(self.scanGPT)
        self.read.clicked.connect(self.readPartition)
        self.write.clicked.connect(self.writePartition)
        self.verify.clicked.connect(self.verifyPartition)
        self.stop.clicked.connect(self.stopRead)

    @staticmethod
    def classify(name):
        n = name.lower().strip()
        if not n:
            return "UNKNOWN"
        if any(x in n for x in ("userdata", "user-data", "data")):
            return "SKIP"
        if any(x in n for x in ("system", "vendor", "product", "odm", "system_ext")):
            return "FW INFO"
        if any(x in n for x in ("security", "protect", "seccfg", "secro")):
            return "SECURITY"
        if any(x in n for x in ("imei", "nvram", "nvdata", "nvcfg", "persist", "modem", "efs", "fsg", "metadata")):
            return "SERVICE"
        return "AVAILABLE"

    def scanGPT(self):
        if self.gpt_busy or self.reading:
            return
        self.gpt_busy = True
        self.partitions.clear()
        self.table.setRowCount(0)
        self.console.log("GPT REQUEST")
        try:
            self.emmc.gpt()
        except Exception as e:
            self.console.log(f"GPT ERROR: {e}")
            self.gpt_busy = False

    def handle_serial_data(self, obj):
        typ = obj.get("type")
        if typ == "emmc.gpt.begin":
            self.partitions.clear()
            self.table.setRowCount(0)
            self.console.log(f"GPT HEADER OK - {obj.get('entries', 0)} entries")
            return
        if typ == "emmc.gpt.partition":
            name = str(obj.get("name", "")).strip()
            start = int(obj.get("start_lba", 0))
            sectors = int(obj.get("sectors", 0))
            status = self.classify(name)
            self.partitions.append({"name": name, "start": start, "sectors": sectors, "status": status})
            row = self.table.rowCount()
            self.table.insertRow(row)
            size = sectors * 512
            if size >= 1024**3:
                size_text = f"{size / 1024**3:.2f} GB"
            elif size >= 1024**2:
                size_text = f"{size / 1024**2:.2f} MB"
            elif size >= 1024:
                size_text = f"{size / 1024:.2f} KB"
            else:
                size_text = f"{size} B"
            for c, v in enumerate((name, str(start), str(sectors), size_text, status)):
                self.table.setItem(row, c, QTableWidgetItem(v))
            return
        if typ == "emmc.gpt.end":
            self.gpt_busy = False
            self.console.log(f"GPT READY - {len(self.partitions)} real partition(s)")
            self.read.setEnabled(bool(self.partitions))
            self.verify.setEnabled(False)
            return
        if typ == "emmc.gpt.result":
            if not obj.get("ok", False):
                self.gpt_busy = False
                self.read.setEnabled(False)
                self.console.log("GPT ERROR: " + str(obj.get("msg", "unknown error")))
            return
        if typ == "emmc.dump.status":
            state = obj.get("state", "")
            done = int(obj.get("done_blocks", 0))
            total = max(1, int(obj.get("total_blocks", 1)))
            self.dump_received = done * 512
            self.dump_expected = self.dump_total * 512
            self.console.log(f"READ {state}: {done}/{total} sectors - {obj.get('detail', '')}")
            if state == "complete":
                self.finish_read(True)
            elif state == "error":
                self.finish_read(False)

    def handle_binary_data(self, frame):
        if not self.reading or len(frame) < 8 or frame[0] != self.BIN_MAGIC:
            return
        ch = frame[1]
        offset = int.from_bytes(frame[2:6], "little")
        count = int.from_bytes(frame[6:8], "little")
        if ch == self.CH_DUMP_DATA:
            payload = frame[8:8 + count]
        elif ch == self.CH_DUMP_RUN and len(frame) >= 9:
            payload = bytes([frame[8]]) * count
        else:
            return
        if len(payload) != count or not self.dump_file:
            return
        self.dump_file.seek(offset)
        self.dump_file.write(payload)
        self.dump_received = max(self.dump_received, offset + count)

    def selectedPartition(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.partitions):
            return None
        p = self.partitions[row]
        return p["name"], p["start"], p["sectors"], p["status"]

    def readPartition(self):
        p = self.selectedPartition()
        if not p:
            self.console.log("READ: select a partition first")
            return
        name, start, count, status = p
        if status == "SKIP":
            self.console.log(f"READ BLOCKED: {name} is SKIP by policy")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save partition image", f"{name}.bin", "Binary (*.bin);;All Files (*)")
        if not path:
            return
        try:
            self.dump_file = open(path, "w+b")
            self.dump_file.truncate(count * 512)
        except OSError as e:
            self.console.log(f"READ FILE ERROR: {e}")
            self.dump_file = None
            return
        self.dump_expected = count * 512
        self.dump_received = 0
        self.dump_start_lba = start
        self.dump_total = count
        self.reading = True
        self.read.setEnabled(False)
        self.scan.setEnabled(False)
        self.stop.setEnabled(True)
        self.console.log(f"READ START: {name} LBA={start} sectors={count}")
        try:
            self.emmc.dump_start(start, count, 512, True, 3)
        except Exception as e:
            self.console.log(f"READ START ERROR: {e}")
            self.finish_read(False)

    def stopRead(self):
        if not self.reading:
            return
        try:
            self.emmc.dump_stop()
        except Exception as e:
            self.console.log(f"READ STOP ERROR: {e}")
        self.finish_read(False, stopped=True)

    def finish_read(self, success, stopped=False):
        if not self.reading and not self.dump_file:
            return
        path = None
        if self.dump_file:
            path = getattr(self.dump_file, "name", None)
            try:
                self.dump_file.flush()
                self.dump_file.close()
            except Exception:
                pass
        self.dump_file = None
        was_reading = self.reading
        self.reading = False
        self.stop.setEnabled(False)
        self.scan.setEnabled(True)
        self.read.setEnabled(bool(self.partitions))
        if success and self.dump_received >= self.dump_expected:
            self._last_read_path = path
            self.verify.setEnabled(True)
            self.console.log(f"READ COMPLETE: {path}")
        elif stopped:
            self.console.log(f"READ STOPPED: partial file kept: {path}")
        elif was_reading:
            self.console.log(f"READ FAILED: {path or 'no file'}")

    def writePartition(self):
        self.console.log("WRITE disabled: firmware write protocol is not implemented yet; no dummy write will be performed")

    def verifyPartition(self):
        p = self.selectedPartition()
        if not p:
            self.console.log("VERIFY: select a partition first")
            return
        name, start, count, status = p
        if status == "SKIP":
            self.console.log(f"VERIFY BLOCKED: {name} is SKIP by policy")
            return
        if not getattr(self, "_last_read_path", None):
            self.console.log("VERIFY ERROR: no completed READ image is available")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Select reference image", "", "Binary (*.bin *.img);;All Files (*)"
        )
        if not path:
            return
        expected_size = count * 512
        try:
            import os
            if os.path.getsize(path) != expected_size:
                self.console.log(f"VERIFY SIZE ERROR: expected {expected_size} bytes")
                return
            with open(path, "rb") as f:
                reference = f.read()
            with open(self._last_read_path, "rb") as f:
                captured = f.read()
            if captured == reference:
                self.console.log(f"VERIFY OK: {name} ({expected_size} bytes)")
                return
            mismatch = next((i for i, (a, b) in enumerate(zip(captured, reference)) if a != b), min(len(captured), len(reference)))
            self.console.log(f"VERIFY FAILED: {name} first mismatch at byte 0x{mismatch:X}")
        except OSError as e:
            self.console.log(f"VERIFY FILE ERROR: {e}")
