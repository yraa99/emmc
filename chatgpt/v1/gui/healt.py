from PyQt6.QtWidgets import *


class HealthTab(QWidget):

    def __init__(self, emmc, console):

        super().__init__()

        self.emmc = emmc
        self.console = console

        self.setup()



    def setup(self):

        layout = QVBoxLayout()


        title = QLabel(
            "eMMC HEALTH REPORT"
        )


        self.table = QTableWidget(
            5,
            2
        )


        self.table.setHorizontalHeaderLabels(
            [
                "PARAMETER",
                "VALUE"
            ]
        )


        fields = [

            "DEVICE_LIFE_TIME_A",

            "DEVICE_LIFE_TIME_B",

            "PRE_EOL_INFO",

            "RPMB STATUS",

            "HEALTH STATUS"

        ]


        for i,f in enumerate(fields):

            self.table.setItem(
                i,
                0,
                QTableWidgetItem(f)
            )



        button = QPushButton(
            "READ HEALTH"
        )


        button.clicked.connect(
            self.readHealth
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



    def readHealth(self):

        self.console.log(
            "READ eMMC HEALTH"
        )


        # nanti mapping:
        # HEALTH command ke firmware Pico