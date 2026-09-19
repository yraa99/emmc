from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox,
    QTabWidget, QSplitter, QGroupBox, QComboBox, QProgressBar,
    QSizePolicy, QStackedWidget, QLineEdit, QGridLayout, QFileDialog
)
from PyQt6.QtCore import Qt, QTimer, QDateTime


class FileDropEdit(QLineEdit):
    """Read-only file field that also accepts UFI-style drag & drop."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path:
                self.setText(path)
                event.acceptProposedAction()
        else:
            event.ignore()


from gui.console import Console
from gui.identify import IdentifyTab
from gui.boot_extcsd import BootExtCSDTab
from gui.userarea import UserAreaTab
from gui.health import HealthTab
from gui.special_task import SpecialTaskTab
from gui.isp_test import ISPTestTab
from gui.adb_fastboot import ADBFastbootTab
from gui.factory_image import FactoryImageTab


class MainWindow(QMainWindow):
    """Main service-tool shell matching the user's hand-drawn layout.

    Default MAIN view:
      top connection/action bar
      MAIN | FLASH | ADB FASTBOOT
      30% LOG / 70% work area
      Boot 1 / Boot 2 / ExtCSD / Userarea command rail
      user-area partition table
      Process / Special Task / Dark-Light footer
    """

    def __init__(self, emmc, serial):
        super().__init__()
        self.emmc = emmc
        self.serial = serial
        self.last_pico_device = None
        self.identify_sequence = False
        self.light_theme = False

        self.operation_timer = QTimer(self)
        self.operation_timer.setSingleShot(True)
        self.operation_timer.timeout.connect(self.operation_timeout)

        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_clock)
        self.clock_timer.start(1000)

        self.setWindowTitle("RP2040 eMMC PROGRAMMER By YADITAMA")
        self.resize(1280, 800)
        self.setMinimumSize(980, 620)

        self.console = Console()
        self.program_backup = {"active": False, "key": None, "file": None, "path": None, "expected": 0, "received": 0}
        self.setupUI()

        self.serial.set_disconnect_callback(self.on_serial_disconnect)
        self.refresh_device(auto_connect=True)

        self.watchdog = QTimer(self)
        self.watchdog.timeout.connect(self.check_connection)
        self.watchdog.start(1000)

        self._install_command_log_reset()
        self.update_clock()

    def setupUI(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(5, 5, 5, 5)
        root.setSpacing(4)

        # ------------------------------------------------------
        # TOP BAR - deliberately compact, matching the sketch.
        # ------------------------------------------------------
        top = QHBoxLayout()
        top.setSpacing(4)

        top.addWidget(QLabel("Port:"))

        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(210)
        self.port_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        top.addWidget(self.port_combo)

        self.btn_refresh = QPushButton("Refresh")
        self.btn_connect = QPushButton("Connect")
        self.btn_identify = QPushButton("IDENTIFY")
        for button in (self.btn_refresh, self.btn_connect, self.btn_identify):
            button.setMinimumWidth(82)
            button.setMinimumHeight(28)
        top.addWidget(self.btn_refresh)
        top.addWidget(self.btn_connect)
        top.addWidget(self.btn_identify)

        top.addStretch(1)

        self.clock_label = QLabel()
        self.clock_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.clock_label.setMinimumWidth(185)
        top.addWidget(self.clock_label)

        self.connection_status = QLabel("DISCONNECTED")
        self.connection_status.setObjectName("status_disconnected")
        top.addWidget(self.connection_status)

        self.rp_status = QLabel("RP2040")
        top.addWidget(self.rp_status)

        self.btn_refresh.clicked.connect(self.refresh_device)
        self.btn_connect.clicked.connect(self.toggle_connection)
        self.btn_identify.clicked.connect(self.main_identify)
        root.addLayout(top)

        # ------------------------------------------------------
        # MAIN / FLASH / ADB FASTBOOT - exactly the sketch's
        # three primary sections.
        # ------------------------------------------------------
        self.category_tabs = QTabWidget()
        self.category_tabs.setObjectName("categoryTabs")
        self.category_tabs.tabBarClicked.connect(self.on_category_clicked)

        self.main_page = self._build_main_page()
        self.flash_page = self._build_flash_page()
        self.adb_page = self._build_adb_page()

        self.category_tabs.addTab(self.main_page, "MAIN")
        self.category_tabs.addTab(self.flash_page, "Flash")
        self.category_tabs.addTab(self.adb_page, "ADB Fastboot")
        root.addWidget(self.category_tabs, 1)

        # ------------------------------------------------------
        # FOOTER - Process / Special Task / Dark-Light.
        # ------------------------------------------------------
        footer = QHBoxLayout()
        footer.setSpacing(4)

        process_box = QHBoxLayout()
        process_box.setSpacing(5)
        process_box.addWidget(QLabel("Process :"))

        self.operation_label = QLabel("Ready")
        self.operation_label.setMinimumWidth(120)
        process_box.addWidget(self.operation_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setMinimumWidth(170)
        process_box.addWidget(self.progress)

        self.btn_cancel = QPushButton("STOP")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setMinimumWidth(65)
        process_box.addWidget(self.btn_cancel)

        process_widget = QWidget()
        process_widget.setLayout(process_box)
        footer.addWidget(process_widget, 1)

        special_widget = QWidget()
        special_layout = QHBoxLayout(special_widget)
        special_layout.setContentsMargins(0, 0, 0, 0)
        special_layout.setSpacing(4)
        special_layout.addWidget(QLabel("Special task :"))
        self.special_combo = QComboBox()
        self.special_combo.addItems(self.special.task_names())
        self.special_combo.setMinimumWidth(230)
        self.special_execute = QPushButton("OPEN")
        self.special_execute.setMinimumWidth(60)
        special_layout.addWidget(self.special_combo, 1)
        special_layout.addWidget(self.special_execute)
        footer.addWidget(special_widget, 1)

        self.theme_button = QPushButton("Dark / Light")
        self.theme_button.setMinimumWidth(105)
        footer.addWidget(self.theme_button)

        root.addLayout(footer)

        self.btn_cancel.clicked.connect(self.cancel_operation)
        self.special_execute.clicked.connect(self.open_special_task)
        self.theme_button.clicked.connect(self.toggle_theme)

        self.apply_style()

    def _button(self, text, width=105):
        button = QPushButton(text)
        button.setObjectName("serviceButton")
        button.setMinimumWidth(width)
        button.setMinimumHeight(32)
        button.setMaximumHeight(36)
        return button

    def _build_main_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)

        work = QSplitter(Qt.Orientation.Horizontal)
        work.setChildrenCollapsible(False)
        work.setHandleWidth(4)

        # LEFT: compact result log, manually resizable against the work area.
        log_box = QGroupBox("LOG")
        log_layout = QVBoxLayout(log_box)
        log_layout.setContentsMargins(3, 3, 3, 3)
        log_layout.addWidget(self.console)

        # RIGHT: programming workspace from the reference photo.
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(3, 3, 3, 3)
        right_layout.setSpacing(4)

        identify_bar = QHBoxLayout()
        identify_bar.setSpacing(4)
        self.btn_main_identify = self._button("IDENTIFY", 110)
        self.btn_main_identify.clicked.connect(self.main_identify)
        identify_bar.addWidget(self.btn_main_identify)
        identify_bar.addWidget(QLabel("eMMC Programming / Dump File"))
        identify_bar.addStretch(1)
        right_layout.addLayout(identify_bar)

        # These are TASK rows, not navigation buttons. Files can be selected
        # exactly as a service programmer workflow: Boot1/2, EXT_CSD, Userarea.
        program_box = QGroupBox("eMMC PROGRAMMING")
        grid = QGridLayout(program_box)
        grid.setContentsMargins(5, 5, 5, 5)
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(4)
        headers = ["TASK", "DUMP / IMAGE FILE", "SELECT", "BACKUP", "WRITE"]
        for col, title in enumerate(headers):
            lab = QLabel(title)
            lab.setObjectName("tableHeader")
            grid.addWidget(lab, 0, col)

        self.program_rows = {}
        specs = [
            ("BOOT 1", "boot1", "*.bin *.img"),
            ("BOOT 2", "boot2", "*.bin *.img"),
            ("EXT_CSD", "extcsd", "*.bin"),
            ("USERAREA", "userarea", "*.bin *.img"),
        ]
        for row, (label, key, filt) in enumerate(specs, start=1):
            grid.addWidget(QLabel(label), row, 0)
            edit = FileDropEdit()
            edit.setReadOnly(True)
            edit.setPlaceholderText("Select dump / image")
            select = QPushButton("...")
            select.setFixedWidth(34)
            read = QPushButton("BACKUP")
            write = QPushButton("WRITE")
            self.program_rows[key] = {
                "edit": edit, "select": select, "read": read, "write": write,
                "filter": filt,
            }
            grid.addWidget(edit, row, 1)
            grid.addWidget(select, row, 2)
            grid.addWidget(read, row, 3)
            grid.addWidget(write, row, 4)
            select.clicked.connect(lambda checked=False, k=key: self.select_program_file(k))
            read.clicked.connect(lambda checked=False, k=key: self.program_read(k))
            write.clicked.connect(lambda checked=False, k=key: self.program_write(k))

        # READ in eMMC PROGRAMMING is BACKUP only. BOOT1/BOOT2 are backed up
        # through the same firmware dump stream, with partition switching.
        self.program_rows["boot1"]["write"].setEnabled(False)
        self.program_rows["boot2"]["write"].setEnabled(False)
        self.program_rows["boot1"]["write"].setToolTip("Write protocol is not implemented.")
        self.program_rows["boot2"]["write"].setToolTip("Write protocol is not implemented.")

        self.program_rows["extcsd"]["read"].setText("BACKUP")
        self.program_rows["extcsd"]["write"].setEnabled(False)
        self.program_rows["extcsd"]["write"].setToolTip("EXT_CSD write protocol is not yet implemented")

        self.program_rows["userarea"]["write"].setEnabled(False)
        self.program_rows["userarea"]["write"].setToolTip("eMMC write-stream protocol is not yet implemented")

        user_mode = QHBoxLayout()
        user_mode.addWidget(QLabel("USERAREA mode"))
        self.userarea_mode = QComboBox()
        self.userarea_mode.addItems(["AUTO", "RAW", "SPARSE"])
        user_mode.addWidget(self.userarea_mode)
        self.userarea_verify = QCheckBox("Verify after read")
        self.userarea_verify.setChecked(True)
        user_mode.addWidget(self.userarea_verify)
        user_mode.addStretch(1)
        right_layout.addWidget(program_box)
        right_layout.addLayout(user_mode)

        # SETBOOT sits immediately above the User Area partition table.
        setboot = QGroupBox("SET BOOT")
        sb = QGridLayout(setboot)
        sb.setContentsMargins(5, 5, 5, 5)
        sb.setHorizontalSpacing(4)
        sb.setVerticalSpacing(4)

        sb.addWidget(QLabel("Chipset / SoC"), 0, 0)
        self.setboot_chipset = QComboBox()
        self.setboot_chipset.addItems([
            "Generic eMMC",
            "Qualcomm",
            "MediaTek",
            "Unisoc / Spreadtrum",
            "Samsung / Exynos",
            "Huawei / HiSilicon",
        ])
        sb.addWidget(self.setboot_chipset, 0, 1)

        sb.addWidget(QLabel("Boot source"), 0, 2)
        self.setboot_source = QComboBox()
        self.setboot_source.addItems(["Disabled", "BOOT1", "BOOT2", "User Area"])
        sb.addWidget(self.setboot_source, 0, 3)

        sb.addWidget(QLabel("Boot bus"), 1, 0)
        self.setboot_bus = QComboBox()
        self.setboot_bus.addItems(["x1", "x4", "x8"])
        self.setboot_bus.setCurrentText("x8")
        sb.addWidget(self.setboot_bus, 1, 1)

        sb.addWidget(QLabel("Reset boot bus"), 1, 2)
        self.setboot_reset = QComboBox()
        self.setboot_reset.addItems(["x1", "retain"])
        self.setboot_reset.setCurrentText("retain")
        sb.addWidget(self.setboot_reset, 1, 3)

        self.btn_setboot_read = QPushButton("READ SETBOOT")
        self.btn_setboot_write = QPushButton("WRITE SETBOOT")
        self.btn_setboot_write.setEnabled(False)
        self.btn_setboot_write.setToolTip("Requires validated EXT_CSD CMD6 write support in RP2040 firmware")
        sb.addWidget(self.btn_setboot_read, 2, 0, 1, 2)
        sb.addWidget(self.btn_setboot_write, 2, 2, 1, 2)

        self.btn_setboot_read.clicked.connect(self.read_setboot)
        self.btn_setboot_write.clicked.connect(self.write_setboot)
        self.setboot_chipset.currentIndexChanged.connect(self.apply_setboot_profile)
        self.apply_setboot_profile(self.setboot_chipset.currentIndex())

        right_layout.addWidget(setboot)

        # Live User Area partition table is embedded here, not opened as a tab.
        self.userarea = UserAreaTab(self.emmc, self.console)
        self.userarea.hide_main_chrome()
        right_layout.addWidget(self.userarea, 1)

        work.addWidget(log_box)
        work.addWidget(right)
        work.setSizes([360, 820])
        work.setStretchFactor(0, 3)
        work.setStretchFactor(1, 7)

        layout.addWidget(work, 1)

        # Service objects remain available to the existing event dispatcher,
        # but MAIN controls above perform tasks directly.
        self.identify = IdentifyTab(self.emmc, self.console)
        self.boot = BootExtCSDTab(self.emmc, self.console)
        self.health = HealthTab(self.emmc, self.console)
        self.special = SpecialTaskTab(self.emmc, self.console)
        self.isp = ISPTestTab(self.emmc, self.console)
        self.main_home = page

        self.btn_userarea = self.program_rows["userarea"]["read"]
        self.btn_boot1 = self.program_rows["boot1"]["read"]
        self.btn_boot2 = self.program_rows["boot2"]["read"]
        self.btn_extcsd = self.program_rows["extcsd"]["read"]

        self.userarea.scan.clicked.connect(lambda: self.start_operation(120000, "READ GPT"))
        self.userarea.read.clicked.connect(lambda: self.start_operation(3600000, "READ / BACKUP"))
        self.userarea.stop.clicked.connect(self.cancel_operation)

        return page

    def select_program_file(self, key):
        row = self.program_rows[key]
        path, _ = QFileDialog.getOpenFileName(
            self, f"Select {key.upper()} file", "", f"Images ({row['filter']});;All Files (*)"
        )
        if path:
            row["edit"].setText(path)

    def program_read(self, key):
        # BACKUP is a standalone eMMC PROGRAMMING action. It never opens
        # another tab/service page.
        if key not in self.program_rows:
            return
        if self.program_backup["active"]:
            self.console.log("BACKUP: another backup is already running")
            return

        defaults = {"boot1": "boot1.bin", "boot2": "boot2.bin",
                    "extcsd": "ext_csd.bin", "userarea": "userarea.bin"}
        path, _ = QFileDialog.getSaveFileName(
            self, f"Save {key.upper()} backup", defaults.get(key, f"{key}.bin"),
            "Binary image (*.bin *.img);;All Files (*)"
        )
        if not path:
            return
        try:
            f = open(path, "w+b")
        except OSError as e:
            self.console.log(f"{key.upper()} BACKUP FILE ERROR: {e}")
            return

        self.program_backup.update({"active": True, "key": key, "file": f,
                                    "path": path, "expected": 0, "received": 0})
        self.program_rows[key]["edit"].setText(path)
        self.start_operation(24 * 60 * 60 * 1000, f"BACKUP {key.upper()}")
        try:
            self.emmc.layout()
        except Exception as e:
            self.console.log(f"{key.upper()} BACKUP START ERROR: {e}")
            self._finish_program_backup(False)

    def _start_program_backup_from_layout(self, obj):
        key = self.program_backup["key"]
        f = self.program_backup["file"]
        if not key or not f:
            return
        if not obj.get("ok", False):
            self.console.log(f"{key.upper()} BACKUP: layout read failed: {obj.get('msg', 'unknown error')}")
            self._finish_program_backup(False)
            return

        if key == "extcsd":
            try:
                data = bytes.fromhex(str(obj.get("ext_csd_hex", "")))
                if len(data) != 512:
                    raise ValueError("EXT_CSD must be exactly 512 bytes")
                f.write(data)
                self.program_backup["expected"] = 512
                self.program_backup["received"] = 512
                self._finish_program_backup(True)
            except (ValueError, OSError) as e:
                self.console.log(f"EXT_CSD BACKUP ERROR: {e}")
                self._finish_program_backup(False)
            return

        if key in ("boot1", "boot2"):
            sectors = int(obj.get("boot_bytes_each", 0)) // 512
            partition = 1 if key == "boot1" else 2
        else:
            sectors = int(obj.get("sec_count", 0))
            partition = 0

        if sectors <= 0:
            self.console.log(f"{key.upper()} BACKUP: invalid sector count")
            self._finish_program_backup(False)
            return

        expected = sectors * 512
        try:
            f.truncate(expected)
            self.program_backup["expected"] = expected
            self.program_backup["received"] = 0
            self.emmc.dump_start(0, sectors, 256, True, 3, partition)
        except (OSError, Exception) as e:
            self.console.log(f"{key.upper()} BACKUP START ERROR: {e}")
            self._finish_program_backup(False)

    def _handle_program_backup_binary(self, frame):
        if not self.program_backup["active"] or not self.program_backup["file"]:
            return
        if len(frame) < 8 or frame[0] != 0xB0:
            return
        ch = frame[1]
        offset = int.from_bytes(frame[2:6], "little")
        count = int.from_bytes(frame[6:8], "little")
        if ch == 0x04:
            payload = frame[8:8 + count]
        elif ch == 0x05 and len(frame) >= 9:
            payload = bytes([frame[8]]) * count
        else:
            return
        if len(payload) != count:
            return
        try:
            f = self.program_backup["file"]
            f.seek(offset)
            f.write(payload)
            self.program_backup["received"] = max(self.program_backup["received"], offset + count)
        except OSError as e:
            self.console.log(f"BACKUP FILE WRITE ERROR: {e}")
            self._finish_program_backup(False)

    def _finish_program_backup(self, success):
        pb = self.program_backup
        path = pb["path"]
        expected = pb["expected"]
        received = pb["received"]
        if pb["file"]:
            try:
                pb["file"].flush()
                pb["file"].close()
            except OSError:
                pass
        pb.update({"active": False, "key": None, "file": None, "path": None, "expected": 0, "received": 0})
        if success and expected > 0 and received >= expected:
            self.finish_operation(True, "BACKUP COMPLETE")
            self.console.log(f"BACKUP COMPLETE: {path}")
        else:
            self.finish_operation(False, "BACKUP FAILED")
            if path:
                self.console.log(f"BACKUP FAILED: {path}")

    def program_write(self, key):
        self.console.log(f"{key.upper()} WRITE: RP2040 write protocol is not implemented; no data was sent")

    def apply_setboot_profile(self, index):
        # Profiles are workflow presets, not claims about every device.
        profiles = {
            0: ("Disabled", "x8", "retain"),
            1: ("BOOT1", "x8", "retain"),
            2: ("BOOT1", "x8", "retain"),
            3: ("BOOT1", "x8", "retain"),
            4: ("BOOT1", "x8", "retain"),
            5: ("BOOT1", "x8", "retain"),
        }
        source, bus, reset = profiles.get(index, profiles[0])
        self.setboot_source.setCurrentText(source)
        self.setboot_bus.setCurrentText(bus)
        self.setboot_reset.setCurrentText(reset)

    def read_setboot(self):
        self.console.clear()
        self.start_operation(10000, "READ SETBOOT")
        try:
            self.emmc.extcsd()
        except Exception as e:
            self.finish_operation(False, "SETBOOT ERROR")
            self.console.log(f"SETBOOT READ ERROR: {e}")

    def write_setboot(self):
        self.console.log(
            "SETBOOT WRITE: not sent. RP2040 firmware has no validated EXT_CSD CMD6 write protocol."
        )

    def _build_flash_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(2, 2, 2, 2)
        self.factory_image = FactoryImageTab(self.console)
        layout.addWidget(self.factory_image)
        return page

    def _build_adb_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(2, 2, 2, 2)
        self.adb_fastboot = ADBFastbootTab(self.console)
        layout.addWidget(self.adb_fastboot)
        return page

    def show_service(self, widget):
        """Show a service page without changing the outer photo-like shell."""
        if widget is self.userarea:
            self.userarea.show_service_controls()
            return
        if widget is self.boot:
            title = "BOOT / EXT_CSD"
        elif widget is self.identify:
            title = "IDENTIFY"
        elif widget is self.health:
            title = "HEALTH"
        elif widget is self.special:
            title = "SPECIAL TASK"
        elif widget is self.isp:
            title = "ISP TEST"
        else:
            title = "USER AREA"

        dialog = getattr(self, "_service_dialog", None)
        if dialog is None:
            from PyQt6.QtWidgets import QDialog
            dialog = QDialog(self)
            dialog.setModal(False)
            dialog.resize(920, 650)
            dialog.setWindowTitle("RP2040 eMMC PROGRAMMER")
            box = QVBoxLayout(dialog)
            bar = QHBoxLayout()
            dialog.back_button = QPushButton("← MAIN")
            dialog.title_label = QLabel()
            dialog.title_label.setObjectName("dialogTitle")
            bar.addWidget(dialog.back_button)
            bar.addWidget(dialog.title_label)
            bar.addStretch(1)
            box.addLayout(bar)
            dialog.stack = QStackedWidget()
            box.addWidget(dialog.stack, 1)
            dialog.back_button.clicked.connect(dialog.hide)
            self._service_dialog = dialog

        stack = dialog.stack
        while stack.count():
            old = stack.widget(0)
            stack.removeWidget(old)
        stack.addWidget(widget)
        dialog.title_label.setText(title)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def on_category_clicked(self, index):
        if index == 0:
            # MAIN is the photo-like home screen.
            self.userarea.hide_main_chrome()
        elif index == 1:
            pass
        elif index == 2:
            pass

    def _install_command_log_reset(self):
        for button in self.findChildren(QPushButton):
            if button in (
                self.btn_cancel,
                self.theme_button,
                self.special_execute,
            ):
                continue
            button.pressed.connect(self._clear_log_for_new_command)

    def _clear_log_for_new_command(self):
        sender = self.sender()
        if not isinstance(sender, QPushButton):
            return
        text = sender.text().strip().upper()
        if text in {"REFRESH", "CONNECT", "DISCONNECT", "← MAIN", "OPEN", "STOP"}:
            return
        self.console.clear()

    def apply_style(self):
        if self.light_theme:
            self.setStyleSheet("""
            QMainWindow, QWidget { background:#f1f3f5; color:#202428; font-family:Segoe UI; font-size:9pt; }
            QLabel { color:#202428; }
            QGroupBox { border:1px solid #aeb5bb; border-radius:3px; margin-top:7px; padding-top:5px; font-weight:bold; }
            QGroupBox::title { subcontrol-origin:margin; left:7px; padding:0 4px; }
            QPushButton { background:#e5e8eb; border:1px solid #a5adb4; border-radius:2px; padding:4px 8px; min-height:26px; }
            QPushButton:hover { background:#d9dde1; }
            QPushButton:pressed { background:#cbd0d5; }
            QPushButton:disabled { color:#8a9095; background:#e8eaec; }
            QComboBox { background:#ffffff; border:1px solid #a5adb4; border-radius:2px; padding:4px 7px; min-height:25px; }
            QTabWidget::pane { border:1px solid #aeb5bb; background:#f7f8f9; }
            QTabBar::tab { background:#dfe3e6; border:1px solid #aeb5bb; padding:6px 14px; color:#394047; }
            QTabBar::tab:selected { background:#ffffff; color:#111417; }
            QSplitter::handle { background:#aeb5bb; }
            QProgressBar { border:1px solid #aeb5bb; background:#ffffff; text-align:center; min-height:18px; }
            QProgressBar::chunk { background:#707980; }
            QTableWidget { background:#ffffff; alternate-background-color:#f2f4f5; gridline-color:#c5cbd0; selection-background-color:#d7dde2; }
            QHeaderView::section { background:#e1e5e8; color:#252a2e; padding:5px; border:1px solid #c5cbd0; font-weight:bold; }
            QLabel#status_disconnected { color:#b23b3b; font-weight:bold; }
            QLabel#status_connected { color:#277746; font-weight:bold; }
            QLabel#dialogTitle { font-weight:bold; font-size:11pt; }
            """)
        else:
            self.setStyleSheet("""
            QMainWindow, QWidget { background:#111417; color:#d7dde2; font-family:Segoe UI; font-size:9pt; }
            QLabel { color:#d7dde2; }
            QGroupBox { border:1px solid #30373d; border-radius:3px; margin-top:7px; padding-top:5px; font-weight:bold; color:#aeb8c0; }
            QGroupBox::title { subcontrol-origin:margin; left:7px; padding:0 4px; color:#9da8b0; }
            QPushButton { background:#20262b; border:1px solid #3b444b; border-radius:2px; padding:4px 8px; color:#dce2e6; min-height:26px; }
            QPushButton:hover { background:#2b3339; border-color:#68757e; }
            QPushButton:pressed { background:#171c20; }
            QPushButton:disabled { color:#596168; background:#171b1e; border-color:#292e32; }
            QComboBox { background:#181d21; border:1px solid #3a434a; border-radius:2px; padding:4px 7px; min-height:25px; }
            QTabWidget::pane { border:1px solid #30373d; background:#151a1e; }
            QTabBar::tab { background:#1b2024; border:1px solid #30373d; padding:6px 14px; color:#8f9aa3; }
            QTabBar::tab:selected { background:#30383f; color:#ffffff; }
            QSplitter::handle { background:#30383e; }
            QSplitter::handle:hover { background:#59656e; }
            QProgressBar { border:1px solid #30373d; border-radius:2px; background:#181d21; text-align:center; min-height:18px; }
            QProgressBar::chunk { background:#46535d; }
            QTableWidget { background:#151a1e; alternate-background-color:#1b2024; gridline-color:#30373d; selection-background-color:#303c45; }
            QHeaderView::section { background:#20272c; color:#cdd5da; padding:5px; border:1px solid #30373d; font-weight:bold; }
            QLabel#status_disconnected { color:#d66a6a; font-weight:bold; }
            QLabel#status_connected { color:#72c48b; font-weight:bold; }
            QLabel#dialogTitle { color:#ffffff; font-weight:bold; font-size:11pt; }
            """)

    def toggle_theme(self):
        self.light_theme = not self.light_theme
        self.apply_style()
        self.theme_button.setText("Light / Dark" if self.light_theme else "Dark / Light")
        self.console.log("Theme: light" if self.light_theme else "Theme: dark")

    def update_clock(self):
        self.clock_label.setText(
            QDateTime.currentDateTime().toString("dd/MM/yyyy  HH:mm:ss")
        )

    def open_special_task(self):
        index = self.special_combo.currentIndex()
        self.show_service(self.special)
        try:
            self.special.select_task(index)
        except Exception:
            pass

    def refresh_device(self, auto_connect=True):
        self.port_combo.clear()
        try:
            import serial.tools.list_ports
            ports = list(serial.tools.list_ports.comports())
            pico_port = self.serial.find_pico_port(ports)
            for port in ports:
                description = port.description or "Unknown Device"
                is_pico = pico_port is not None and port.device == pico_port.device
                prefix = "PICO USB - " if is_pico else ""
                self.port_combo.addItem(
                    f"{prefix}{port.device} - {description}",
                    port.device,
                )
            if pico_port:
                self.last_pico_device = pico_port.device
                self.port_combo.setCurrentIndex(
                    self.port_combo.findData(pico_port.device)
                )
                if auto_connect and not self.serial.is_connected():
                    self.connect_rp2040()
            if self.port_combo.count() == 0:
                self.port_combo.addItem("No COM port detected", None)
                self.last_pico_device = None
        except Exception as e:
            self.console.log(f"PORT SCAN ERROR: {e}")

    def toggle_connection(self):
        if self.serial.is_connected():
            self.disconnect_rp2040()
        else:
            self.connect_rp2040()

    def connect_rp2040(self):
        if self.serial.is_connected():
            return
        port = self.port_combo.currentData()
        if not port:
            try:
                port = self.serial.auto_detect()
            except Exception as e:
                self.console.log(f"AUTO DETECT ERROR: {e}")
                port = None
        if not port:
            self.set_disconnected("RP2040 not found")
            return
        try:
            connected = self.serial.connect(port)
        except Exception as e:
            self.console.log(f"CONNECT ERROR: {e}")
            connected = False
        if connected:
            self.set_connected(port)
        else:
            self.set_disconnected(f"Cannot open {port}")

    def disconnect_rp2040(self):
        try:
            self.serial.disconnect(silent=True)
        except Exception as e:
            self.console.log(f"DISCONNECT ERROR: {e}")
        self.set_disconnected()

    def set_connected(self, port):
        self.rp_status.setText(f"RP2040 : {port}")
        self.connection_status.setText("CONNECTED")
        self.connection_status.setObjectName("status_connected")
        self.connection_status.setStyleSheet("")
        self.btn_connect.setText("Disconnect")
        self.footer_status_safe(f"Connected to {port}")

    def footer_status_safe(self, text):
        self.operation_label.setText(text if text else "Ready")

    def set_disconnected(self, message=None):
        self.rp_status.setText("RP2040")
        self.connection_status.setText("DISCONNECTED")
        self.connection_status.setObjectName("status_disconnected")
        self.connection_status.setStyleSheet("")
        self.btn_connect.setText("Connect")
        if message:
            self.console.log(message)
        self.operation_timer.stop()
        self.btn_cancel.setEnabled(False)
        self.progress.setValue(0)
        try:
            self.isp.finish()
        except Exception:
            pass

    def check_connection(self):
        try:
            if self.serial.is_connected() and not self.serial.port_exists():
                self.serial.disconnect()
                return
            if not self.serial.is_connected():
                self.detect_new_pico()
        except Exception:
            pass

    def detect_new_pico(self):
        pico_port = self.serial.find_pico_port()
        pico_device = pico_port.device if pico_port else None
        if not pico_device:
            self.last_pico_device = None
            return
        if pico_device != self.last_pico_device:
            self.last_pico_device = pico_device
            self.refresh_device(auto_connect=True)

    def on_serial_disconnect(self):
        self.set_disconnected("RP2040 disconnected")

    def start_operation(self, timeout_ms=5000, label="Operation"):
        self.btn_cancel.setEnabled(True)
        self.progress.setValue(0)
        self.operation_label.setText(label)
        self.operation_timer.start(timeout_ms)

    def finish_operation(self, ok=True, label="Ready"):
        self.operation_timer.stop()
        self.btn_cancel.setEnabled(False)
        self.progress.setValue(100 if ok else 0)
        self.operation_label.setText(label)

    def operation_timeout(self):
        self.btn_cancel.setEnabled(False)
        self.progress.setValue(0)
        self.operation_label.setText("TIMEOUT")
        self.console.log("OPERATION TIMEOUT - no response from RP2040")

    def cancel_operation(self):
        try:
            self.emmc.stop_tests()
        except Exception:
            pass
        self.operation_timer.stop()
        self.btn_cancel.setEnabled(False)
        self.progress.setValue(0)
        self.operation_label.setText("Cancelled")
        try:
            self.isp.finish()
        except Exception:
            pass

    def command_init(self):
        self.start_operation(10000, "INIT")
        try:
            self.emmc.init()
        except Exception as e:
            self.finish_operation(False, "INIT ERROR")
            self.console.log(f"INIT ERROR: {e}")

    def command_detect(self):
        self.show_service(self.identify)

    def command_identify(self):
        self.main_identify()

    def command_read_cid(self):
        self.show_service(self.identify)

    def main_identify(self):
        if not self.serial.is_connected():
            self.console.log("IDENTIFY: RP2040 is not connected")
            return
        # IDENTIFY is a standalone task. It must not implicitly launch GPT
        # or open another tab; the result is routed to IdentifyTab by main.py.
        self.identify_sequence = False
        try:
            self.start_operation(24 * 60 * 60 * 1000, "IDENTIFY")
            self.emmc.identify()
        except Exception as e:
            self.finish_operation(False, "IDENTIFY ERROR")
            self.console.log(f"IDENTIFY ERROR: {e}")

    def main_gpt(self):
        if not self.serial.is_connected():
            self.console.log("READ GPT: RP2040 is not connected")
            return
        try:
            self.userarea.show_service_controls()
            self.start_operation(120000, "READ GPT")
            self.userarea.scanGPT()
        except Exception as e:
            self.finish_operation(False, "GPT ERROR")
            self.console.log(f"READ GPT ERROR: {e}")

    def main_health(self):
        self.show_service(self.special)
        index = self.special.task_names().index("eMMC Health Check")
        self.special.select_task(index)
        self.special.execute_task()

    def handle_serial_data(self, obj):
        if not isinstance(obj, dict):
            return
        typ = obj.get("type")
        if typ == "emmc.identify.progress":
            percent = int(obj.get("percent", 0))
            self.progress.setValue(max(0, min(100, percent)))
            self.operation_label.setText(f"IDENTIFY {obj.get('area', '')} {percent}%")
        elif typ == "emmc.identify.result":
            if obj.get("ok"):
                self.finish_operation(True, "IDENTIFY OK")
                if self.identify_sequence:
                    self.identify_sequence = False
                    self.main_gpt()
            else:
                self.finish_operation(False, "IDENTIFY FAILED")
        elif typ == "emmc.gpt.end":
            if obj.get("ok", True):
                self.finish_operation(True, "GPT OK")
            else:
                self.finish_operation(False, "GPT FAILED")
        elif typ == "emmc.layout.result":
            if self.program_backup["active"]:
                self._start_program_backup_from_layout(obj)
                return
            if obj.get("ok"):
                cfg = int(obj.get("partition_config", 0) or 0)
                boot_en = (cfg >> 3) & 0x7
                access = cfg & 0x7
                source = {0: "Disabled", 1: "BOOT1", 2: "BOOT2", 7: "User Area"}.get(boot_en, "Disabled")
                self.setboot_source.setCurrentText(source)
                self.console.log(f"SETBOOT READ : SoC={self.setboot_chipset.currentText()}  PARTITION_CONFIG=0x{cfg:02X}  Boot={source}  Access={access}")
                self.finish_operation(True, "SETBOOT READ OK")
            else:
                self.finish_operation(False, "SETBOOT READ FAILED")
        elif typ == "emmc.dump.status":
            if self.program_backup["active"]:
                state = str(obj.get("state", ""))
                if state == "complete":
                    self._finish_program_backup(self.program_backup["received"] >= self.program_backup["expected"])
                elif state in ("error", "stopped"):
                    self._finish_program_backup(False)
                return
            state = str(obj.get("state", ""))
            done = int(obj.get("done_blocks", 0))
            total = int(obj.get("total_blocks", 0))
            if total > 0:
                self.progress.setValue(max(0, min(100, int(done * 100 / total))))
            if state == "complete":
                self.finish_operation(True, "READ COMPLETE")
            elif state == "error":
                self.finish_operation(False, "READ FAILED")

    def handle_binary_data(self, frame):
        self._handle_program_backup_binary(frame)

    def closeEvent(self, event):
        try:
            self.operation_timer.stop()
            self.watchdog.stop()
            self.clock_timer.stop()
        except Exception:
            pass
        try:
            if self.serial.is_connected():
                self.serial.disconnect()
        except Exception:
            pass
        event.accept()
