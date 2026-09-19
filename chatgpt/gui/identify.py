from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QPushButton, QHBoxLayout, QSizePolicy
from PyQt6.QtCore import QTimer


class IdentifyTab(QWidget):
    def __init__(self, emmc, console):
        super().__init__()
        self.emmc = emmc
        self.console = console
        self.busy = False
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self.on_timeout)
        self.setup()

    def setup(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("eMMC IDENTIFY"))
        self.table = QTableWidget(16, 2)
        self.table.setHorizontalHeaderLabels(["PARAMETER", "VALUE"])
        fields = [
            "Manufacturer", "MID", "CBX", "OID", "Model", "PRV",
            "Serial Number", "Manufacturing Date", "CID", "CSD",
            "EXT_CSD", "Capacity", "Sector Size", "Bus Width", "Clock", "Status"
        ]
        for i, f in enumerate(fields):
            self.table.setItem(i, 0, QTableWidgetItem(f))
        row = QHBoxLayout()
        self.button = QPushButton("IDENTIFY DEVICE")
        self.cancel = QPushButton("CANCEL")
        for button in (self.button, self.cancel):
            button.setMinimumWidth(150)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.cancel.setEnabled(False)
        row.addWidget(self.button, 1)
        row.addWidget(self.cancel, 1)
        layout.addWidget(self.table)
        layout.addLayout(row)
        self.button.clicked.connect(self.identify)
        self.cancel.clicked.connect(self.cancel_identify)

    def handle_serial_data(self, obj):
        if obj.get("type") != "emmc.identify.result":
            return
        if not obj.get("ok", False):
            self.console.log("IDENTIFY ERROR: " + str(obj.get("msg", "unknown error")))
            self.set_value("Status", "ERROR")
            self.finish()
            return
        cid = str(obj.get("cid", ""))
        csd = str(obj.get("csd", ""))
        ocr = int(obj.get("ocr", 0))
        self.set_value("CID", cid)
        self.set_value("CSD", csd)
        fields = self.decode_cid(cid)
        self.set_value("Manufacturer", fields["manufacturer"])
        self.set_value("MID", fields["mid"])
        self.set_value("CBX", fields["cbx"])
        self.set_value("OID", fields["oid"])
        self.set_value("Model", fields["pnm"])
        self.set_value("PRV", fields["prv"])
        self.set_value("Serial Number", fields["psn"])
        self.set_value("Manufacturing Date", fields["mdt"])
        self.set_value("Capacity", self.csd_capacity(csd))
        self.set_value("Sector Size", "512 bytes")
        self.set_value("Bus Width", "1-bit")
        self.set_value("Clock", "400 kHz (identify)")
        self.set_value("EXT_CSD", "Not requested")
        self.set_value("Status", f"OK (OCR 0x{ocr:08X})")
        self.console.log("IDENTIFY RESULT OK")
        self.finish()

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
            manufacturers = {
                0x13: "Micron",
                0x15: "Samsung",
                0x11: "Toshiba/Kioxia",
                0x45: "SanDisk/Western Digital",
                0xAD: "SK hynix",
            }
            return {
                "manufacturer": manufacturers.get(mid, "Unknown"),
                "mid": f"0x{mid:02X}",
                "cbx": f"0x{cbx:02X}",
                "oid": f"0x{oid:02X}",
                "pnm": pnm,
                "prv": f"0x{prv:02X}",
                "psn": f"0x{psn:08X}",
                "mdt": f"0x{mdt:02X}",
            }
        except Exception:
            return {
                "manufacturer": "", "mid": "", "cbx": "", "oid": "",
                "pnm": "", "prv": "", "psn": "", "mdt": ""
            }

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
        self.console.log("IDENTIFY REQUEST")
        try:
            self.emmc.identify()
            self.timeout.start(15000)
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
        self.console.log("IDENTIFY TIMEOUT (15s) - RP2040 tidak memberi hasil")
        self.finish()

    def finish(self):
        self.timeout.stop()
        self.busy = False
        self.button.setEnabled(True)
        self.cancel.setEnabled(False)
