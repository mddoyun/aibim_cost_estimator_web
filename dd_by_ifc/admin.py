#dd_by_ifc/admin.py

from django.contrib import admin
from dd_by_ifc.models import ProjectDD
# Register your models here.

@admin.register(ProjectDD)
class ProjectDDAdmin(admin.ModelAdmin):
  pass