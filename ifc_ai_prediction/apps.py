# ifc_ai_prediction/apps.py
from django.apps import AppConfig

class IFCAIPredictionConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ifc_ai_prediction'
    verbose_name = 'IFC AI 예측'
    
    def ready(self):
        """앱이 준비되었을 때 실행되는 메소드"""
        # 시그널이나 기타 초기화 작업이 필요한 경우 여기에 추가
        pass