import os

from androguard.core.apk import APK
from PIL import Image
from io import BytesIO



class APKParser:


    def __init__(self):

        pass



    def parse(self, apk_path):

        try:

            apk = APK(
                apk_path
            )


            info = {

                "package":
                apk.get_package(),

                "version":
                apk.get_androidversion_name(),

                "name":
                apk.get_app_name(),

                "icon":
                self.get_icon(apk)

            }


            return info



        except Exception as e:

            return {

                "error":
                str(e)

            }



    def get_icon(self, apk):


        try:

            icon_path = apk.get_icon()


            data = apk.get_file(
                icon_path
            )


            image = Image.open(
                BytesIO(data)
            )


            return image.convert(
                "RGBA"
            )


        except:


            return None