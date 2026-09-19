import os
import re
from datetime import datetime

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QComboBox, QTextEdit


class SpecialTaskTab(QWidget):
    """UFI-style direct-execution service tasks.

    Selecting a task executes it immediately. This widget never opens another
    tab or dialog. Firmware support is required for every task exposed here.
    """

    TASKS = [
        ("FFU MODE", True),
        ("PARTITION CONFIG", True),
        ("RPMB INFO", True),
        ("SECURITY TASK", True),
        ("Backup Security", True),
        ("eMMC Health Check", True),
    ]

    BIN_MAGIC = 0xB0
    CH_DUMP_DATA = 0x04
    CH_DUMP_RUN = 0x05

    SECURITY_TOKENS = (
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

    def __init__(self, emmc, console):
        super().__init__()
        self.emmc = emmc
        self.console = console
        self.security_parts = []
        self.security_busy = False
        self.security_waiting_gpt = False
        self.security_waiting_buildprop = False
        self.security_index = 0
        self.security_file = None
        self.security_dir = None
        self.security_current = None
        self.security_received = 0
        self.security_expected = 0
        self.health_busy = False
        self.security_scan_only = False
        self.setup()

    @classmethod
    def task_names(cls):
        return [name for name, _ in cls.TASKS]

    def setup(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        layout.addWidget(QLabel("SPECIAL TASK"))

        self.task_combo = QComboBox()
        for name, enabled in self.TASKS:
            self.task_combo.addItem(name)
            self.task_combo.model().item(self.task_combo.count() - 1).setEnabled(enabled)
        layout.addWidget(self.task_combo)

        self.description = QTextEdit()
        self.description.setReadOnly(True)
        self.description.setMinimumHeight(180)
        layout.addWidget(self.description)
        layout.addStretch(1)

        self.task_combo.currentIndexChanged.connect(self._selection_changed)
        self.describe_task(0)

    def select_task(self, index, execute=False):
        if 0 <= index < self.task_combo.count():
            changed = self.task_combo.currentIndex() != index
            self.task_combo.setCurrentIndex(index)
            if execute and not changed:
                self.execute_task(index)

    def _selection_changed(self, index):
        self.describe_task(index)
        if index >= 0:
            self.execute_task(index)

    def describe_task(self, index):
        descriptions = {
            "FFU MODE": "Read and report FFU capability/status from EXT_CSD.",
            "PARTITION CONFIG": "Read EXT_CSD[179] and decode BOOT_ACK, BOOT_PARTITION_ENABLE and PARTITION_ACCESS.",
            "RPMB INFO": "Read RPMB size multiplier and relevant EXT_CSD information.",
            "SECURITY TASK": "Scan GPT and report security/identity partitions without writing them.",
            "Backup Security": "Scan GPT, detect security/identity partitions and back them up as binary files.",
            "eMMC Health Check": "Read PRE_EOL_INFO, DEVICE_LIFE_TIME_EST_TYP_A/B and RPMB_SIZE_MULT.",
        }
        self.description.setPlainText(descriptions.get(self.TASKS[index][0], ""))

    def execute_task(self, index=None):
        if index is None:
            index = self.task_combo.currentIndex()
        if index < 0 or index >= len(self.TASKS):
            return
        name = self.TASKS[index][0]
        direct = {
            "FFU MODE": "ffu",
            "PARTITION CONFIG": "partition_config",
            "RPMB INFO": "rpmb_info",
        }
        if name in direct:
            self.console.log(f"SPECIAL TASK: {name}")
            try:
                self.emmc.special_task(direct[name])
            except Exception as e:
                self.console.log(f"SPECIAL TASK ERROR: {e}")
            return
        if name == "SECURITY TASK":
            self.security_parts = []
            self.security_scan_only = True
            self.security_waiting_gpt = True
            self.security_waiting_buildprop = False
            self.console.log("SECURITY TASK: scanning GPT...")
            try:
                self.emmc.gpt()
            except Exception as e:
                self.security_waiting_gpt = False
                self.console.log(f"SECURITY TASK ERROR: {e}")
            return
        if name == "Backup Security":
            self.run_security_backup()
            return
        if name == "eMMC Health Check":
            self.run_health()

    def run_health(self):
        if self.health_busy:
            return
        self.health_busy = True
        self.console.log("eMMC HEALTH CHECK: reading EXT_CSD health fields...")
        try:
            self.emmc.layout()
        except Exception as e:
            self.health_busy = False
            self.console.log(f"HEALTH ERROR: {e}")

    def run_security_backup(self):
        if self.security_busy:
            self.console.log("SECURITY BACKUP: already running")
            return
        self.security_parts = []
        self.security_index = 0
        self.security_current = None
        self.security_scan_only = False
        self.security_waiting_gpt = True
        self.security_waiting_buildprop = True
        self.console.log("SECURITY BACKUP: scanning GPT for security/identity partitions...")
        try:
            self.emmc.gpt()
        except Exception as e:
            self.security_waiting_gpt = False
            self.security_waiting_buildprop = False
            self.console.log(f"SECURITY BACKUP ERROR: {e}")

    @classmethod
    def is_security_partition(cls, name):
        n = str(name).lower().strip()
        return bool(n) and any(token in n for token in cls.SECURITY_TOKENS)

    @staticmethod
    def safe_name(name):
        return re.sub(r"[^A-Za-z0-9._-]+", "_", str(name).strip()) or "partition"

    def handle_serial_data(self, obj):
        typ = obj.get("type")

        if typ == "emmc.special.result":
            if obj.get("ok"):
                self.console.log(f"SPECIAL TASK OK: {obj.get('task', '')}")
                for key, value in obj.items():
                    if key not in ("type", "ok", "task"):
                        self.console.log(f"{key.upper()} : {value}")
            else:
                self.console.log("SPECIAL TASK ERROR: " + str(obj.get("msg", "unknown error")))
            return

        if typ == "emmc.layout.result" and self.health_busy:
            self.health_busy = False
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
            pre_text = {1: "NORMAL", 2: "WARNING", 3: "URGENT"}.get(pre, "UNKNOWN")
            self.console.log(
                f"eMMC HEALTH: LIFE_A=0x{a:02X} LIFE_B=0x{b:02X} "
                f"PRE_EOL=0x{pre:02X} {pre_text} RPMB_SIZE_MULT=0x{rpmb:02X}"
            )
            return

        if typ == "emmc.gpt.begin" and (self.security_waiting_gpt or self.security_busy):
            self.security_parts = []
            return

        if typ == "emmc.gpt.partition" and (self.security_waiting_gpt or self.security_busy):
            name = str(obj.get("name", "")).strip()
            if self.is_security_partition(name):
                sectors = int(obj.get("sectors", 0))
                start = int(obj.get("start_lba", 0))
                self.console.log(f"SECURITY CANDIDATE: {name} LBA={start} sectors={sectors}")
                if sectors > 0:
                    self.security_parts.append({"name": name, "start": start, "sectors": sectors})
            return

        if typ == "emmc.gpt.end" and self.security_waiting_gpt:
            self.security_waiting_gpt = False
            if not obj.get("ok", True):
                self.security_waiting_buildprop = False
                self.console.log("SECURITY TASK/Backup ERROR: GPT scan failed")
                return
            if self.security_scan_only:
                self.console.log(f"SECURITY TASK COMPLETE: {len(self.security_parts)} candidate partition(s)")
                return
            if self.security_waiting_buildprop:
                return
            self._start_security_backup()
            return

        if typ == "emmc.buildprop.end" and self.security_waiting_buildprop:
            self.security_waiting_buildprop = False
            if self.security_busy and not self.security_waiting_gpt:
                self._start_security_backup()
            return

        if typ == "emmc.dump.status" and self.security_busy:
            state = str(obj.get("state", ""))
            if state == "complete":
                self._finish_security_file(True)
            elif state in ("error", "stopped"):
                self._finish_security_file(False)
            return

    def _start_security_backup(self):
        if self.security_busy:
            return
        if not self.security_parts:
            self.console.log("SECURITY BACKUP: no known security partitions found in GPT")
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.security_dir = os.path.abspath(f"security_backup_{stamp}")
        try:
            os.makedirs(self.security_dir, exist_ok=True)
        except OSError as e:
            self.console.log(f"SECURITY BACKUP DIRECTORY ERROR: {e}")
            return
        self.security_busy = True
        self.security_index = 0
        self.console.log(f"SECURITY BACKUP: {len(self.security_parts)} partition(s) -> {self.security_dir}")
        self._start_next_security_partition()

    def _start_next_security_partition(self):
        if self.security_index >= len(self.security_parts):
            self.security_busy = False
            self.security_current = None
            self.security_file = None
            self.console.log(f"SECURITY BACKUP COMPLETE: {self.security_dir}")
            return
        p = self.security_parts[self.security_index]
        path = os.path.join(self.security_dir, self.safe_name(p["name"]) + ".bin")
        try:
            self.security_file = open(path, "w+b")
            self.security_file.truncate(p["sectors"] * 512)
        except OSError as e:
            self.console.log(f"SECURITY BACKUP FILE ERROR ({p['name']}): {e}")
            self.security_index += 1
            self._start_next_security_partition()
            return
        self.security_current = p
        self.security_received = 0
        self.security_expected = p["sectors"] * 512
        self.console.log(f"SECURITY BACKUP: {p['name']} LBA={p['start']} sectors={p['sectors']}")
        try:
            self.emmc.dump_start(p["start"], p["sectors"], 512, True, 3, 0)
        except Exception as e:
            self.console.log(f"SECURITY BACKUP START ERROR ({p['name']}): {e}")
            self._finish_security_file(False)

    def handle_binary_data(self, frame):
        if not self.security_busy or len(frame) < 8 or frame[0] != self.BIN_MAGIC:
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
        if len(payload) != count or not self.security_file:
            return
        self.security_file.seek(offset)
        self.security_file.write(payload)
        self.security_received = max(self.security_received, offset + count)

    def _finish_security_file(self, success):
        path = getattr(self.security_file, "name", None) if self.security_file else None
        if self.security_file:
            try:
                self.security_file.flush()
                self.security_file.close()
            except Exception:
                pass
        self.security_file = None
        p = self.security_current
        if not p:
            return
        if success and self.security_received >= self.security_expected:
            self.console.log(f"SECURITY BACKUP OK: {p['name']} -> {path}")
        else:
            self.console.log(f"SECURITY BACKUP FAILED: {p['name']} -> {path}")
        self.security_current = None
        self.security_index += 1
        self._start_next_security_partition()
