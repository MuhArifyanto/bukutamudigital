import os
from cloudinary_storage.storage import MediaCloudinaryStorage


class DynamicMediaCloudinaryStorage(MediaCloudinaryStorage):
    """
    Storage Cloudinary cerdas yang secara dinamis menentukan tipe resource:
    - File gambar (jpg, png, webp, svg, dsb.) diunggah sebagai resource_type='image'.
    - File video (mp4, webm, dsb.) diunggah sebagai resource_type='video'.
    - Dokumen non-gambar (pdf, doc, docx, xls, xlsx) diunggah sebagai resource_type='raw'.

    Ini mengatasi keterbatasan bawaan MediaCloudinaryStorage yang hanya mendukung
    gambar secara default dan menolak dokumen office/PDF saat diunggah ke Cloudinary.
    """

    IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp', 'gif', 'bmp', 'ico', 'svg'}
    VIDEO_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv', 'webm'}

    def _get_resource_type(self, name):
        ext = os.path.splitext(name)[1].lower().lstrip('.')
        if ext in self.IMAGE_EXTENSIONS:
            return 'image'
        elif ext in self.VIDEO_EXTENSIONS:
            return 'video'
        return 'raw'
