from django.contrib import admin
from django.urls import path, include
from config.views import index # view의 index 함수를 가져옵니다.
from blog.views import post_list # blog 앱의 post_list 뷰를 가져옵니다.
from est_dd.views import upload_ifc # est_dd 앱의 upload_ifc 뷰를 가져옵니다.
from django.conf import settings
from django.conf.urls.static import static
from sd_by_input.views import go_sd_by_input, go_sd_by_input_result # sd_by_input 앱의 go_sd_by_input 뷰를 가져옵니다.
from ai_learning.views import go_ai_learning # ai_learning 앱의 go_ai_learning 뷰를 가져옵니다.
from dd_by_ifc.views import (
    go_dd_by_ifc, 
    go_dd_by_ifc_result,
    get_ifc_objects,
    search_cost_codes,
    add_cost_code_to_objects,
    remove_cost_code_from_objects,
    get_object_details,
    get_summary_table,
    load_cost_codes_from_csv,
    download_ifc_file,
    ifc_to_json
) # dd_by_ifc 앱의 뷰들을 가져옵니다.

urlpatterns = [
    path('admin/', admin.site.urls),
    path("",index),
    path("posts/", post_list),
    path("upload/",upload_ifc, name='upload_ifc'),
    path("sd_by_input/", go_sd_by_input),  # sd_by_input 앱의 URL을 포함합니다.
    path("sd_by_input_result/<int:inputValuesId>", go_sd_by_input_result ),  # sd_by_input_result 뷰를 추가합니다.
    path("ai_learning/", go_ai_learning),  # ai_learning 앱의 URL을 포함합니다.
    path("dd_by_ifc/", go_dd_by_ifc),  # dd_by_ifc 앱의 URL을 포함합니다.
    path("dd_by_ifc_result/<int:project_id>/", go_dd_by_ifc_result, name='go_dd_by_ifc_result'),
    
    # API 엔드포인트들
    path("api/ifc_objects/<int:project_id>/", get_ifc_objects, name='get_ifc_objects'),
    path("api/search_cost_codes/", search_cost_codes, name='search_cost_codes'),
    path("api/add_cost_code/", add_cost_code_to_objects, name='add_cost_code_to_objects'),
    path("api/remove_cost_code/", remove_cost_code_from_objects, name='remove_cost_code_from_objects'),
    path("api/object_details/", get_object_details, name='get_object_details'),
    path("api/summary_table/<int:project_id>/", get_summary_table, name='get_summary_table'),
    path("api/load_cost_codes/", load_cost_codes_from_csv, name='load_cost_codes_from_csv'),
    path("api/download_ifc/<int:project_id>/", download_ifc_file, name='download_ifc_file'),
    # urls.py에 추가
    path('api/ifc_geometry/<int:project_id>/', ifc_to_json, name='ifc_geometry'),
    path('ai_prediction/', include('ai_prediction.urls')),

    # 새로운 앱 URL 추가
    path('ifc_ai_prediction/', include('ifc_ai_prediction.urls')),

]

# urls.py 맨 아래에 추가
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)