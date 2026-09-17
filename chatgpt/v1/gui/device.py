from PyQt6.QtWidgets import *


class DeviceTab(QWidget):

    def __init__(self,emmc,console):

        super().__init__()

        self.emmc=emmc
        self.console=console

        self.setup()


    def setup(self):

        layout=QVBoxLayout()


        self.table=QTableWidget(
            10,
            2
        )


        self.table.setHorizontalHeaderLabels(
            [
                "PARAMETER",
                "VALUE"
            ]
        )


        data=[
            "Manufacturer",
            "Model",
            "CID",
            "CSD",
            "EXT_CSD",
            "Capacity",
            "Sector Size",
            "Bus Width",
            "Clock",
            "Status"
        ]


        for i,x in enumerate(data):

            self.table.setItem(
                i,
                0,
                QTableWidgetItem(x)
            )


        btn=QPushButton(
            "IDENTIFY eMMC"
        )


        btn.clicked.connect(
            self.identify
        )


        layout.addWidget(
            self.table
        )

        layout.addWidget(
            btn
        )


        self.setLayout(layout)



    def identify(self):

        self.console.log(
            "SEND IDENTIFY"
        )

        self.emmc.identify()