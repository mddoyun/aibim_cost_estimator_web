from django.contrib import admin
from sd_by_input.models import InputData, OutputData
# Register your models here.

@admin.register(InputData)
class InputDataAdmin(admin.ModelAdmin):
  pass

@admin.register(OutputData)
class OutputDataAdmin(admin.ModelAdmin):
  pass

