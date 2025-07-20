from django.contrib import admin
from ai_learning.models import LearningProject
# Register your models here.

@admin.register(LearningProject)
class LearningProjectAdmin(admin.ModelAdmin):
    pass