from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QFileDialog,
    QTableWidget,
    QTableWidgetItem,
    QGroupBox,
    QHeaderView,
    QSizePolicy,
    QLineEdit,
    QComboBox,
    QMenu,
    QAbstractItemView,
    QMessageBox
)

from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtCore import Qt, QSize

import os
import tempfile
import shutil


from core.adb import ADB
from core.fastboot import Fastboot
from core.apk_parser import APKParser



class ADBFastbootTab(QWidget):


    def __init__(self, console):

        super().__init__()

        self.console = console

        self.adb = ADB()
        self.fastboot = Fastboot()
        self.parser = APKParser()

        self.app_data = []

        self.setup()


    def log(self, text):

        if self.console:

            self.console.log(
                str(text)
            )



    def setup(self):

        main = QVBoxLayout(self)


        title = QLabel(
            "ADB / FASTBOOT MANAGER"
        )

        title.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        main.addWidget(title)



        # =========================
        # DEVICE
        # =========================


        device_box = QGroupBox(
            "DEVICE"
        )

        device_layout = QHBoxLayout()


        self.btn_scan_adb = QPushButton(
            "SCAN ADB"
        )

        self.btn_scan_fastboot = QPushButton(
            "SCAN FASTBOOT"
        )

        self.btn_reboot = QPushButton(
            "REBOOT"
        )

        self.btn_bootloader = QPushButton(
            "BOOTLOADER"
        )

        for button in (self.btn_scan_adb, self.btn_scan_fastboot, self.btn_reboot, self.btn_bootloader):
            button.setMinimumWidth(120)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


        device_layout.addWidget(
            self.btn_scan_adb
        )

        device_layout.addWidget(
            self.btn_scan_fastboot
        )

        device_layout.addWidget(
            self.btn_reboot
        )

        device_layout.addWidget(
            self.btn_bootloader
        )


        device_box.setLayout(
            device_layout
        )

        main.addWidget(
            device_box
        )



        # =========================
        # SEARCH FILTER
        # =========================


        filter_layout = QHBoxLayout()


        self.search_box = QLineEdit()

        self.search_box.setPlaceholderText(
            "Search application..."
        )


        self.filter_box = QComboBox()

        self.filter_box.addItems(
            [
                "ALL",
                "USER APP",
                "SYSTEM APP",
                "DISABLED APP"
            ]
        )


        filter_layout.addWidget(
            self.search_box
        )

        filter_layout.addWidget(
            self.filter_box
        )


        main.addLayout(
            filter_layout
        )



        # =========================
        # APP TABLE
        # =========================


        self.app_table = QTableWidget()


        self.app_table.setColumnCount(
            6
        )


        self.app_table.setHorizontalHeaderLabels(
            [
                "ICON",
                "NAME",
                "PACKAGE",
                "VERSION",
                "TYPE",
                "STATUS"
            ]
        )


        self.app_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )


        self.app_table.setIconSize(
            QSize(48,48)
        )


        self.app_table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )


        self.app_table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.app_table.customContextMenuRequested.connect(self.context_menu)

        main.addWidget(
            self.app_table
        )

        # =========================
        # APP CONTROL
        # =========================


        app_box = QGroupBox(
            "APPLICATION"
        )


        app_layout = QHBoxLayout()


        self.btn_install = QPushButton(
            "INSTALL APK"
        )

        self.btn_uninstall = QPushButton(
            "UNINSTALL"
        )

        self.btn_backup = QPushButton(
            "BACKUP APK"
        )

        self.btn_disable = QPushButton(
            "DISABLE"
        )

        self.btn_enable = QPushButton(
            "ENABLE"
        )

        for button in (self.btn_install, self.btn_uninstall, self.btn_backup, self.btn_disable, self.btn_enable):
            button.setMinimumWidth(115)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


        app_layout.addWidget(
            self.btn_install
        )

        app_layout.addWidget(
            self.btn_uninstall
        )

        app_layout.addWidget(
            self.btn_backup
        )

        app_layout.addWidget(
            self.btn_disable
        )

        app_layout.addWidget(
            self.btn_enable
        )


        app_box.setLayout(
            app_layout
        )


        main.addWidget(
            app_box
        )



        # =========================
        # FASTBOOT
        # =========================


        fast_box = QGroupBox(
            "FASTBOOT INFO"
        )


        fast_layout = QVBoxLayout()


        self.btn_getvar = QPushButton(
            "GETVAR ALL"
        )

        self.btn_getvar.setMinimumWidth(150)
        self.btn_getvar.setMaximumWidth(220)
        self.btn_getvar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)


        fast_actions = QHBoxLayout()
        fast_actions.addWidget(self.btn_getvar)
        fast_actions.addStretch()
        fast_layout.addLayout(fast_actions)


        fast_box.setLayout(
            fast_layout
        )


        main.addWidget(
            fast_box
        )



        # =========================
        # SIGNAL
        # =========================


        self.btn_scan_adb.clicked.connect(
            self.scan_adb
        )


        self.btn_scan_fastboot.clicked.connect(
            self.scan_fastboot
        )


        self.btn_install.clicked.connect(
            self.install_apk
        )


        self.btn_uninstall.clicked.connect(
            self.uninstall
        )


        self.btn_backup.clicked.connect(
            self.backup_apk
        )


        self.btn_disable.clicked.connect(
            self.disable
        )


        self.btn_enable.clicked.connect(
            self.enable
        )


        self.btn_reboot.clicked.connect(
            self.reboot
        )


        self.btn_bootloader.clicked.connect(
            self.bootloader
        )


        self.btn_getvar.clicked.connect(
            self.getvar
        )


        self.search_box.textChanged.connect(
            self.filter_table
        )


        self.filter_box.currentTextChanged.connect(
            self.filter_table
        )



    # =========================
    # SCAN ADB
    # =========================


    def scan_adb(self):

        self.log(
            "Scanning ADB device..."
        )


        devices = self.adb.devices()


        self.log(
            devices
        )


        if "device" not in devices:

            self.log(
                "No ADB device detected"
            )

            return



        packages = self.adb.list_packages_detail()
        print(packages[:10])

        self.log(
            f"Found {len(packages)} applications"
        )


        self.app_data.clear()


        self.app_table.setRowCount(
            0
        )


        for app in packages:

            self.app_data.append(
                {
                    "package": app["package"],
                    "name": app["package"],
                    "version": "",
                    "type": app["type"],
                    "status": app["status"]
                }
            )


        self.load_table()



    def load_table(self):

        self.app_table.setRowCount(
            0
        )


        for app in self.app_data:


            row = self.app_table.rowCount()


            self.app_table.insertRow(
                row
            )


            self.app_table.setItem(
                row,
                1,
                QTableWidgetItem(
                    app["name"]
                )
            )


            self.app_table.setItem(
                row,
                2,
                QTableWidgetItem(
                    app["package"]
                )
            )


            self.app_table.setItem(
                row,
                3,
                QTableWidgetItem(
                    app["version"]
                )
            )


            self.app_table.setItem(
                row,
                4,
                QTableWidgetItem(
                    app["type"]
                )
            )


            self.app_table.setItem(
                row,
                5,
                QTableWidgetItem(
                    app["status"]
                )
            )

    # =========================
    # FILTER TABLE
    # =========================


    def filter_table(self):

        text = self.search_box.text().lower()

        mode = self.filter_box.currentText()


        for row in range(self.app_table.rowCount()):

            pkg = self.app_table.item(row,2).text().lower()
            app_type = self.app_table.item(row,4).text()
            status = self.app_table.item(row,5).text()


            visible = True


            if text:

                if text not in pkg:
                    visible = False


            if mode == "USER APP":

                if app_type != "USER":
                    visible = False


            elif mode == "SYSTEM APP":

                if app_type != "SYSTEM":
                    visible = False


            elif mode == "DISABLED APP":

                if status != "DISABLED":
                    visible = False


            self.app_table.setRowHidden(
                row,
                not visible
            )



    # =========================
    # SELECT PACKAGE
    # =========================


    def selected_packages(self):

        packages = []


        rows = self.app_table.selectionModel().selectedRows()


        for index in rows:


            item = self.app_table.item(
                index.row(),
                2
            )


            if item:

                packages.append(
                    item.text()
                )


        return packages



    # =========================
    # RIGHT CLICK MENU
    # =========================


    def context_menu(self, pos):

        menu = QMenu(
            self
        )


        backup = menu.addAction(
            "Backup APK"
        )


        uninstall = menu.addAction(
            "Uninstall"
        )


        disable = menu.addAction(
            "Disable"
        )


        enable = menu.addAction(
            "Enable"
        )


        refresh = menu.addAction(
            "Refresh"
        )


        action = menu.exec(
            self.app_table.mapToGlobal(pos)
        )


        if action == backup:

            self.backup_apk()


        elif action == uninstall:

            self.uninstall()


        elif action == disable:

            self.disable()


        elif action == enable:

            self.enable()


        elif action == refresh:

            self.scan_adb()



    # =========================
    # INSTALL APK
    # =========================


    def install_apk(self):

        file, _ = QFileDialog.getOpenFileName(
            self,
            "Select APK",
            "",
            "APK (*.apk)"
        )


        if file:


            result = self.adb.install(
                file
            )

    # =========================
    # BACKUP APK
    # =========================


    def backup_apk(self):

        packages = self.selected_packages()


        if not packages:

            self.log(
                "No application selected"
            )

            return



        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Backup Folder"
        )


        if not folder:

            return



        for pkg in packages:


            self.log(
                f"Backup {pkg}..."
            )


            path = self.adb.shell(
                f"pm path {pkg}"
            )


            if not path.startswith(
                "package:"
            ):

                self.log(
                    f"APK path not found: {pkg}"
                )

                continue



            apk_path = path.replace(
                "package:",
                ""
            ).strip()



            temp = os.path.join(
                tempfile.gettempdir(),
                os.path.basename(apk_path)
            )


            pull = self.adb.run(
                [
                    "pull",
                    apk_path,
                    temp
                ]
            )


            save = os.path.join(
                folder,
                pkg + ".apk"
            )


            try:

                shutil.copy(
                    temp,
                    save
                )


                self.log(
                    f"Saved: {save}"
                )


            except Exception as e:

                self.log(
                    str(e)
                )

    # =========================
    # UNINSTALL
    # =========================

    def uninstall(self):

            packages = self.selected_packages()

            if not packages:
                self.log(
                    "No application selected"
                )
                return


            for pkg in packages:

                result = self.adb.uninstall(
                    pkg
                )

                self.log(
                    f"{pkg}: {result}"
                )

    # =========================
    # FASTBOOT
    # =========================


    def scan_fastboot(self):

        self.log(
            "Scanning Fastboot..."
        )


        result = self.fastboot.devices()


        if result:

            self.log(
                result
            )

        else:

            self.log(
                "No fastboot device"
            )

    def disable(self):

        packages = self.selected_packages()


        if not packages:

            self.log(
                "No application selected"
            )

            return



        for pkg in packages:

            result = self.adb.disable(
                pkg
            )


            self.log(
                f"{pkg}: {result}"
            )



    def enable(self):

        packages = self.selected_packages()


        if not packages:

            self.log(
                "No application selected"
            )

            return



        for pkg in packages:

            result = self.adb.enable(
                pkg
            )


            self.log(
                f"{pkg}: {result}"
            )

    def reboot(self):

        result = self.adb.reboot()


        self.log(
            result
        )



    def bootloader(self):

        result = self.adb.reboot(
            "bootloader"
        )


        self.log(
            result
        )



    def getvar(self):

        result = self.fastboot.getvar()


        self.log(
            result
        )

    # =========================
    # END CLASS
    # =========================


    def closeEvent(self, event):

        try:

            self.app_data.clear()

        except:

            pass


        event.accept()
