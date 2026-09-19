from PyQt6.QtWidgets import QTextEdit
from PyQt6.QtGui import QTextCharFormat, QColor, QFont
from datetime import datetime


class Console(QTextEdit):
    """Compact service log with semantic colors for OK/error/warning/info."""

    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setAcceptRichText(False)

    @staticmethod
    def _color_for(text):
        upper = str(text).upper()
        if any(x in upper for x in ("ERROR", "FAILED", "FAIL", "TIMEOUT", "NOT FOUND", "UNKNOWN COMMAND")):
            return QColor("#ff5c6c")
        if any(x in upper for x in (" OK", "OK:", "COMPLETE", "SUCCESS", "READY", "CONNECTED")) or upper.endswith(" OK"):
            return QColor("#5ee68a")
        if any(x in upper for x in ("WARNING", "WARN", "SKIP", "NOT EXPOSED", "CANDIDATE")):
            return QColor("#ffc857")
        if any(x in upper for x in ("READ", "WRITE", "SCAN", "IDENTIFY", "GPT", "HEALTH", "SECURITY", "BACKUP")):
            return QColor("#61c7ff")
        return QColor("#d7dde2")

    def log(self, text):
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {text}"
        cursor = self.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(self._color_for(line))
        fmt.setFont(QFont("Consolas", 9))
        cursor.insertText(line + "\\n", fmt)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()
