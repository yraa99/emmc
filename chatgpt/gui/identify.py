from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QPushButton, QHBoxLayout, QSizePolicy, QHeaderView, QGroupBox
from PyQt6.QtCore import QTimer


class IdentifyTab(QWidget):
    def __init__(self, emmc, console):
        super().__init__()
        self.emmc = emmc
        self.console = console
        self.busy = False
        self.buildprop_lines = []
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self.on_timeout)
        self.setup()

    def setup(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        title = QLabel("eMMC IDENTIFY")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        action_group = QGroupBox("DEVICE OPERATIONS")
        action_layout = QHBoxLayout(action_group)
        action_layout.setContentsMargins(8, 8, 8, 8)
        action_layout.setSpacing(6)

        self.button = QPushButton("IDENTIFY DEVICE")
        self.cancel = QPushButton("CANCEL")

        for button in (self.button, self.cancel):
            button.setObjectName("serviceButton")
            button.setMinimumHeight(32)
            button.setMinimumWidth(145)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.cancel.setEnabled(False)
        action_layout.addWidget(self.button)
        action_layout.addWidget(self.cancel)
        layout.addWidget(action_group)

        info_group = QGroupBox("eMMC INFORMATION")
        info_layout = QVBoxLayout(info_group)
        info_layout.setContentsMargins(6, 6, 6, 6)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["PARAMETER", "VALUE"])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        fields = [
            "Manufacturer", "MID", "CBX", "OID", "Model", "PRV",
            "eMMC Serial (CID)", "Device SN", "IMEI", "Wi-Fi MAC", "Manufacturing Date", "CID", "CSD",
            "EXT_CSD", "EXT_CSD Revision", "Capacity", "Sector Size",
            "Bus Width", "Clock", "BOOT1 Read", "BOOT2 Read",
            "EXT_CSD Read", "USERAREA Read", "BUILD.PROP", "Status"
        ]
        self.table.setRowCount(len(fields))
        for i, f in enumerate(fields):
            self.table.setItem(i, 0, QTableWidgetItem(f))

        info_layout.addWidget(self.table)
        layout.addWidget(info_group, 1)

        self.button.clicked.connect(self.identify)
        self.cancel.clicked.connect(self.cancel_identify)

    def handle_serial_data(self, obj):
        typ = obj.get("type")
        if typ == "emmc.identify.area":
            area = str(obj.get("area", ""))
            state = str(obj.get("state", ""))
            if state == "start":
                self.console.log(f"IDENTIFY READ START: {area}")
            elif state == "complete":
                self.console.log(f"IDENTIFY READ COMPLETE: {area}")
            return
        if typ == "emmc.identify.progress":
            self.console.log(
                f"IDENTIFY {obj.get('area', '')}: {int(obj.get('percent', 0))}%"
            )
            return
        if typ == "emmc.buildprop.begin":
            self.buildprop_lines = []
            part = str(obj.get("partition", "system"))
            self.set_value("BUILD.PROP", f"READING {part}")
            self.console.log(f"BUILD.PROP [{part}] READ START")
            return

        if typ == "emmc.buildprop.chunk":
            data = str(obj.get("data", ""))
            if data:
                self.buildprop_lines.append(data)
            return
        if typ == "emmc.buildprop.result":
            self.set_value(
                "BUILD.PROP",
                f"OK ({obj.get('partition', 'build.prop')})" if obj.get("ok") else "FAILED"
            )
            return
        if typ == "emmc.buildprop.end":
            ok = bool(obj.get("ok"))
            if ok:
                self.set_value("BUILD.PROP", "OK")
                self.console.log("BUILD.PROP : OK")
                if self.buildprop_lines:
                    self._log_system_summary("".join(self.buildprop_lines))
            else:
                self.set_value("BUILD.PROP", "FAILED")
                self.console.log("BUILD.PROP : FAILED - " + str(obj.get("msg", "unknown error")))
            return
        if typ != "emmc.identify.result":
            return
        if not obj.get("ok", False):
            self.console.log("IDENTIFY ERROR: " + str(obj.get("msg", "unknown error")))
            self.set_value("Status", "ERROR")
            self.finish()
            return
        cid = str(obj.get("cid", ""))
        csd = str(obj.get("csd", ""))
        ext = str(obj.get("ext_csd", ""))
        ocr = int(obj.get("ocr", 0))
        if not cid or len(cid) != 32 or not csd or len(csd) != 32 or len(ext) != 1024:
            self.console.log("IDENTIFY ERROR: incomplete CID/CSD/EXT_CSD response")
            self.set_value("Status", "ERROR: incomplete register data")
            self.finish()
            return

        self.set_value("CID", cid)
        self.set_value("CSD", csd)
        self.set_value("EXT_CSD", ext)
        fields = self.decode_cid(cid)
        self.set_value("Manufacturer", fields["manufacturer"])
        self.set_value("MID", fields["mid"])
        self.set_value("CBX", fields["cbx"])
        self.set_value("OID", fields["oid"])
        self.set_value("Model", fields["pnm"])
        self.set_value("PRV", fields["prv"])
        self.set_value("eMMC Serial (CID)", fields["psn"])
        self.set_value("Device SN", str(obj.get("device_sn", "NOT FOUND")))
        self.set_value("IMEI", str(obj.get("imei", "NOT FOUND")))
        self.set_value("Wi-Fi MAC", str(obj.get("wifi_mac", "NOT FOUND")))
        self.set_value("Manufacturing Date", fields["mdt"])

        capacity_bytes = int(obj.get("capacity_bytes", 0))
        if capacity_bytes > 0:
            self.set_value("Capacity", self.format_capacity(capacity_bytes))
        else:
            self.set_value("Capacity", self.ext_capacity(ext))

        self.set_value("EXT_CSD Revision", f"0x{int(obj.get('ext_csd_rev', int(ext[384:386], 16) if len(ext) >= 386 else 0)):02X}")
        self.set_value("Sector Size", f"{int(obj.get('sector_size', 512))} bytes")
        self.set_value("Bus Width", self.bus_width_text(int(obj.get("bus_width_mode", 0))))
        self.set_value("Clock", f"{int(obj.get('clock_hz', 200000)) / 1000:.0f} kHz (identify)")
        self.set_value("BOOT1 Read", "OK" if obj.get("boot1_read") else "FAILED")
        self.set_value("BOOT2 Read", "OK" if obj.get("boot2_read") else "FAILED")
        self.set_value("EXT_CSD Read", "OK" if obj.get("extcsd_read") else "FAILED")
        self.set_value("USERAREA Read", "OK" if obj.get("userarea_read") else "FAILED")
        status = f"OK (OCR 0x{ocr:08X}, RCA {int(obj.get('rca', 0))})"
        self.set_value("Status", status)
        self.console.log("eMMC IDENTIFY")
        self.console.log(f"OCR          : 0x{ocr:08X}")
        self.console.log(f"RCA          : {int(obj.get('rca', 0))}")
        for row in range(self.table.rowCount()):
            key = self.table.item(row, 0)
            value = self.table.item(row, 1)
            if key:
                self.console.log(f"{key.text():16} : {value.text() if value else '-'}")
        self.console.log("IDENTIFY OK")
        self.finish()

    def _log_system_summary(self, data):
        props = {}
        for line in data.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            props[key.strip()] = value.strip()
        fields = (
            ("Brand", "ro.product.brand", "ro.product.system.brand"),
            ("Model", "ro.product.model", "ro.product.system.model"),
            ("Product", "ro.product.device", "ro.product.name", "ro.product.system.name"),
            ("Android", "ro.build.version.release", "ro.build.version.release_or_codename"),
            ("SDK", "ro.build.version.sdk"),
            ("Build ID", "ro.build.id", "ro.system.build.id"),
            ("Platform", "ro.board.platform", "ro.hardware"),
            ("Security Patch", "ro.build.version.security_patch", "ro.vendor.build.security_patch"),
            ("Fingerprint", "ro.build.fingerprint", "ro.system.build.fingerprint"),
        )
        self.console.log("SYSTEM INFO (build.prop summary only)")
        for label, *names in fields:
            value = next((props[n] for n in names if props.get(n)), "")
            if value:
                self.console.log(f"{label}: {value}")
        self.console.log("IMEI / device SN / Wi-Fi MAC: read from identity/security sources, not full build.prop")

    def set_value(self, field, value):
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0) and self.table.item(r, 0).text() == field:
                self.table.setItem(r, 1, QTableWidgetItem(str(value)))
                return

    @staticmethod
    def decode_cid(cid):
        try:
            b = bytes.fromhex(cid)
            if len(b) != 16:
                raise ValueError
            mid = b[0]
            cbx = b[1] & 0x03
            oid = b[2]
            pnm = b[3:9].decode("ascii", errors="replace").rstrip(" \x00")
            prv = b[9]
            psn = int.from_bytes(b[10:14], "big")
            mdt = b[14]
            year = 1997 + ((mdt >> 4) & 0x0F)
            month = mdt & 0x0F
            cbx_names = {0: "Card", 1: "BGA", 2: "POP", 3: "Reserved"}
            manufacturers = {
                0x00: "SanDisk",
                0x02: "Kingston/SanDisk",
                0x03: "Toshiba",
                0x11: "Toshiba",
                0x12: "Gigastone",
                0x13: "Micron",
                0x15: "Samsung/SanDisk/LG",
                0x27: "Apacer",
                0x2C: "Kingston",
                0x37: "KingMax",
                0x44: "ATP",
                0x45: "SanDisk Corporation",
                0x5D: "Swissbit",
                0x70: "Kingston",
                0x90: "SK hynix",
                0xFE: "Micron",
            }
            return {
                "manufacturer": manufacturers.get(mid, "Unknown"),
                "mid": f"0x{mid:02X}",
                "cbx": f"0x{cbx:02X} ({cbx_names.get(cbx, 'Unknown')})",
                "oid": f"0x{oid:02X}",
                "pnm": pnm,
                "prv": f"0x{prv:02X}",
                "psn": f"0x{psn:08X}",
                "mdt": f"{month:02d}/{year}" if 1 <= month <= 12 else f"0x{mdt:02X}",
            }
        except Exception:
            return {
                "manufacturer": "", "mid": "", "cbx": "", "oid": "",
                "pnm": "", "prv": "", "psn": "", "mdt": ""
            }

    @staticmethod
    def format_capacity(value):
        if value >= 1024**4:
            return f"{value / 1024**4:.2f} TB"
        if value >= 1024**3:
            return f"{value / 1024**3:.2f} GB"
        if value >= 1024**2:
            return f"{value / 1024**2:.2f} MB"
        return f"{value / 1024:.2f} KB"

    @staticmethod
    def ext_capacity(ext):
        try:
            b = bytes.fromhex(ext)
            if len(b) != 512:
                return ""
            sectors = int.from_bytes(b[212:216], "little")
            return IdentifyTab.format_capacity(sectors * 512)
        except Exception:
            return ""

    @staticmethod
    def bus_width_text(mode):
        return {
            0: "1-bit",
            1: "4-bit",
            2: "8-bit",
            5: "4-bit DDR",
            6: "8-bit DDR",
        }.get(mode & 0x07, f"mode {mode}")

    @staticmethod
    def cid_mid(cid):
        try:
            return f"0x{bytes.fromhex(cid)[0]:02X}"
        except Exception:
            return ""

    @staticmethod
    def cid_pnm(cid):
        try:
            b = bytes.fromhex(cid)
            return b[3:9].decode("ascii", errors="replace").rstrip(" \x00")
        except Exception:
            return ""

    @staticmethod
    def csd_capacity(csd):
        try:
            b = bytes.fromhex(csd)
            if len(b) != 16:
                return ""
            v = int.from_bytes(b, "big")
            csd_structure = (v >> 126) & 0x3
            if csd_structure == 1:
                sectors = (((v >> 48) & 0x3FFFFF) + 1) * 1024
                return f"{sectors * 512 / (1024**3):.2f} GB"
            return "CSD v1 (capacity not decoded)"
        except Exception:
            return ""

    def identify(self):
        if self.busy:
            return
        self.busy = True
        self.button.setEnabled(False)
        self.cancel.setEnabled(True)
        try:
            self.emmc.identify()
            self.timeout.start(24 * 60 * 60 * 1000)
        except Exception as e:
            self.console.log(f"IDENTIFY ERROR: {e}")
            self.finish()

    def cancel_identify(self):
        self.console.log("IDENTIFY CANCEL")
        try:
            self.emmc.stop_tests()
        except Exception:
            pass
        self.timeout.stop()
        self.finish()

    def on_timeout(self):
        self.console.log("IDENTIFY TIMEOUT (24h) - RP2040 tidak memberi hasil")
        self.finish()

    def finish(self):
        self.timeout.stop()
        self.busy = False
        self.button.setEnabled(True)
        self.cancel.setEnabled(False)
