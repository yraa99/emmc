from PyQt6.QtWidgets import QTextEdit


class Console(QTextEdit):

    def __init__(self):
        super().__init__()

        self.setReadOnly(True)



    def log(self,text):

        self.append(
            str(text)
        )