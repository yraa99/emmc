from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QGroupBox, QTextEdit
)
from PyQt6.QtCore import Qt


class SpecialTaskTab(QWidget):
    """UFI-style eMMC special-task catalogue.

    The catalogue mirrors eMMC tasks documented by UFI Box. Actions that
    require firmware protocols not implemented by this RP2040 project stay
    disabled instead of pretending to work.
    """

    TASKS = [
        # eMMC ToolBox special tasks documented by UFI
        ("eMMC Health Check", True),
        ("Update eMMC5.x Firmware", False),
        ("Read eMMC Firmware / FFU", False),
        ("Secure Wipe - TRIM", False),
        ("Secure Wipe - Sanitize", False),
        ("eMMC Full Reset", False),
        ("Force Boot Mode", False),
        ("Resize User Partition", False),
        ("Repair CID", False),
        ("NAND Test", False),
        # UFI Android/flash service special-task catalogue
        ("Full Erase", False),
        ("Full Erase (Except Bootloader)", False),
        ("Clean Viruses", False),
        ("Factory Reset", False),
        ("Patch Boot Image (Insecure Boot)", False),
        ("Clear User Locks (Code / PIN / Gesture / Fingerprint)", False),
        ("Clear FRP Lock", False),
        ("Remove Google Account", False),
        ("Reset Xiaomi (Mi Account) Lock", False),
        ("Reset Meizu (Flyme Account) Lock", False),
        ("Wipe Data & App", False),
        ("Wipe Data Only", False),
        ("Wipe App Data", False),
    ]

    def __init__(self, emmc, console):
        super().__init__()
        self.emmc = emmc
        self.console = console
        self.setup()

    @classmethod
    def task_names(cls):
        return [name for name, _ in cls.TASKS]

    def setup(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel("SPECIAL TASK")
        title.setObjectName("section_title")
        layout.addWidget(title)

        info = QLabel(
            "UFI eMMC special-task catalogue. "
            "Tasks without an RP2040 protocol are shown but kept disabled."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.task_combo = QComboBox()
        for name, enabled in self.TASKS:
            self.task_combo.addItem(name)
            self.task_combo.model().item(self.task_combo.count() - 1).setEnabled(enabled)
        layout.addWidget(self.task_combo)

        self.description = QTextEdit()
        self.description.setReadOnly(True)
        self.description.setMinimumHeight(110)
        layout.addWidget(self.description)

        actions = QHBoxLayout()
        self.execute = QPushButton("EXECUTE")
        self.execute.setEnabled(False)
        self.backup = QPushButton("SELECT FILE")
        self.backup.setEnabled(False)
        actions.addWidget(self.execute)
        actions.addWidget(self.backup)
        layout.addLayout(actions)
        layout.addStretch(1)

        self.task_combo.currentIndexChanged.connect(self.describe_task)
        self.execute.clicked.connect(self.execute_task)
        self.describe_task(0)

    def select_task(self, index):
        if 0 <= index < self.task_combo.count():
            self.task_combo.setCurrentIndex(index)

    def describe_task(self, index):
        if index < 0 or index >= len(self.TASKS):
            return
        name, enabled = self.TASKS[index]
        if enabled:
            text = f"{name}\n\nAvailable in the current RP2040 firmware."
        else:
            text = (
                f"{name}\n\n"
                "UFI provides this task, but the current RP2040 firmware "
                "does not expose a safe command for it yet. "
                "No destructive/fake command is sent."
            )
        self.description.setPlainText(text)
        self.execute.setEnabled(enabled)

    def execute_task(self):
        name = self.task_combo.currentText()
        if name == "eMMC Health Check":
            self.execute.setEnabled(False)
            self.console.log("eMMC HEALTH CHECK: reading EXT_CSD health fields...")
            try:
                self.emmc.layout()
            except Exception as e:
                self.console.log(f"HEALTH ERROR: {e}")
                self.execute.setEnabled(True)
            return
        self.console.log(f"SPECIAL TASK: {name} is not implemented in RP2040 firmware")

    def handle_serial_data(self, obj):
        if obj.get("type") != "emmc.layout.result":
            return
        self.execute.setEnabled(True)
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
        a, b, pre = ext[268], ext[269], ext[267]
        life_a = "0x%02X" % a
        life_b = "0x%02X" % b
        pre_text = {1: "NORMAL", 2: "WARNING", 3: "URGENT"}.get(pre, "UNKNOWN")
        self.console.log(f"eMMC HEALTH: LIFE_A={life_a} LIFE_B={life_b} PRE_EOL=0x{pre:02X} {pre_text}")
        self.console.log(f"eMMC HEALTH: RPMB_SIZE_MULT=0x{ext[168]:02X}")
