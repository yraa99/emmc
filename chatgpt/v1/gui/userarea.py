from PyQt6.QtWidgets import *


class UserAreaTab(QWidget):

    def __init__(self, emmc, console):

        super().__init__()

        self.emmc = emmc
        self.console = console

        self.partitions = []

        self.setup()



    def setup(self):

        layout = QVBoxLayout()


        title = QLabel(
            "USER AREA PARTITION MANAGER"
        )


        self.table = QTableWidget()

        self.table.setColumnCount(5)

        self.table.setHorizontalHeaderLabels(
            [
                "Partition",
                "Start LBA",
                "Sectors",
                "Size",
                "Status"
            ]
        )


        self.scan = QPushButton(
            "SCAN GPT"
        )


        self.read = QPushButton(
            "READ"
        )


        self.write = QPushButton(
            "WRITE"
        )


        self.verify = QPushButton(
            "VERIFY"
        )


        self.scan.clicked.connect(
            self.scanGPT
        )


        self.read.clicked.connect(
            self.readPartition
        )


        self.write.clicked.connect(
            self.writePartition
        )


        self.verify.clicked.connect(
            self.verifyPartition
        )



        btn = QHBoxLayout()

        btn.addWidget(
            self.scan
        )

        btn.addWidget(
            self.read
        )

        btn.addWidget(
            self.write
        )

        btn.addWidget(
            self.verify
        )


        layout.addWidget(
            title
        )

        layout.addWidget(
            self.table
        )

        layout.addLayout(
            btn
        )


        self.setLayout(
            layout
        )



    def scanGPT(self):

        self.console.log(
            "REQUEST GPT SCAN"
        )


        # sementara menunggu
        # data asli dari firmware

        self.loadExample()



    def loadExample(self):

        data = [

            [
                "modem",
                "2048",
                "131072",
                "64 MB",
                "READY"
            ],

            [
                "nvdata",
                "133120",
                "65536",
                "32 MB",
                "READY"
            ],

            [
                "persist",
                "198656",
                "32768",
                "16 MB",
                "READY"
            ],

            [
                "metadata",
                "231424",
                "131072",
                "64 MB",
                "READY"
            ],

            [
                "system",
                "500000",
                "8000000",
                "4 GB",
                "SKIP"
            ],

            [
                "userdata",
                "9000000",
                "120000000",
                "64 GB",
                "SKIP"
            ]

        ]


        self.table.setRowCount(
            len(data)
        )


        for r,row in enumerate(data):

            for c,value in enumerate(row):

                self.table.setItem(
                    r,
                    c,
                    QTableWidgetItem(
                        value
                    )
                )


        self.console.log(
            "GPT LIST READY"
        )



    def selectedPartition(self):

        row = self.table.currentRow()

        if row < 0:
            return None


        name = self.table.item(
            row,0
        ).text()


        start = int(
            self.table.item(
                row,1
            ).text()
        )


        count = int(
            self.table.item(
                row,2
            ).text()
        )


        return name,start,count



    def readPartition(self):

        p = self.selectedPartition()

        if not p:
            return


        name,start,count = p


        self.console.log(
            f"READ {name}"
        )


        self.emmc.backup(
            start,
            count
        )



    def writePartition(self):

        p = self.selectedPartition()

        if not p:
            return


        name,start,count = p


        self.console.log(
            f"WRITE {name}"
        )


        self.emmc.restore(
            start,
            count
        )



    def verifyPartition(self):

        p = self.selectedPartition()

        if not p:
            return


        name,start,count = p


        self.console.log(
            f"VERIFY {name}"
        )