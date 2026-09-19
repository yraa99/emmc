from PyQt6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QLabel, QComboBox, QPushButton, QGroupBox


class SetBootTab(QWidget):
    """Dedicated SetBoot configuration page.

    Unlike Special Task, SetBoot intentionally opens as a service page.
    """

    def __init__(self, emmc, console):
        super().__init__()
        self.emmc = emmc
        self.console = console
        self.setup()

    def setup(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        root.addWidget(QLabel("SET BOOT"))

        box = QGroupBox("eMMC BOOT CONFIGURATION")
        grid = QGridLayout(box)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)

        grid.addWidget(QLabel("Chipset / SoC"), 0, 0)
        self.chipset = QComboBox()
        self.chipset.addItems([
            "Generic eMMC", "Qualcomm", "MediaTek",
            "Unisoc / Spreadtrum", "Samsung / Exynos", "Huawei / HiSilicon",
        ])
        grid.addWidget(self.chipset, 0, 1)

        grid.addWidget(QLabel("Boot source"), 1, 0)
        self.source = QComboBox()
        self.source.addItems(["Disabled", "BOOT1", "BOOT2", "User Area"])
        grid.addWidget(self.source, 1, 1)

        grid.addWidget(QLabel("Boot bus"), 2, 0)
        self.bus = QComboBox()
        self.bus.addItems(["x1", "x4", "x8"])
        self.bus.setCurrentText("x8")
        grid.addWidget(self.bus, 2, 1)

        grid.addWidget(QLabel("Reset boot bus"), 3, 0)
        self.reset = QComboBox()
        self.reset.addItems(["retain", "reset"])
        self.reset.setCurrentText("retain")
        grid.addWidget(self.reset, 3, 1)

        grid.addWidget(QLabel("BOOT_ACK"), 4, 0)
        self.ack = QComboBox()
        self.ack.addItems(["Disabled", "Enabled"])
        grid.addWidget(self.ack, 4, 1)

        grid.addWidget(QLabel("Boot mode"), 5, 0)
        self.mode = QComboBox()
        self.mode.addItems(["Backward compatible / SDR", "High Speed SDR", "DDR"])
        grid.addWidget(self.mode, 5, 1)

        self.read_button = QPushButton("READ SETBOOT")
        self.write_button = QPushButton("WRITE SETBOOT")
        grid.addWidget(self.read_button, 6, 0)
        grid.addWidget(self.write_button, 6, 1)

        root.addWidget(box)
        root.addStretch(1)

        self.read_button.clicked.connect(self.read_setboot)
        self.write_button.clicked.connect(self.write_setboot)

    def read_setboot(self):
        self.console.log("SETBOOT: reading EXT_CSD boot configuration...")
        try:
            self.emmc.setboot_read()
        except Exception as e:
            self.console.log(f"SETBOOT READ ERROR: {e}")

    def write_setboot(self):
        part = {"Disabled": 0, "BOOT1": 1, "BOOT2": 2, "User Area": 7}[self.source.currentText()]
        width = {"x1": 0, "x4": 1, "x8": 2}[self.bus.currentText()]
        reset = 1 if self.reset.currentText() == "reset" else 0
        mode = self.mode.currentIndex()
        ack = 1 if self.ack.currentText() == "Enabled" else 0
        self.console.log(
            f"SETBOOT WRITE: partition={part} bus={self.bus.currentText()} "
            f"reset={reset} mode={mode} ack={ack}"
        )
        try:
            self.emmc.setboot_write(part, width, reset, mode, ack)
        except Exception as e:
            self.console.log(f"SETBOOT WRITE ERROR: {e}")

    def handle_serial_data(self, obj):
        typ = obj.get("type")
        if typ == "emmc.setboot.result":
            if obj.get("ok"):
                self.console.log(
                    "SETBOOT OK: "
                    f"PARTITION_CONFIG=0x{int(obj.get('partition_config', 0)):02X} "
                    f"BOOT_PARTITION_ENABLE={obj.get('boot_partition', '?')} "
                    f"PARTITION_ACCESS={obj.get('partition_access', '?')} "
                    f"BOOT_ACK={obj.get('boot_ack', '?')} "
                    f"BOOT_BUS_WIDTH=0x{int(obj.get('boot_bus_width', 0)):02X}"
                )
            else:
                self.console.log("SETBOOT ERROR: " + str(obj.get("msg", "unknown error")))
