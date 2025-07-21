# ifc_ai_prediction/urls.py

from django.urls import path
from . import views

app_name = 'ifc_ai_prediction'

# ifc_ai_prediction/urls.py
urlpatterns = [
    # 기본 페이지들
    path('', views.project_list, name='project_list'),
    path('upload/', views.upload_ifc, name='upload_ifc'),
    path('project/<int:project_id>/predict/', views.prediction_page, name='prediction_page'),
    path('project/<int:project_id>/history/', views.prediction_history, name='prediction_history'),
    
    # IFC 관련 API
    path('api/project/<int:project_id>/objects/', views.get_ifc_objects, name='get_ifc_objects'),
    path('api/project/<int:project_id>/test-aggregation/', views.test_aggregation, name='test_aggregation'),
    path('api/project/<int:project_id>/execute-prediction/', views.execute_prediction, name='execute_prediction'),
    
    # AI 모델 관련 API  
    path('api/model/<int:model_id>/metadata/', views.get_model_metadata, name='get_model_metadata'),
    path('api/upload_ai_model/', views.upload_ai_model, name='upload_ai_model'),
    
    # 필터링 및 예측 API
    path('api/filters/save/', views.save_filter_conditions, name='save_filter_conditions'),
    path('api/mapping/<int:mapping_id>/save-result/', views.save_prediction_result, name='save_prediction_result'),
    path('api/mapping/<int:mapping_id>/generate-pdf/<int:prediction_id>/', views.generate_prediction_pdf, name='generate_prediction_pdf'),
    path('project/<int:project_id>/delete/', views.delete_project, name='delete_project'),
    path("delete_ai_model/<int:model_id>/", views.delete_ai_model, name="delete_ai_model"),

]