from django.db import models

# Create your models here.
class InputData(models.Model):
    project_name = models.CharField("프로젝트명", max_length=50)
    total_room_count = models.IntegerField("실개수",default=0)
    total_area = models.FloatField("연면적_m2", default=0.0)
    ground_level = models.IntegerField("지상층수", default=0)
    basement_level = models.IntegerField("지하층수", default=0)
    site_area = models.FloatField("대지면적_m2", default=0.0)
    budget = models.FloatField("예산_원", default=0.0)

    def __str__(self):
        return self.project_name

class OutputData(models.Model):
    input_data = models.ForeignKey(InputData, on_delete=models.CASCADE)
    total_cost = models.FloatField("총공사비_원", default=0.0)
    a_cost = models.FloatField("건축공사비_원", default=0.0)
    etc_cost = models.FloatField("기타공사비_원", default=0.0)




    def __str__(self):
        return f"{self.input_data.project_name}의 예측값"