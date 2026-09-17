from PyQt6.QtWidgets import *


class SpecialTaskTab(QWidget):

    def __init__(self, emmc, console):

        super().__init__()

        self.emmc = emmc
        self.console = console

        self.setup()



    def setup(self):

        layout = QVBoxLayout()


        title = QLabel(
            "SPECIAL TASK"
        )


        self.ffu = QPushButton(
            "FFU MODE"
        )


        self.setBoot = QPushButton(
            "SET BOOT PARTITION"
        )


        self.partition = QPushButton(
            "PARTITION CONFIG"
        )


        self.rpmb = QPushButton(
            "RPMB INFO"
        )


        self.security = QPushButton(
            "SECURITY TASK"
        )



        self.ffu.clicked.connect(
            lambda:
            self.command(
                "FFU"
            )
        )


        self.setBoot.clicked.connect(
            lambda:
            self.command(
                "SET_BOOT"
            )
        )


        self.partition.clicked.connect(
            lambda:
            self.command(
                "PARTITION_CONFIG"
            )
        )


        self.rpmb.clicked.connect(
            lambda:
            self.command(
                "RPMB_INFO"
            )
        )


        self.security.clicked.connect(
            lambda:
            self.command(
                "SECURITY"
            )
        )



        layout.addWidget(
            title
        )


        layout.addWidget(
            self.ffu
        )

        layout.addWidget(
            self.setBoot
        )

        layout.addWidget(
            self.partition
        )

        layout.addWidget(
            self.rpmb
        )

        layout.addWidget(
            self.security
        )


        layout.addStretch()


        self.setLayout(
            layout
        )



    def command(self,cmd):

        self.console.log(
            f"SPECIAL TASK : {cmd}"
        )


        # nanti masuk protocol.py