from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QPushButton, QAbstractItemView, QFileDialog, QMenu, QSizePolicy, QHeaderView
)
from PyQt6.QtCore import QTimer, Qt
import os


class UserAreaTab(QWidget):
    """GPT/user-area browser with read/backup context actions.

    The active firmware exposes safe READ streaming only. WRITE remains
    intentionally disabled until a real write protocol is available.
    """

    BIN_MAGIC = 0xB0
    CH_DUMP_DATA = 0x04
    CH_DUMP_RUN = 0x05

    def __init__(self, emmc, console):
        super().__init__()
        self.emmc = emmc
        self.console = console
        self.partitions = []
        self.gpt_busy = False
        self.buildprop_busy = False
        self.buildprop_found = False
        self.gpt_count = 0
        self.boot_sectors = 0
        self.primary_meta_lba = 0
        self.primary_meta_sectors = 34
        self.meta_label = "PRIMARY GPT"
        self.gpt_timeout = QTimer(self)
        self.gpt_timeout.setSingleShot(True)
        self.gpt_timeout.timeout.connect(self.on_gpt_timeout)
        self.dump_file = None
        self.dump_expected = 0
        self.dump_received = 0
        self.dump_start_lba = 0
        self.dump_total = 0
        self.dump_segments = []
        self.dump_segment_index = 0
        self.dump_file_base = 0
        self.reading = False
        self._last_read_path = None
        self._buildprop_data = []
        self.setup()

    def hide_main_chrome(self):
        """Hide controls when the live partition table is embedded in MAIN."""
        for widget in (getattr(self, "title", None), getattr(self, "status", None), getattr(self, "actions_widget", None)):
            if widget is not None:
                widget.hide()

    def show_service_controls(self):
        for widget in (getattr(self, "title", None), getattr(self, "status", None), getattr(self, "actions_widget", None)):
            if widget is not None:
                widget.show()

    def setup(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel("USER AREA")
        title.setObjectName("section_title")
        layout.addWidget(title)

        self.status = QLabel("Select a partition and use BACKUP")
        layout.addWidget(self.status)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Partition", "Start LBA", "End LBA", "Sector", "Size", "Type", "Location"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.context_menu)
        self.table.doubleClicked.connect(lambda _: self.readPartition())
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        self.actions_widget = QWidget()
        self.actions_widget.setLayout(actions)
        actions.setSpacing(8)
        self.read = QPushButton("BACKUP")
        self.stop = QPushButton("STOP")
        self.stop.setEnabled(False)
        for button in (self.read, self.stop):
            button.setObjectName("serviceButton")
            button.setMinimumHeight(32)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            actions.addWidget(button)
        layout.addLayout(actions)

        self.read.clicked.connect(self.readPartition)
        self.stop.clicked.connect(self.stopRead)

    def _add_meta_partitions(self):
        if self.boot_sectors > 0:
            self._add_partition("BOOT 1", 0, self.boot_sectors, "BOOT", "READY", False)
            self.partitions[-1]["partition"] = 1
            self._add_partition("BOOT 2", 0, self.boot_sectors, "BOOT", "READY", False)
            self.partitions[-1]["partition"] = 2
        self._add_partition(self.meta_label, self.primary_meta_lba, self.primary_meta_sectors, "METADATA", "READY", False)
        if self.partitions:
            self.partitions[-1]["metadata_only"] = True

    @staticmethod
    def classify(name):
        n = name.lower().strip()
        if not n:
            return "UNKNOWN"
        if n == "super" or n.startswith(("system", "vendor", "product", "odm", "system_ext")):
            return "ANDROID"
        if any(x in n for x in ("userdata", "user-data", "data")):
            return "USERDATA"
        security_tokens = (
            "imei", "nvram", "nvdata", "nvitem", "nvcfg", "persist",
            "modemst", "modem_nv", "modemnvm", "modemsecure", "efs",
            "sec_efs", "fsg", "fsc", "protect", "proinfo", "seccfg",
            "prod_nv", "prodnv", "l_fixnv", "l_runtime", "misdata",
            "md_sec", "oeminfo", "factory", "devinfo", "oppostanvbk",
            "oppodycnvbk", "oppo_custom", "opporeserve", "asuskey",
            "board_info", "secure_storage", "secure", "certification",
            "frp", "keymaster", "keystore", "tee", "trustzone", "tz",
            "secdata", "storsec", "persistbak", "widevine", "drm",
        )
        if any(x in n for x in security_tokens):
            return "SECURITY"
        return "PARTITION"

    def scanGPT(self):
        if self.gpt_busy or self.reading:
            return
        self.gpt_busy = True
        self.buildprop_busy = True
        self.buildprop_found = False
        self._buildprop_data = []
        self.read.setEnabled(False)
        self.stop.setEnabled(False)
        self.partitions.clear()
        self.table.setRowCount(0)
        self.status.setText("Reading partition map...")
        try:
            # Load hardware-area sizes first so BOOT1/BOOT2 rows are always
            # present before GPT partitions are appended.
            self.emmc.layout()
            self.emmc.gpt()
            self.gpt_timeout.start(120000)
        except Exception as e:
            self.gpt_timeout.stop()
            self.gpt_busy = False
            self.buildprop_busy = False
            self.status.setText("GPT request failed")
            self.console.log(f"GPT ERROR: {e}")

    def _add_partition(self, name, start, sectors, ptype="GPT", status="READY", logical=False):
        if not name or sectors <= 0:
            return
        key = (name, int(start), int(sectors), bool(logical))
        if any((p["name"], p["start"], p["sectors"], p["logical"]) == key for p in self.partitions):
            return
        item = {
            "name": name, "start": int(start), "sectors": int(sectors),
            "status": status, "type": ptype, "logical": bool(logical),
            "extents": []
        }
        self.partitions.append(item)
        row = self.table.rowCount()
        self.table.insertRow(row)
        size = int(sectors) * 512
        if size >= 1024**4:
            size_text = f"{size / 1024**4:.2f} TB"
        elif size >= 1024**3:
            size_text = f"{size / 1024**3:.2f} GB"
        elif size >= 1024**2:
            size_text = f"{size / 1024**2:.2f} MB"
        else:
            size_text = f"{size / 1024:.2f} KB"
        location = "SUPER" if logical else "USER"
        end_lba = int(start) + int(sectors) - 1\n        values = (name, str(start), str(end_lba), str(sectors), size_text, ptype, location)
        for col, value in enumerate(values):
            cell = QTableWidgetItem(value)
            if item["status"] == "SECURITY":
                cell.setForeground(Qt.GlobalColor.red)
            self.table.setItem(row, col, cell)

    @staticmethod
    def _prop(data, *keys):
        props = {}
        for line in data.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            props[key.strip()] = value.strip()
        for key in keys:
            if props.get(key):
                return props[key]
        return ""

    def _log_buildprop_summary(self):
        data = "".join(self._buildprop_data)
        if not data:
            return
        brand = self._prop(data, "ro.product.brand", "ro.product.system.brand")
        model = self._prop(data, "ro.product.model", "ro.product.system.model")
        name = self._prop(data, "ro.product.name", "ro.product.system.name")
        product = self._prop(data, "ro.product.device", "ro.product.product.name", "ro.product.name")
        sdk = self._prop(data, "ro.build.version.sdk")
        codename = self._prop(data, "ro.build.version.codename", "ro.build.version.release_or_codename")
        incremental = self._prop(data, "ro.build.version.incremental")
        build_id = self._prop(data, "ro.build.id", "ro.system.build.id")
        android = self._prop(data, "ro.build.version.release")
        miui = self._prop(data, "ro.miui.ui.version.name", "ro.miui.ui.version.code")
        patch = self._prop(data, "ro.build.version.security_patch", "ro.vendor.build.security_patch")
        timezone = self._prop(data, "persist.sys.timezone", "ro.timezone")
        platform = self._prop(data, "ro.board.platform", "ro.hardware")
        abi = self._prop(data, "ro.product.cpu.abi", "ro.product.cpu.abilist")
        build_date = self._prop(data, "ro.build.date", "ro.system.build.date")
        fingerprint = self._prop(data, "ro.build.fingerprint", "ro.system.build.fingerprint")
        imei = self._prop(data, "persist.radio.imei", "ro.ril.oem.imei", "ro.boot.imei")
        mac = self._prop(data, "ro.boot.wifi_mac_address", "wifi.interface.mac", "persist.sys.wifi.macaddr")

        self.console.log("Reading system info ...")
        fields = [
            ("Brand", brand), ("Model", model), ("Name", name), ("Product", product),
            ("Sdk ver", sdk), ("Code name", codename), ("Incremental", incremental),
            ("Build id", build_id), ("Android ver", android), ("Miui ver", miui),
            ("Security patch", patch), ("Timezone", timezone), ("Platform", platform),
            ("Cpu Abi", abi), ("Build Date", build_date), ("Fingerprint", fingerprint),
            ("IMEI", imei), ("MAC", mac),
        ]
        for label, value in fields:
            if value:
                self.console.log(f"{label}: {value}")
        if not imei:
            self.console.log("IMEI: Not exposed by build.prop")
        if not mac:
            self.console.log("MAC: Not exposed by build.prop")

        physical = [p for p in self.partitions if not p["logical"]]
        userdata = [p for p in physical if p["name"].lower() in {"userdata", "user_data", "data"}]
        storage_sectors = max((p["sectors"] for p in userdata), default=sum(p["sectors"] for p in physical))
        if storage_sectors:
            self.console.log(f"Internal storage : {storage_sectors * 512 / 1024**3:.2f} GB")

    def handle_serial_data(self, obj):
        typ = obj.get("type")
        if typ == "emmc.buildprop.begin":
            self.buildprop_busy = True
            self._buildprop_data = []
            self.status.setText(f"Reading system info from {obj.get('partition', 'Android')}...")
            return

        if typ == "emmc.buildprop.chunk":
            self._buildprop_data.append(str(obj.get("data", "")))
            return

        if typ == "emmc.buildprop.result":
            if obj.get("ok"):
                self.buildprop_found = True
                self.status.setText(f"System info: {obj.get('partition', 'build.prop')}")
            return

        if typ == "emmc.buildprop.end":
            self.buildprop_busy = False
            self._log_buildprop_summary()
            self.gpt_timeout.stop()
            self.gpt_busy = False
            self.read.setEnabled(bool(self.partitions))
            if self.buildprop_found:
                self.status.setText("Partition map + system information ready")
            else:
                self.status.setText("Partition map ready; build.prop not found")
            return

        if typ == "emmc.lp.partition":
            self._add_partition(
                str(obj.get("name", "")),
                int(obj.get("start_lba", 0)),
                int(obj.get("sectors", 0)),
                "LOGICAL",
                self.classify(str(obj.get("name", ""))),
                True,
            )
            try:
                extents = obj.get("extents", [])
                if isinstance(extents, list) and self.partitions:
                    self.partitions[-1]["extents"] = [
                        (int(x.get("start", 0)), int(x.get("sectors", 0)))
                        for x in extents
                        if isinstance(x, dict) and int(x.get("sectors", 0)) > 0
                    ]
                    row = self.table.rowCount() - 1
                    if row >= 0:
                        self.table.setItem(row, 6, QTableWidgetItem("SUPER"))
            except Exception:
                pass
            return

        if typ == "emmc.layout.result":
            if obj.get("ok"):
                self.boot_sectors = int(obj.get("boot_bytes_each", 0)) // 512
            return

        if typ == "emmc.gpt.begin":
            self.gpt_count = 0
            self.partitions.clear()
            self.table.setRowCount(0)
            layout_type = str(obj.get("layout_type", "GPT")).upper()
            self.meta_label = "PRELOADER" if layout_type == "PRELOADER" else "PRIMARY GPT"
            self.primary_meta_lba = int(obj.get("primary_gpt_lba", obj.get("preloader_lba", 0)))
            self.primary_meta_sectors = int(obj.get("primary_gpt_sectors", obj.get("preloader_sectors", 34)))
            self._add_meta_partitions()
            self.status.setText("Reading GPT...")
            return

        if typ == "emmc.gpt.partition":
            name = str(obj.get("name", "")).strip()
            self._add_partition(
                name, int(obj.get("start_lba", 0)), int(obj.get("sectors", 0)),
                "GPT", self.classify(name)
            )
            return

        if typ == "emmc.gpt.end":
            if obj.get("ok", True):
                self.gpt_count = int(obj.get("partitions", self.gpt_count))
                self.console.log(f"BOOT DEVICE OK : {self.gpt_count} user-area partitions (real GPT LBAs/sizes)")
            if not self.buildprop_busy:
                self.gpt_busy = False
                self.gpt_timeout.stop()
                self.read.setEnabled(bool(self.partitions))
            return

        if typ == "emmc.gpt.result":
            if obj.get("ok", False):
                return
            if not obj.get("ok", False):
                self.gpt_busy = False
                self.buildprop_busy = False
                self.read.setEnabled(False)
                self.status.setText("GPT failed")
                self.console.log("GPT ERROR: " + str(obj.get("msg", "unknown error")))
            return

        if typ == "emmc.dump.status":
            state = str(obj.get("state", ""))
            done = int(obj.get("done_blocks", 0))
            total = max(1, int(obj.get("total_blocks", 1)))
            self.dump_received = done * 512
            self.dump_expected = self.dump_total * 512
            if state == "complete":
                if self.dump_segment_index + 1 < len(self.dump_segments):
                    self.dump_segment_index += 1
                    self.dump_file_base += self.dump_segments[self.dump_segment_index - 1][1] * 512
                    try:
                        start_lba, sector_count = self.dump_segments[self.dump_segment_index]
                        self.emmc.dump_start(start_lba, sector_count, 512, True, 3)
                    except Exception as e:
                        self.console.log(f"BACKUP NEXT EXTENT ERROR: {e}")
                        self.finish_read(False)
                else:
                    self.finish_read(True)
            elif state == "error":
                self.finish_read(False)

    def on_gpt_timeout(self):
        if not self.gpt_busy and not self.buildprop_busy:
            return
        self.gpt_busy = False
        self.buildprop_busy = False
        self.read.setEnabled(bool(self.partitions))
        self.status.setText("Partition scan timeout")
        self.console.log("PARTITION SCAN TIMEOUT (120s)")
        try:
            self.emmc.stop_tests()
        except Exception:
            pass

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
        self.dump_file.seek(self.dump_file_base + offset)
        self.dump_file.write(payload)
        self.dump_received = max(self.dump_received, self.dump_file_base + offset + count)

    def selectedPartition(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.partitions):
            return None
        return self.partitions[row]

    def context_menu(self, pos):
        p = self.selectedPartition()
        if not p:
            return
        menu = QMenu(self)
        backup = menu.addAction("Backup")
        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if action == backup:
            self.readPartition()

    def readPartition(self):
        p = self.selectedPartition()
        if not p:
            self.console.log("BACKUP: select a partition first")
            return
        if p["sectors"] <= 0 or p["start"] < 0:
            return

        if p.get("metadata_only"):
            path, _ = QFileDialog.getSaveFileName(
                self, f"Save {p['name']} backup", f"{p['name'].lower().replace(' ', '_')}.bin",
                "Binary image (*.bin *.img);;All Files (*)"
            )
            if not path:
                return
            try:
                self.dump_file = open(path, "w+b")
                self.dump_file.truncate(p["sectors"] * 512)
            except OSError as e:
                self.dump_file = None
                self.console.log(f"METADATA FILE ERROR: {e}")
                return
            self.dump_expected = p["sectors"] * 512
            self.dump_received = 0
            self.dump_segments = [(p["start"], p["sectors"])]
            self.dump_segment_index = 0
            self.dump_file_base = 0
            self.dump_total = p["sectors"]
            self.reading = True
            self.read.setEnabled(False)
            self.stop.setEnabled(True)
            try:
                self.emmc.dump_start(p["start"], p["sectors"], 512, True, 3, 0)
            except Exception as e:
                self.console.log(f"METADATA BACKUP ERROR: {e}")
                self.finish_read(False)
            return

        if p.get("partition") in (1, 2):
            partition = int(p["partition"])
            default = f"boot{partition}.bin"
            path, _ = QFileDialog.getSaveFileName(
                self, f"Save BOOT{partition} backup", default,
                "Binary image (*.bin *.img);;All Files (*)"
            )
            if not path:
                return
            try:
                self.dump_file = open(path, "w+b")
                self.dump_file.truncate(p["sectors"] * 512)
            except OSError as e:
                self.dump_file = None
                self.console.log(f"BOOT{partition} FILE ERROR: {e}")
                return
            self.dump_expected = p["sectors"] * 512
            self.dump_received = 0
            self.dump_segments = [(0, p["sectors"])]
            self.dump_segment_index = 0
            self.dump_file_base = 0
            self.dump_total = p["sectors"]
            self.reading = True
            self.read.setEnabled(False)
            self.stop.setEnabled(True)
            try:
                self.emmc.dump_start(0, p["sectors"], 512, True, 3, partition)
            except Exception as e:
                self.console.log(f"BOOT{partition} READ ERROR: {e}")
                self.finish_read(False)
            return

        if p.get("logical"):
            if p.get("extents"):
                base = p["start"] - p["extents"][0][0]
                segments = [(base + start, sectors) for start, sectors in p["extents"]]
            else:
                segments = [(p["start"], p["sectors"])]
        else:
            segments = [(p["start"], p["sectors"])]

        default = os.path.join("", f"{p['name']}.bin")
        path, _ = QFileDialog.getSaveFileName(
            self, "Save partition image", default,
            "Binary image (*.bin *.img);;All Files (*)"
        )
        if not path:
            return

        try:
            self.dump_file = open(path, "w+b")
            self.dump_file.truncate(p["sectors"] * 512)
        except OSError as e:
            self.dump_file = None
            self.console.log(f"BACKUP FILE ERROR: {e}")
            return

        self.dump_expected = p["sectors"] * 512
        self.dump_received = 0
        self.dump_segments = segments
        self.dump_segment_index = 0
        self.dump_file_base = 0
        self.dump_start_lba = segments[0][0]
        self.dump_total = p["sectors"]
        self.reading = True
        self.read.setEnabled(False)
        self.stop.setEnabled(True)
        try:
            start_lba, sector_count = self.dump_segments[0]
            self.emmc.dump_start(start_lba, sector_count, 512, True, 3)
        except Exception as e:
            self.console.log(f"BACKUP START ERROR: {e}")
            self.finish_read(False)

    def stopRead(self):
        if not self.reading:
            return
        try:
            self.emmc.dump_stop()
        except Exception:
            pass
        self.finish_read(False, stopped=True)

    def finish_read(self, success, stopped=False):
        if not self.reading and not self.dump_file:
            return
        path = getattr(self.dump_file, "name", None) if self.dump_file else None
        if self.dump_file:
            try:
                self.dump_file.flush()
                self.dump_file.close()
            except Exception:
                pass
        self.dump_file = None
        self.reading = False
        self.dump_segments = []
        self.dump_segment_index = 0
        self.dump_file_base = 0
        self.stop.setEnabled(False)
        self.read.setEnabled(bool(self.partitions))
        if success and self.dump_received >= self.dump_expected:
            self._last_read_path = path
            self.console.log(f"BACKUP COMPLETE: {path}")
        elif stopped:
            self.console.log(f"BACKUP STOPPED: partial file kept: {path}")
        elif path:
            self.console.log(f"BACKUP FAILED: {path}")

