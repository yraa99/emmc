from PyQt6.QtWidgets import *
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

import tempfile
import os

from core.adb import ADB
from core.fastboot import Fastboot
from core.apk_parser import APKParser
from core.app_manager import AppManager



class ADBFastbootTab(QWidget):


    def __init__(self, console):

    super().__init__()


    self.console = console


    self.adb = ADB()

    self.fastboot = Fastboot()

    self.app_manager = AppManager(
        self.adb
    )

    self.apk_parser = APKParser()


    self.apps = []

    self.apk_file = None


    self.setAcceptDrops(
        True
    )


    self.setup()


    def setup(self):

        layout = QVBoxLayout()


        title = QLabel(
            "ADB / FASTBOOT MANAGER"
        )

        title.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )


        self.list = QListWidget()

        self.list.setIconSize(
            Qt.QSize(48,48)
        )


        scan = QPushButton(
            "SCAN DEVICE"
        )

        install = QPushButton(
            "INSTALL APK"
        )

        uninstall = QPushButton(
            "UNINSTALL"
        )

        enable = QPushButton(
            "ENABLE"
        )

        disable = QPushButton(
            "DISABLE"
        )

        reboot = QPushButton(
            "REBOOT SYSTEM"
        )

        recovery = QPushButton(
            "RECOVERY"
        )

        boot = QPushButton(
            "BOOTLOADER"
        )


        scan.clicked.connect(
            self.scan
        )

        install.clicked.connect(
            self.install_apk
        )

        uninstall.clicked.connect(
            self.uninstall
        )

        enable.clicked.connect(
            self.enable
        )

        disable.clicked.connect(
            self.disable
        )


        reboot.clicked.connect(
            lambda:self.reboot("")
        )

        recovery.clicked.connect(
            lambda:self.reboot("recovery")
        )

        boot.clicked.connect(
            lambda:self.reboot("bootloader")
        )



        for w in [
            title,
            self.list,
            scan,
            install,
            uninstall,
            enable,
            disable,
            reboot,
            recovery,
            boot
        ]:

            layout.addWidget(w)



        self.setLayout(
            layout
        )



    # ======================
    # ADB SCAN
    # ======================

    def scan_apps(self):

    self.log(
        "Scanning installed applications..."
    )


    self.apps = self.app_manager.get_app_list()


    self.app_table.setRowCount(
        len(self.apps)
    )


    for row, app in enumerate(self.apps):


        self.app_table.setRowHeight(
            row,
            60
        )


        icon_item = QTableWidgetItem()


        name_item = QTableWidgetItem(
            app.get(
                "name",
                app["package"]
            )
        )


        package_item = QTableWidgetItem(
            app["package"]
        )


        status_item = QTableWidgetItem(
            app["status"]
        )



        # =========================
        # PASANG ICON APK
        # =========================

        icon = app.get(
            "icon"
        )


        if icon:


            temp = tempfile.NamedTemporaryFile(
                suffix=".png",
                delete=False
            )


            icon.save(
                temp.name
            )


            icon_item.setIcon(
                QIcon(
                    temp.name
                )
            )



        self.app_table.setItem(
            row,
            0,
            icon_item
        )


        self.app_table.setItem(
            row,
            1,
            name_item
        )


        self.app_table.setItem(
            row,
            2,
            package_item
        )


        self.app_table.setItem(
            row,
            3,
            status_item
        )


    self.log(
        f"{len(self.apps)} application loaded"
    )



    # ======================
    # APK INSTALL
    # ======================

    def install_apk(self):

        file,_ = QFileDialog.getOpenFileName(
            self,
            "Select APK",
            "",
            "APK (*.apk)"
        )


        if file:

            self.show_apk(file)



    def show_apk(self,path):

        data = self.apk.parse(
            path
        )


        self.apk_file = path


        if "error" in data:

            self.console.log(
                data["error"]
            )

            return


        msg = QMessageBox()

        msg.setWindowTitle(
            "APK INFORMATION"
        )


        msg.setText(
            f"""
Name:
{data['name']}

Package:
{data['package']}

Version:
{data['version']}


Install this APK?
"""
        )


        if data["icon"]:

            temp = tempfile.NamedTemporaryFile(
                suffix=".png",
                delete=False
            )

            data["icon"].save(
                temp.name
            )


            msg.setIcon(
                QMessageBox.Icon.Information
            )


        result = msg.exec()


        if result:

            self.console.log(
                self.adb.install(
                    path
                )
            )



    # ======================
    # SELECT APP
    # ======================

    def selected(self):

        item=self.list.currentItem()

        if item:

            return item.text()

        return None



    def uninstall(self):

        p=self.selected()

        if p:

            self.console.log(
                self.adb.uninstall(p)
            )



    def enable(self):

        p=self.selected()

        if p:

            self.console.log(
                self.adb.enable(p)
            )



    def disable(self):

        p=self.selected()

        if p:

            self.console.log(
                self.adb.disable(p)
            )



    def reboot(self,mode):

        self.console.log(
            self.adb.reboot(mode)
        )



    # ======================
    # DRAG DROP APK
    # ======================


    def dragEnterEvent(self,event):

        if event.mimeData().hasUrls():

            event.acceptProposedAction()



    def dropEvent(self,event):

        files = event.mimeData().urls()


        for f in files:

            path=f.toLocalFile()


            if path.endswith(
                ".apk"
            ):

                self.show_apk(path)