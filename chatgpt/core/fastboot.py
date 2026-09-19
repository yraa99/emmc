import subprocess
import os



class Fastboot:


    def __init__(self):

        base = os.path.dirname(
            os.path.dirname(
                os.path.abspath(__file__)
            )
        )


        self.fastboot = os.path.join(
            base,
            "tools",
            "fastboot.exe"
        )



    def run(self,args):

        try:

            result = subprocess.run(
                [self.fastboot] + args,
                capture_output=True,
                text=True
            )

            output = result.stdout.strip()
            error = result.stderr.strip()
            return output if output else error


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



    def bootloader(self):

        return self.run(
            [
                "reboot-bootloader"
            ]
        )



    def getvar(self):

        return self.run(
            [
                "getvar",
                "all"
            ]
        )