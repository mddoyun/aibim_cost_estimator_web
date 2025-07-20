# dd_by_ifc/urls.py

from django.urls import path
from . import views

app_name = 'dd_by_ifc'

urlpatterns = [
    # 프로젝트 관리
    path('', views.project_list, name='project_list'),
    path('upload/', views.upload_project, name='upload_project'),
    path('project/<int:project_id>/', views.project_detail, name='project_detail'),
    
    # 기존 URL 호환성
    path('old/', views.go_dd_by_ifc, name='go_dd_by_ifc'),  # 기존 업로드 페이지
    path('result/<int:project_id>/', views.go_dd_by_ifc_result, name='go_dd_by_ifc_result'),  # 기존 결과 페이지
    
    # API 엔드포인트들
    path('api/ifc_objects/<int:project_id>/', views.get_ifc_objects, name='get_ifc_objects'),
    path('api/search_cost_codes/', views.search_cost_codes, name='search_cost_codes'),
    # path('api/add_cost_code/', views.add_cost_code_to_objects, name='add_cost_code_to_objects'),
    # path('api/remove_cost_code/', views.remove_cost_code_from_objects, name='remove_cost_code_from_objects'),
    path('api/object_details/', views.get_object_details, name='get_object_details'),
    path('api/summary_table/<int:project_id>/', views.get_summary_table, name='get_summary_table'),
    path('api/load_cost_codes/', views.load_cost_codes_from_csv, name='load_cost_codes_from_csv'),
    path('api/download_ifc/<int:project_id>/', views.download_ifc_file, name='download_ifc_file'),
    path('api/ifc_geometry/<int:project_id>/', views.ifc_to_json, name='ifc_geometry'),

    # dd_by_ifc/urls.py에 다음 2줄 추가
    path('api/debug_ifc/<int:project_id>/', views.debug_ifc_properties, name='debug_ifc_properties'),
    path('api/test_update/', views.force_update_single_object, name='force_update_single_object'),

    # 새로운 URL 추가
    path('api/add_cost_code/', views.add_cost_code_to_objects_simple, name='add_cost_code_to_objects'),
    path('api/remove_cost_code/', views.remove_cost_code_from_objects_simple, name='remove_cost_code_from_objects'),
    path('api/download_new_ifc/<int:project_id>/', views.download_new_ifc_file, name='download_new_ifc_file'),

]