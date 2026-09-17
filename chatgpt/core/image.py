import os


class ImageManager:


    def create(self,path,size):

        with open(path,"wb") as f:

            f.write(
                b"\x00"*size
            )


    def save_block(self,path,data):

        with open(path,"ab") as f:

            f.write(data)



    def read_block(self,path,offset,size):

        with open(path,"rb") as f:

            f.seek(offset)

            return f.read(size)



    def size(self,path):

        return os.path.getsize(path)