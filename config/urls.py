# config/urls.py

from django.contrib import admin
from django.urls import path, include
from config.views import index
from django.conf import settings
from django.conf.urls.static import static
from ai_learning.views import go_ai_learning

# dd_by_ifc views import 추가
from dd_by_ifc.views import (
    go_dd_by_ifc, go_dd_by_ifc_result, get_ifc_objects, search_cost_codes,
    add_cost_code_to_objects, remove_cost_code_from_objects, get_object_details,
    get_summary_table, load_cost_codes_from_csv, download_ifc_file, ifc_to_json
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path("", index, name='index'),  # 홈 페이지
    path("ai_learning/", go_ai_learning),  # ai_learning 앱의 URL
    
    # 앱별 URL 패턴 포함
    path('ai_prediction/', include('ai_prediction.urls')),
    path('ifc_ai_prediction/', include('ifc_ai_prediction.urls')),
    path('dd_by_ifc/', include('dd_by_ifc.urls')),  # 새로운 dd_by_ifc URL 패턴
    
    # 기존 dd_by_ifc 호환성을 위한 개별 URL들 (하위 호환성)
    path("dd_by_ifc_old/", go_dd_by_ifc),
    path("dd_by_ifc_result/<int:project_id>/", go_dd_by_ifc_result, name='go_dd_by_ifc_result'),
    
    # 기존 API 엔드포인트들 (하위 호환성)
    path("api/ifc_objects/<int:project_id>/", get_ifc_objects, name='get_ifc_objects'),
    path("api/search_cost_codes/", search_cost_codes, name='search_cost_codes'),
    path("api/add_cost_code/", add_cost_code_to_objects, name='add_cost_code_to_objects'),
    path("api/remove_cost_code/", remove_cost_code_from_objects, name='remove_cost_code_from_objects'),
    path("api/object_details/", get_object_details, name='get_object_details'),
    path("api/summary_table/<int:project_id>/", get_summary_table, name='get_summary_table'),
    path("api/load_cost_codes/", load_cost_codes_from_csv, name='load_cost_codes_from_csv'),
    path("api/download_ifc/<int:project_id>/", download_ifc_file, name='download_ifc_file'),
    path('api/ifc_geometry/<int:project_id>/', ifc_to_json, name='ifc_geometry'),
]

# Static 및 Media 파일 설정
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)