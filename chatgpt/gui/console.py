from PyQt6.QtWidgets import QTextEdit
from datetime import datetime


class Console(QTextEdit):

    def __init__(self):

        super().__init__()

        self.setReadOnly(True)



    def log(self,text):

        t=datetime.now().strftime(
            "%H:%M:%S"
        )

        self.append(
            f"[{t}] {text}"
        )