#ai_learning/models.py
from django.db import models

class LearningProject(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    dataset = models.FileField(upload_to='dataset/', blank=True, null=True)

    def __str__(self):
        return self.name
    
