from PyQt6.QtWidgets import *


class IdentifyTab(QWidget):

    def __init__(self, emmc, console):

        super().__init__()

        self.emmc = emmc
        self.console = console

        self.setup()



    def setup(self):

        layout = QVBoxLayout()


        title = QLabel(
            "eMMC IDENTIFY"
        )


        self.table = QTableWidget(
            10,
            2
        )


        self.table.setHorizontalHeaderLabels(
            [
                "PARAMETER",
                "VALUE"
            ]
        )


        fields = [

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


        for i,f in enumerate(fields):

            self.table.setItem(
                i,
                0,
                QTableWidgetItem(f)
            )


        button = QPushButton(
            "IDENTIFY DEVICE"
        )


        button.clicked.connect(
            self.identify
        )


        layout.addWidget(
            title
        )


        layout.addWidget(
            self.table
        )


        layout.addWidget(
            button
        )


        self.setLayout(
            layout
        )



    def identify(self):

        self.console.log(
            "IDENTIFY REQUEST"
        )


        self.emmc.identify()