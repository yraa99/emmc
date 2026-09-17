from PyQt6.QtWidgets import *


class ReadWriteTab(QWidget):

    def __init__(self,emmc,console):

        super().__init__()

        self.emmc=emmc
        self.console=console

        self.initUI()



    def initUI(self):

        l=QVBoxLayout()


        self.file=QLineEdit()

        browse=QPushButton(
            "Browse"
        )


        read=QPushButton(
            "READ BACKUP"
        )


        write=QPushButton(
            "WRITE IMAGE"
        )


        verify=QPushButton(
            "VERIFY"
        )


        read.clicked.connect(
            self.read
        )

        write.clicked.connect(
            self.write
        )


        l.addWidget(
            self.file
        )

        l.addWidget(
            browse
        )

        l.addWidget(
            read
        )

        l.addWidget(
            write
        )

        l.addWidget(
            verify
        )


        self.progress=QProgressBar()

        l.addWidget(
            self.progress
        )


        self.setLayout(l)




    def read(self):

        self.console.log(
            "> READ START"
        )

        self.emmc.backup(
            0,
            1024
        )



    def write(self):

        self.console.log(
            "> WRITE START"
        )

        self.emmc.restore(
            0,
            1024
        )