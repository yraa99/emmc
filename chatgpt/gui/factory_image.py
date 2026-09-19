from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QFileDialog, QComboBox, QTableWidget, QTableWidgetItem,
    QGroupBox, QLineEdit, QMessageBox, QSizePolicy
)
import os


class FactoryImageTab(QWidget):
    """Factory image preparation/inspection.

    The current RP2040 firmware is read-only. This tab therefore provides the
    file-selection, format detection and image inventory workflow, while actual
    eMMC flashing stays disabled until a matching write backend exists.
    """

    FILTERS = (
        "Factory Images (*.xml *.xlm *.scatter *.txt *.pac *.ofp *.bin *.img *.zip)",
        "XML (*.xml)",
        "Scatter (*.scatter *.txt)",
        "PAC (*.pac)",
        "OFP (*.ofp)",
        "Images (*.bin *.img)",
        "All Files (*)",
    )

    def __init__(self, console):
        super().__init__()
        self.console = console
        self.selected_path = ""
        self.setup()

    def setup(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel("FACTORY IMAGE")
        title.setObjectName("section_title")
        layout.addWidget(title)

        select_box = QGroupBox("IMAGE SOURCE")
        select_layout = QGridLayout(select_box)
        select_layout.setHorizontalSpacing(8)
        select_layout.setVerticalSpacing(8)

        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        self.path_edit.setPlaceholderText("Select XML / Scatter / PAC / OFP / image package")

        self.format_box = QComboBox()
        self.format_box.addItems(["AUTO", "XML", "SCATTER", "PAC", "OFP", "BIN/IMG"])

        self.browse = QPushButton("SELECT FILE")
        self.inspect = QPushButton("INSPECT")

        select_layout.addWidget(QLabel("FILE"), 0, 0)
        select_layout.addWidget(self.path_edit, 0, 1, 1, 3)
        select_layout.addWidget(self.browse, 0, 4)
        select_layout.addWidget(QLabel("TYPE"), 1, 0)
        select_layout.addWidget(self.format_box, 1, 1)
        select_layout.addWidget(self.inspect, 1, 2)

        layout.addWidget(select_box)

        info_box = QGroupBox("IMAGE INVENTORY")
        info_layout = QVBoxLayout(info_box)
        self.info = QTableWidget(0, 4)
        self.info.setHorizontalHeaderLabels(["ITEM", "FORMAT", "SIZE", "STATUS"])
        self.info.horizontalHeader().setStretchLastSection(True)
        self.info.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        info_layout.addWidget(self.info)
        layout.addWidget(info_box, 1)

        action_box = QGroupBox("FACTORY FLASH")
        action_layout = QHBoxLayout(action_box)
        self.prepare = QPushButton("PREPARE")
        self.flash = QPushButton("FLASH")
        self.clear = QPushButton("CLEAR")
        self.flash.setEnabled(False)
        self.flash.setToolTip("Disabled: current RP2040 firmware has no safe factory-image write protocol.")
        for button in (self.prepare, self.flash, self.clear):
            button.setMinimumHeight(32)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            action_layout.addWidget(button)
        layout.addWidget(action_box)

        self.browse.clicked.connect(self.select_file)
        self.inspect.clicked.connect(self.inspect_file)
        self.prepare.clicked.connect(self.inspect_file)
        self.clear.clicked.connect(self.clear_image)
        self.flash.clicked.connect(self.flash_disabled)

    def log(self, text):
        if self.console:
            self.console.log(str(text))

    def select_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Factory Image", "", ";;".join(self.FILTERS)
        )
        if not path:
            return
        self.selected_path = path
        self.path_edit.setText(path)
        self.inspect_file()

    def detect_format(self, path):
        ext = os.path.splitext(path)[1].lower()
        if ext in (".xml", ".xlm"):
            return "XML"
        if ext in (".scatter", ".txt"):
            return "SCATTER"
        if ext == ".pac":
            return "PAC"
        if ext == ".ofp":
            return "OFP"
        if ext in (".bin", ".img"):
            return "BIN/IMG"
        return "UNKNOWN"

    def detect_soc(self, path):
        try:
            with open(path, "rb") as f:
                sample = f.read(1024 * 1024)
            text = sample.decode("latin-1", errors="ignore").lower()
        except OSError:
            return "UNKNOWN"
        checks = (
            ("QUALCOMM / MSM / SNAPDRAGON", ("qualcomm", "snapdragon", "msm", "qcom")),
            ("MEDIATEK / MTK", ("mediatek", "mtk", "mt65", "mt67", "mt68")),
            ("UNISOC / SPREADTRUM", ("unisoc", "spreadtrum", "sc986", "sc773")),
            ("HISILICON / HUAWEI", ("hisilicon", "kirin", "hisi")),
            ("SAMSUNG / EXYNOS", ("exynos", "samsung")),
        )
        for label, tokens in checks:
            if any(token in text for token in tokens):
                return label
        return "UNKNOWN"

    def inspect_file(self):
        path = self.selected_path or self.path_edit.text().strip()
        if not path:
            self.log("FACTORY IMAGE: select an image first")
            return
        if not os.path.isfile(path):
            self.log("FACTORY IMAGE: file does not exist")
            return

        fmt = self.detect_format(path)
        try:
            size = os.path.getsize(path)
        except OSError as e:
            self.log(f"FACTORY IMAGE: {e}")
            return

        self.info.setRowCount(0)
        soc = self.detect_soc(path)
        rows = [
            ("File", os.path.basename(path), str(size), "READY"),
            ("Format", fmt, "-", "DETECTED"),
            ("SoC", soc, "-", "DETECTED" if soc != "UNKNOWN" else "NOT DETECTED"),
            ("Path", os.path.dirname(path), "-", "SELECTED"),
        ]
        for values in rows:
            row = self.info.rowCount()
            self.info.insertRow(row)
            for col, value in enumerate(values):
                self.info.setItem(row, col, QTableWidgetItem(str(value)))

        self.log(f"FACTORY IMAGE: {fmt} / {soc} - {os.path.basename(path)}")
        self.log("FACTORY IMAGE: inspection ready; flashing remains disabled until a write backend is implemented")

    def clear_image(self):
        self.selected_path = ""
        self.path_edit.clear()
        self.info.setRowCount(0)

    def flash_disabled(self):
        QMessageBox.information(
            self,
            "Flash disabled",
            "Factory-image flashing is disabled because the active RP2040 firmware does not expose a safe eMMC write protocol.",
        )
