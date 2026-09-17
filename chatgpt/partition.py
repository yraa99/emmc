from PyQt6.QtWidgets import *


class PartitionTab(QWidget):

    def __init__(self):

        super().__init__()

        layout=QVBoxLayout()


        self.text=QTextEdit()

        self.text.setReadOnly(True)


        layout.addWidget(
            self.text
        )


        self.setLayout(
            layout
        )