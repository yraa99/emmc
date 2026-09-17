import subprocess
import os


class ADB:


    def __init__(self):

        base = os.path.dirname(
            os.path.dirname(
                os.path.abspath(__file__)
            )
        )


        self.adb = os.path.join(
            base,
            "tools",
            "adb.exe"
        )



    def run(self, args):

        try:

            result = subprocess.run(
                [self.adb] + args,
                capture_output=True,
                text=True
            )


            if result.stdout:

                return result.stdout.strip()


            return result.stderr.strip()



        except Exception as e:

            return str(e)



    # =========================
    # DEVICE
    # =========================


    def devices(self):

        return self.run(
            [
                "devices"
            ]
        )



    # =========================
    # SHELL
    # =========================


    def shell(self, command):

        return self.run(
            [
                "shell",
                command
            ]
        )



    # =========================
    # APPLICATION
    # =========================


    def list_packages(self):

        result = self.shell(
            "pm list packages"
        )


        packages = []


        for line in result.splitlines():

            if line.startswith(
                "package:"
            ):

                packages.append(
                    line.replace(
                        "package:",
                        ""
                    )
                )


        return packages



    def list_packages_detail(self):


        system = self.shell(
            "pm list packages -s"
        )


        user = self.shell(
            "pm list packages -3"
        )


        disabled = self.shell(
            "pm list packages -d"
        )



        system = self.clean_packages(
            system
        )


        user = self.clean_packages(
            user
        )


        disabled = self.clean_packages(
            disabled
        )



        result = []



        for pkg in system:


            result.append(

                {
                    "package": pkg,
                    "type": "SYSTEM",
                    "status":
                    "DISABLED"
                    if pkg in disabled
                    else
                    "ENABLED"
                }

            )



        for pkg in user:


            result.append(

                {
                    "package": pkg,
                    "type": "USER",
                    "status":
                    "DISABLED"
                    if pkg in disabled
                    else
                    "ENABLED"
                }

            )


        return result



    def clean_packages(self,data):

        result=[]


        for line in data.splitlines():

            if line.startswith(
                "package:"
            ):

                result.append(
                    line.replace(
                        "package:",
                        ""
                    )
                )


        return result



    # =========================
    # INSTALL
    # =========================


    def install(self, apk):

        return self.run(
            [
                "install",
                apk
            ]
        )



    # =========================
    # REMOVE
    # =========================


    def uninstall(self, package):

        return self.run(
            [
                "uninstall",
                package
            ]
        )



    # =========================
    # ENABLE DISABLE
    # =========================


    def disable(self, package):

        return self.shell(
            f"pm disable-user --user 0 {package}"
        )



    def enable(self, package):

        return self.shell(
            f"pm enable {package}"
        )



    # =========================
    # BACKUP APK
    # =========================


    def backup_apk(self, package, path):
        apk = self.shell(
            f"pm path {package}"
        )


        if not apk.startswith(
            "package:"
        ):

            return apk



        apk = apk.replace(
            "package:",
            ""
        )


        return self.run(

            [
                "pull",
                apk,
                path
            ]

        )



    # =========================
    # REBOOT
    # =========================


    def reboot(self, mode=""):


        if mode:

            return self.run(
                [
                    "reboot",
                    mode
                ]
            )


        return self.run(
            [
                "reboot"
            ]
        )