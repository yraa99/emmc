from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit

class UserAreaTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.info_label = QLabel("USER AREA Manager & Partition Table")
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setPlaceholderText("Userarea partition details will be listed here...")
        layout.addWidget(self.info_label)
        layout.addWidget(self.text)

    def handle_serial_data(self, packet):
        pass

    def handle_binary_data(self, data):
        pass
