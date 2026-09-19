from PyQt6.QtWidgets import QTextEdit
from datetime import datetime


class Console(QTextEdit):
    """Compact service log: show reader results, not serial/debug chatter."""

    VISIBLE_PREFIXES = (
        "eMMC IDENTIFY",
        "Manufacturer :",
        "Model        :",
        "CID          :",
        "CSD          :",
        "OCR          :",
        "RCA          :",
        "Capacity     :",
        "EXT_CSD Rev  :",
        "IDENTIFY OK",
        "IDENTIFY ERROR",
        "Reading system info",
        "Brand:",
        "Model:",
        "Name:",
        "Product:",
        "Sdk ver:",
        "Code name:",
        "Incremental:",
        "Build id:",
        "Android ver:",
        "Miui ver:",
        "Security patch:",
        "Timezone:",
        "Platform:",
        "Cpu Abi:",
        "Build Date:",
        "Fingerprint:",
        "IMEI:",
        "MAC:",
        "Internal storage :",
        "eMMC HEALTH",
        "HEALTH ERROR",
        "EXT_CSD READ OK",
        "EXT_CSD ERROR",
        "READ COMPLETE:",
        "READ FAILED:",
        "READ STOPPED:",
        "READ ERROR:",
        "READ START ERROR:",
        "READ FILE ERROR:",
        "VERIFY OK:",
        "VERIFY FAILED:",
        "VERIFY ERROR:",
        "GPT ERROR:",
        "GPT/system scan timeout",
    )

    def __init__(self):
        super().__init__()
        self.setReadOnly(True)

    def _visible(self, text):
        text = str(text).strip()
        return any(text.startswith(prefix) for prefix in self.VISIBLE_PREFIXES)

    def log(self, text):
        text = str(text).strip()
        if not text or not self._visible(text):
            return
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.append(f"[{timestamp}] {text}")
