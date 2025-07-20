# ifc_ai_prediction/models.py

from django.db import models
import json

class SimpleJSONField(models.TextField):
    """간단한 JSON 필드 구현"""
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('default', dict)
        super().__init__(*args, **kwargs)
    
    def from_db_value(self, value, expression, connection):
        if value is None:
            return {}
        try:
            return json.loads(value)
        except:
            return {}
    
    def to_python(self, value):
        if isinstance(value, dict):
            return value
        if value is None:
            return {}
        try:
            return json.loads(value)
        except:
            return {}
    
    def get_prep_value(self, value):
        if value is None:
            return json.dumps({})
        return json.dumps(value)

# =============================================================================
# AI 모델 관련 (ai_prediction 앱에서 가져옴)
# =============================================================================

class AIModel(models.Model):
    """AI 모델 정보"""
    name = models.CharField("모델명", max_length=255)
    description = models.TextField("설명", blank=True, null=True)
    model_file = models.FileField("모델 파일", upload_to='ai_models/')
    metadata = SimpleJSONField("메타데이터")
    created_at = models.DateTimeField("생성일", auto_now_add=True)
    updated_at = models.DateTimeField("수정일", auto_now=True)
    
    # 모델 성능 메트릭
    rmse = models.FloatField("RMSE", null=True, blank=True)
    mae = models.FloatField("MAE", null=True, blank=True)
    r2_score = models.FloatField("R² 점수", null=True, blank=True)
    
    class Meta:
        verbose_name = "AI 모델"
        verbose_name_plural = "AI 모델들"
    
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

# =============================================================================
# IFC 프로젝트 관련 
# =============================================================================

class IFCProject(models.Model):
    """IFC 프로젝트 모델"""
    name = models.CharField("프로젝트명", max_length=200)
    description = models.TextField("설명", blank=True)
    ifc_file = models.FileField("IFC 파일", upload_to='ifc_ai_files/')
    converted_obj = models.FileField("변환된 OBJ", upload_to='ifc_ai_objs/', null=True, blank=True)
    
    # 처리 상태
    is_processed = models.BooleanField("처리 완료", default=False)
    processing_error = models.TextField("처리 오류", blank=True, null=True)
    
    created_at = models.DateTimeField("생성일", auto_now_add=True)
    updated_at = models.DateTimeField("수정일", auto_now=True)
    
    class Meta:
        verbose_name = "IFC 프로젝트"
        verbose_name_plural = "IFC 프로젝트들"
    
    def __str__(self):
        return self.name
    
    def get_ifc_objects_summary(self):
        """IFC 객체 요약 정보 반환"""
        try:
            ifc_objects = IFCObjectData.objects.filter(project=self)
            total_count = ifc_objects.count()
            
            # 클래스별 개수
            class_counts = {}
            for obj in ifc_objects:
                ifc_class = obj.ifc_class
                class_counts[ifc_class] = class_counts.get(ifc_class, 0) + 1
            
            return {
                'total_count': total_count,
                'class_counts': class_counts,
                'is_processed': self.is_processed
            }
        except Exception as e:
            return {
                'total_count': 0,
                'class_counts': {},
                'is_processed': False,
                'error': str(e)
            }

class IFCObjectData(models.Model):
    """IFC 객체 데이터 (dd_by_ifc에서 개선된 버전)"""
    project = models.ForeignKey(IFCProject, on_delete=models.CASCADE, related_name='ifc_objects')
    global_id = models.CharField("GlobalId", max_length=100)
    name = models.CharField("이름", max_length=200, blank=True)
    ifc_class = models.CharField("IFC 클래스", max_length=100)
    spatial_container = models.CharField("공간 정보", max_length=500, blank=True)
    
    # JSON 필드로 속성 저장
    quantities = SimpleJSONField("수량 정보")
    properties = SimpleJSONField("속성 정보")
    
    # dd_by_ifc에서 가져온 추가 필드들
    cost_items = models.TextField("공사코드", blank=True)
    total_amount = models.DecimalField("총금액", max_digits=15, decimal_places=2, default=0)
    
    created_at = models.DateTimeField("생성일", auto_now_add=True)
    
    class Meta:
        verbose_name = "IFC 객체"
        verbose_name_plural = "IFC 객체들"
        constraints = [
            models.UniqueConstraint(
                fields=['project', 'global_id'], 
                name='unique_ifc_project_global_id'
            )
        ]
    
    def __str__(self):
        return f"{self.ifc_class} - {self.name or self.global_id}"
    
    def get_all_attributes(self):
        """모든 속성을 평면화해서 반환 (AI 모델 입력용)"""
        attributes = {
            'GlobalId': self.global_id,
            'Name': self.name,
            'IfcClass': self.ifc_class,
            'SpatialContainer': self.spatial_container,
            'CostItems': self.cost_items,
            'TotalAmount': float(self.total_amount),
        }
        
        # quantities 추가 (평면화)
        for key, value in self.quantities.items():
            if isinstance(value, (int, float)):
                attributes[key] = value
            elif isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    if isinstance(sub_value, (int, float)):
                        attributes[f"{key}.{sub_key}"] = sub_value
        
        # properties 추가 (평면화)
        for key, value in self.properties.items():
            if isinstance(value, (int, float, str)):
                if isinstance(value, (int, float)):
                    attributes[key] = value
                else:
                    # 문자열은 숫자로 변환 시도
                    try:
                        attributes[key] = float(value)
                    except:
                        attributes[key] = value
        
        return attributes

