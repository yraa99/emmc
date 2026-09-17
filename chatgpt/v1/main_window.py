from PyQt6.QtWidgets import *

from gui.device import DeviceTab
from gui.readwrite import ReadWriteTab
from gui.partition import PartitionTab
from gui.console import Console


class MainWindow(QMainWindow):


    def __init__(self,emmc,serial):

        super().__init__()


        self.setWindowTitle(
            "eMMC Programmer Pro"
        )

        self.resize(
            1000,
            700
        )


        self.console=Console()


        tabs=QTabWidget()


        tabs.addTab(
            DeviceTab(
                emmc,
                self.console
            ),
            "Device"
        )


        tabs.addTab(
            ReadWriteTab(
                emmc,
                self.console
            ),
            "Read / Write"
        )


        tabs.addTab(
            PartitionTab(),
            "Partition"
        )


        tabs.addTab(
            self.console,
            "Console"
        )


        self.setCentralWidget(
            tabs
        )