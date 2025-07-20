#ai_prediction/models.py

from django.db import models
import json

class AIModel(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    model_file = models.FileField(upload_to='ai_models/')
    metadata = models.JSONField(default=dict)  # 메타데이터 저장
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # 모델 성능 메트릭
    rmse = models.FloatField(null=True, blank=True)
    mae = models.FloatField(null=True, blank=True)
    r2_score = models.FloatField(null=True, blank=True)
    
    def __str__(self):
        return self.name
    
    @property
    def input_columns(self):
        """입력 칼럼 리스트 반환"""
        return self.metadata.get('inputColumns', [])
    
    @property
    def output_columns(self):
        """출력 칼럼 리스트 반환"""
        return self.metadata.get('outputColumns', [])

class PredictionHistory(models.Model):
    ai_model = models.ForeignKey(AIModel, on_delete=models.CASCADE)
    input_data = models.JSONField()  # 입력 데이터
    prediction_result = models.JSONField()  # 예측 결과
    prediction_range = models.JSONField()  # 예측 범위 (min, max)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Prediction for {self.ai_model.name} at {self.created_at}"