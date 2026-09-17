from PyQt6.QtWidgets import *


class BootExtCSDTab(QWidget):

    def __init__(self, emmc, console):

        super().__init__()

        self.emmc = emmc
        self.console = console

        self.setup()



    def setup(self):

        layout = QVBoxLayout()


        # ===================
        # BOOT AREA
        # ===================

        bootBox = QGroupBox(
            "BOOT PARTITION"
        )

        bootLayout = QHBoxLayout()


        self.readBoot1 = QPushButton(
            "READ BOOT1"
        )

        self.readBoot2 = QPushButton(
            "READ BOOT2"
        )


        self.writeBoot1 = QPushButton(
            "WRITE BOOT1"
        )

        self.writeBoot2 = QPushButton(
            "WRITE BOOT2"
        )


        bootLayout.addWidget(
            self.readBoot1
        )

        bootLayout.addWidget(
            self.readBoot2
        )

        bootLayout.addWidget(
            self.writeBoot1
        )

        bootLayout.addWidget(
            self.writeBoot2
        )


        bootBox.setLayout(
            bootLayout
        )


        # ===================
        # EXT CSD
        # ===================


        extBox = QGroupBox(
            "EXT_CSD INFORMATION"
        )


        extLayout = QVBoxLayout()


        self.extTable = QTableWidget(
            8,
            2
        )


        self.extTable.setHorizontalHeaderLabels(
            [
                "FIELD",
                "VALUE"
            ]
        )


        fields = [

            "PARTITION_CONFIG",

            "BOOT_SIZE_MULT",

            "RPMB_SIZE_MULT",

            "BOOT_BUS_WIDTH",

            "RST_N_FUNCTION",

            "DEVICE_LIFE_TIME_A",

            "DEVICE_LIFE_TIME_B",

            "PRE_EOL_INFO"

        ]


        for i,f in enumerate(fields):

            self.extTable.setItem(
                i,
                0,
                QTableWidgetItem(f)
            )


        readExt = QPushButton(
            "READ EXT_CSD"
        )


        saveExt = QPushButton(
            "SAVE EXT_CSD"
        )


        writeExt = QPushButton(
            "WRITE EXT_CSD"
        )


        readExt.clicked.connect(
            self.readExtCSD
        )


        self.readBoot1.clicked.connect(
            lambda:self.bootRead(1)
        )


        self.readBoot2.clicked.connect(
            lambda:self.bootRead(2)
        )


        self.writeBoot1.clicked.connect(
            lambda:self.bootWrite(1)
        )


        self.writeBoot2.clicked.connect(
            lambda:self.bootWrite(2)
        )


        extLayout.addWidget(
            self.extTable
        )


        extLayout.addWidget(
            readExt
        )


        extLayout.addWidget(
            saveExt
        )


        extLayout.addWidget(
            writeExt
        )


        extBox.setLayout(
            extLayout
        )



        layout.addWidget(
            bootBox
        )


        layout.addWidget(
            extBox
        )


        self.setLayout(
            layout
        )



    def bootRead(self,part):

        self.console.log(
            f"READ BOOT{part}"
        )


        # nanti diganti protocol:
        # BOOT_READ 1/2



    def bootWrite(self,part):

        self.console.log(
            f"WRITE BOOT{part}"
        )



    def readExtCSD(self):

        self.console.log(
            "READ EXT_CSD"
        )


        self.emmc.extcsd()