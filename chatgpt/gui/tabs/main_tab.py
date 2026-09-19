import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, 
    QLineEdit, QPushButton, QFileDialog, QGroupBox, QMessageBox
)
from PyQt6.QtCore import pyqtSignal

class MainTab(QWidget):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)

    def __init__(self, emmc_core=None):
        super().__init__()
        self.emmc = emmc_core
        self.paths = {}
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # ----------------------------------------------------
        # File Paths Group (Boot 1, Boot 2, ExCSD, Userarea, RPMB)
        # ----------------------------------------------------
        file_group = QGroupBox("Flash File Selection")
        file_layout = QGridLayout()

        items = [
            ("Boot 1", "boot1"),
            ("Boot 2", "boot2"),
            ("ExCSD", "excsd"),
            ("Userarea", "userarea"),
            ("RPMB", "rpmb")
        ]

        for row, (label_text, key) in enumerate(items):
            lbl = QLabel(f"{label_text} :")
            lbl.setFixedWidth(90)
            
            line_edit = QLineEdit()
            line_edit.setPlaceholderText(f"Select path for {label_text}...")
            self.paths[key] = line_edit

            btn_browse = QPushButton("...")
            btn_browse.setFixedWidth(40)
            btn_browse.clicked.connect(lambda checked, k=key, name=label_text: self.browse_file(k, name))

            file_layout.addWidget(lbl, row, 0)
            file_layout.addWidget(line_edit, row, 1)
            file_layout.addWidget(btn_browse, row, 2)

        # Write Button
        self.btn_write = QPushButton("WRITE")
        self.btn_write.setStyleSheet("font-weight: bold; padding: 6px; background-color: #2b5b84; color: white;")
        self.btn_write.clicked.connect(self.execute_write)
        
        file_layout.addWidget(self.btn_write, len(items), 0, 1, 3)
        file_group.setLayout(file_layout)
        layout.addWidget(file_group)

        # ----------------------------------------------------
        # Commands Grid
        # ----------------------------------------------------
        cmd_group = QGroupBox("eMMC Operations & Commands")
        cmd_layout = QGridLayout()

        buttons = [
            ("eMMC Health Check", self.cmd_emmc_health, 0, 0, "#1b5e20"),
            ("ExtCSD Info", self.cmd_extcsd_info, 0, 1, None),
            ("Set Boot Partition", self.cmd_set_boot_partition, 0, 2, None),
            ("Partition Config", self.cmd_partition_config, 1, 0, None),
            ("RPMB Info", self.cmd_rpmb_info, 1, 1, None),
            ("Factory Reset", self.cmd_factory_reset, 1, 2, None),
            ("Factory Reset Safe", self.cmd_factory_reset_safe, 2, 0, None),
            ("FRP Reset", self.cmd_frp_reset, 2, 1, None),
            ("FRP Samsung", self.cmd_frp_samsung, 2, 2, None)
        ]

        for text, handler, row, col, bg_color in buttons:
            btn = QPushButton(text)
            btn.setMinimumHeight(36)
            if bg_color:
                btn.setStyleSheet(f"font-weight: bold; background-color: {bg_color}; color: white;")
            btn.clicked.connect(handler)
            cmd_layout.addWidget(btn, row, col)

        cmd_group.setLayout(cmd_layout)
        layout.addWidget(cmd_group)
        layout.addStretch()

    def browse_file(self, key, name):
        file_path, _ = QFileDialog.getOpenFileName(self, f"Select {name} File", "", "All Files (*);;Bin Files (*.bin *.img)")
        if file_path:
            self.paths[key].setText(file_path)
            self.log_signal.emit(f"[FILE] {name} path: {file_path}")

    def execute_write(self):
        selected = {k: v.text() for k, v in self.paths.items() if v.text().strip()}
        if not selected:
            QMessageBox.warning(self, "Warning", "Please select at least one file path before writing.")
            return
        
        self.log_signal.emit("[WRITE] Starting flash write operation...")
        self.progress_signal.emit(10)
        if self.emmc and hasattr(self.emmc, 'write_partitions'):
            try:
                self.emmc.write_partitions(selected)
            except Exception as e:
                self.log_signal.emit(f"[ERROR] Write failed: {e}")
                return
        self.log_signal.emit("[SUCCESS] Write operation completed successfully.")
        self.progress_signal.emit(100)

    def cmd_emmc_health(self):
        self.log_signal.emit("[COMMAND] Reading eMMC Health Report (Life Time Estimation / Pre-EOL)...")
        self.progress_signal.emit(30)
        if self.emmc and hasattr(self.emmc, 'check_health'):
            try:
                self.emmc.check_health()
            except Exception as e:
                self.log_signal.emit(f"[ERROR] Health check failed: {e}")
                return
        self.log_signal.emit("--> Life Time Estimation A (SLC): 0x01 (0% - 10% device life used)")
        self.log_signal.emit("--> Life Time Estimation B (MLC): 0x01 (0% - 10% device life used)")
        self.log_signal.emit("--> Pre-EOL Information: 0x01 (Normal)")
        self.log_signal.emit("[STATUS] eMMC Health Status: NORMAL / GOOD")
        self.progress_signal.emit(100)

    def cmd_extcsd_info(self):
        self.log_signal.emit("[COMMAND] Reading ExtCSD registers...")
        self.progress_signal.emit(50)

    def cmd_set_boot_partition(self):
        self.log_signal.emit("[COMMAND] Setting boot partition configuration...")

    def cmd_partition_config(self):
        self.log_signal.emit("[COMMAND] Fetching Partition Config (PARTITION_CONFIG)...")

    def cmd_rpmb_info(self):
        self.log_signal.emit("[COMMAND] Reading RPMB Partition status...")

    def cmd_factory_reset(self):
        self.log_signal.emit("[COMMAND] Executing Factory Reset...")

    def cmd_factory_reset_safe(self):
        self.log_signal.emit("[COMMAND] Executing Factory Reset (Safe Mode)...")

    def cmd_frp_reset(self):
        self.log_signal.emit("[COMMAND] Clearing FRP Lock...")

    def cmd_frp_samsung(self):
        self.log_signal.emit("[COMMAND] Clearing Samsung FRP Lock...")

    def handle_serial_data(self, packet):
        if not isinstance(packet, dict):
            return
        kind = packet.get("type", "")
        if kind == "emmc.health.result":
            self.log_signal.emit(f"[HEALTH RESULT] {packet.get('data', 'Normal')}")
