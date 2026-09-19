from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QLineEdit, QHBoxLayout, QFileDialog

class FactoryImageTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        lbl = QLabel("Factory Image Flashing & Extraction")
        lbl.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(lbl)

        file_layout = QHBoxLayout()
        self.txt_path = QLineEdit()
        self.txt_path.setPlaceholderText("Select Factory Firmware / Rawprogram XML...")
        btn_browse = QPushButton("Browse")
        btn_browse.clicked.connect(self.browse)

        file_layout.addWidget(self.txt_path)
        file_layout.addWidget(btn_browse)
        layout.addLayout(file_layout)

        btn_flash = QPushButton("Flash Factory Image")
        btn_flash.setStyleSheet("font-weight: bold; background-color: #1976d2; color: white; padding: 6px;")
        layout.addWidget(btn_flash)
        layout.addStretch()

    def browse(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Factory Image File", "", "All Files (*)")
        if file_path:
            self.txt_path.setText(file_path)

    def handle_serial_data(self, packet):
        pass
