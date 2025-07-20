from django.db import models


class UploadedIFC(models.Model):
    file = models.FileField(upload_to='ifc_files/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
