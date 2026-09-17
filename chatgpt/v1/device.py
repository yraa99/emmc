from PyQt6.QtWidgets import *


class DeviceTab(QWidget):

    def __init__(self, emmc, console):

        super().__init__()

        self.emmc=emmc
        self.console=console

        self.initUI()



    def initUI(self):

        layout=QVBoxLayout()


        self.table=QTableWidget(
            8,
            2
        )

        self.table.setHorizontalHeaderLabels(
            [
                "Parameter",
                "Value"
            ]
        )


        items=[
            "Manufacturer",
            "CID",
            "CSD",
            "EXT_CSD",
            "Capacity",
            "Bus Width",
            "Clock",
            "Status"
        ]


        for i,x in enumerate(items):

            self.table.setItem(
                i,
                0,
                QTableWidgetItem(x)
            )


        btn=QPushButton(
            "IDENTIFY"
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
            "> IDENTIFY"
        )

        self.emmc.identify()