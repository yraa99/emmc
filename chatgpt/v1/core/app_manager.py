import os
import tempfile

from core.apk_parser import APKParser



class AppManager:


    def __init__(self, adb):

        self.adb = adb

        self.parser = APKParser()



    # ==========================
    # PACKAGE LIST
    # ==========================

    def get_packages(self):

        result = []

        data = self.adb.shell(
            "pm list packages"
        )


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



    # ==========================
    # APK LOCATION
    # ==========================

    def get_apk_path(self, package):


        data = self.adb.shell(
            f"pm path {package}"
        )


        for line in data.splitlines():

            if "package:" in line:

                return line.replace(
                    "package:",
                    ""
                )


        return None



    # ==========================
    # STATUS
    # ==========================

    def get_status(self, package):


        data = self.adb.shell(
            f"pm list packages -d {package}"
        )


        if package in data:

            return "DISABLED"


        return "ENABLED"



    # ==========================
    # TYPE APP
    # ==========================

    def get_type(self, package):


        path = self.get_apk_path(
            package
        )


        if path and "/data/app/" in path:

            return "USER"


        return "SYSTEM"



    # ==========================
    # PULL APK TEMP
    # ==========================

    def pull_apk(self, package):


        remote = self.get_apk_path(
            package
        )


        if not remote:

            return None



        filename = package.replace(
            ".",
            "_"
        )


        local = os.path.join(

            tempfile.gettempdir(),

            filename + ".apk"

        )


        self.adb.run(
            [
                "pull",
                remote,
                local
            ]
        )



        if os.path.exists(local):

            return local


        return None



    # ==========================
    # FULL APPLICATION SCAN
    # ==========================

    def get_app_list(self):


        apps = []


        packages = self.get_packages()



        for package in packages:



            app = {


                "name":
                package,


                "package":
                package,


                "version":
                "",


                "status":
                self.get_status(
                    package
                ),


                "type":
                self.get_type(
                    package
                ),


                "icon":
                None,


                "apk":
                None

            }



            apk = self.pull_apk(
                package
            )



            if apk:


                app["apk"] = apk



                info = self.parser.parse(
                    apk
                )



                if "error" not in info:


                    app.update(
                        info
                    )



            apps.append(
                app
            )



        return apps