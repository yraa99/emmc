from PyQt6.QtWidgets import *


class ReadWriteTab(QWidget):


    def __init__(self,emmc,console):

        super().__init__()

        self.emmc=emmc
        self.console=console

        self.setup()



    def setup(self):

        layout=QVBoxLayout()


        self.file=QLineEdit()

        self.file.setPlaceholderText(
            "Image file (.bin)"
        )


        browse=QPushButton(
            "BROWSE"
        )


        self.start=QLineEdit("0")

        self.count=QLineEdit(
            "1024"
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


        self.progress=QProgressBar()



        read.clicked.connect(
            self.read
        )

        write.clicked.connect(
            self.write
        )


        layout.addWidget(
            self.file
        )

        layout.addWidget(
            browse
        )

        layout.addWidget(
            QLabel("Start sector")
        )

        layout.addWidget(
            self.start
        )

        layout.addWidget(
            QLabel("Sector count")
        )

        layout.addWidget(
            self.count
        )

        layout.addWidget(read)

        layout.addWidget(write)

        layout.addWidget(verify)

        layout.addWidget(
            self.progress
        )


        self.setLayout(layout)



    def read(self):

        self.console.log(
            "READ REQUEST"
        )

        self.emmc.backup(
            int(self.start.text()),
            int(self.count.text())
        )



    def write(self):

        self.console.log(
            "WRITE REQUEST"
        )

        self.emmc.restore(
            int(self.start.text()),
            int(self.count.text())
        )