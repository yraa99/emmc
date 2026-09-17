import subprocess


class Fastboot:


    def run(self, cmd):

        try:

            result=subprocess.run(
                ["fastboot"]+cmd,
                capture_output=True,
                text=True
            )

            return result.stdout.strip()

        except Exception as e:

            return str(e)



    def devices(self):

        return self.run(
            [
                "devices"
            ]
        )



    def reboot(self):

        return self.run(
            [
                "reboot"
            ]
        )



    def getvar(self):

        return self.run(
            [
                "getvar",
                "all"
            ]
        )



    def flash(self,partition,image):

        return self.run(
            [
                "flash",
                partition,
                image
            ]
        )