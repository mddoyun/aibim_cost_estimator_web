#ai_prediction/urls.py

from django.urls import path
from . import views

app_name = 'ai_prediction'

urlpatterns = [
    # 모델 업로드 페이지
    path('', views.model_upload, name='model_upload'),
    
    # 모델 목록 페이지
    path('models/', views.model_list, name='model_list'),
    
    # 예측 페이지
    path('predict/<int:model_id>/', views.prediction_page, name='prediction_page'),
    
    # API 엔드포인트
    path('api/predict/<int:model_id>/', views.predict_api, name='predict_api'),
    path('api/save_prediction/<int:model_id>/', views.save_prediction, name='save_prediction'),
    path('api/model_metadata/<int:model_id>/', views.get_model_metadata, name='get_model_metadata'),
    path('api/delete_model/<int:model_id>/', views.delete_model, name='delete_model'),
    
    # PDF 생성
    path('api/generate_pdf/<int:model_id>/', views.generate_prediction_pdf, name='generate_prediction_pdf'),
]