# =============================================================================
# AI-IFC 매핑 및 예측 관련
# =============================================================================

class IFCMapping(models.Model):
    """IFC 프로젝트와 AI 모델 매핑"""
    name = models.CharField("매핑명", max_length=200)
    project = models.ForeignKey(IFCProject, on_delete=models.CASCADE, related_name='mappings')
    ai_model = models.ForeignKey(AIModel, on_delete=models.CASCADE)
    
    # 입력 매핑 설정 (각 AI 모델 입력에 대한 매핑 정보)
    input_mappings = SimpleJSONField("입력 매핑")
    
    created_at = models.DateTimeField("생성일", auto_now_add=True)
    updated_at = models.DateTimeField("수정일", auto_now=True)
    
    class Meta:
        verbose_name = "IFC-AI 매핑"
        verbose_name_plural = "IFC-AI 매핑들"
    
    def __str__(self):
        return f"{self.name} ({self.project.name} → {self.ai_model.name})"

class IFCFilterCondition(models.Model):
    """IFC 객체 필터링 조건 (dd_by_ifc에서 가져옴)"""
    CONDITION_CHOICES = [
        ('equals', '같음'),
        ('contains', '포함'),
        ('starts_with', '시작함'),
        ('ends_with', '끝남'),
        ('greater_than', '보다 큼'),
        ('less_than', '보다 작음'),
        ('greater_equal', '크거나 같음'),
        ('less_equal', '작거나 같음'),
    ]
    
    RELATION_CHOICES = [
        ('and', 'AND'),
        ('or', 'OR'),
    ]
    
    session_key = models.CharField("세션 키", max_length=100)
    order = models.IntegerField("순서", default=0)
    
    attribute_name = models.CharField("속성명", max_length=200)
    condition = models.CharField("조건", max_length=20, choices=CONDITION_CHOICES)
    value = models.CharField("값", max_length=500)
    relation = models.CharField("관계", max_length=5, choices=RELATION_CHOICES, default='and')
    
    created_at = models.DateTimeField("생성일", auto_now_add=True)
    
    class Meta:
        verbose_name = "필터 조건"
        verbose_name_plural = "필터 조건들"
        ordering = ['order']
    
    def check_condition(self, obj_attributes):
        """객체가 이 조건을 만족하는지 확인"""
        attr_value = obj_attributes.get(self.attribute_name)
        
        if attr_value is None:
            return False
        
        # 문자열로 변환
        attr_str = str(attr_value).lower()
        value_str = str(self.value).lower()
        
        try:
            # 숫자 비교가 필요한 경우
            if self.condition in ['greater_than', 'less_than', 'greater_equal', 'less_equal']:
                attr_num = float(attr_value)
                value_num = float(self.value)
                
                if self.condition == 'greater_than':
                    return attr_num > value_num
                elif self.condition == 'less_than':
                    return attr_num < value_num
                elif self.condition == 'greater_equal':
                    return attr_num >= value_num
                elif self.condition == 'less_equal':
                    return attr_num <= value_num
            
            # 문자열 비교
            if self.condition == 'equals':
                return attr_str == value_str
            elif self.condition == 'contains':
                return value_str in attr_str
            elif self.condition == 'starts_with':
                return attr_str.startswith(value_str)
            elif self.condition == 'ends_with':
                return attr_str.endswith(value_str)
                
        except (ValueError, TypeError):
            # 숫자 변환 실패시 문자열 비교로 처리
            if self.condition == 'equals':
                return attr_str == value_str
            elif self.condition == 'contains':
                return value_str in attr_str
        
        return False

class PredictionHistory(models.Model):
    """예측 이력 (ai_prediction에서 가져옴)"""
    mapping = models.ForeignKey(IFCMapping, on_delete=models.CASCADE, related_name='predictions')
    
    # 입력/출력 데이터
    input_values = SimpleJSONField("입력값")
    prediction_result = SimpleJSONField("예측 결과")
    prediction_range = SimpleJSONField("예측 범위")
    
    # 실행 정보
    execution_time = models.FloatField("실행 시간(초)", default=0)
    
    created_at = models.DateTimeField("생성일", auto_now_add=True)
    
    class Meta:
        verbose_name = "예측 이력"
        verbose_name_plural = "예측 이력들"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Prediction for {self.mapping.name} at {self.created_at}"

# ifc_ai_prediction/urls.py (완전 통합 버전)
from django.urls import path
from . import views

app_name = 'ifc_ai_prediction'

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
]