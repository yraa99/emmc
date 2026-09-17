import subprocess


class ADB:

    def run(self, cmd):

        try:
            result = subprocess.run(
                ["adb"] + cmd,
                capture_output=True,
                text=True
            )

            return result.stdout.strip()

        except Exception as e:
            return str(e)



    def devices(self):

        return self.run(
            ["devices"]
        )



    def shell(self, command):

        return self.run(
            [
                "shell",
                command
            ]
        )



    def install(self, apk):

        return self.run(
            [
                "install",
                apk
            ]
        )



    def uninstall(self, package):

        return self.run(
            [
                "uninstall",
                package
            ]
        )



    def disable(self, package):

        return self.shell(
            f"pm disable-user --user 0 {package}"
        )



    def enable(self, package):

        return self.shell(
            f"pm enable {package}"
        )



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



    def packages(self):

        data = self.shell(
            "pm list packages"
        )

        return data.splitlines()