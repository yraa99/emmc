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


        actions = QGridLayout()
        actions.setHorizontalSpacing(8)
        actions.setVerticalSpacing(8)
        buttons = (self.ffu, self.setBoot, self.partition, self.rpmb, self.security)
        for index, button in enumerate(buttons):
            button.setMinimumHeight(30)
            button.setMinimumWidth(170)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.setEnabled(False)
            button.setToolTip("Belum tersedia pada firmware USB CDC eMMC saat ini.")
            actions.addWidget(button, index // 2, index % 2)
        layout.addLayout(actions)


        layout.addStretch()


        self.setLayout(
            layout
        )



    def command(self,cmd):
        self.console.log(f"SPECIAL TASK : {cmd} belum tersedia pada firmware aktif")
