# ifc_ai_prediction/admin.py

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
import json

from .models import (
    IFCProject, IFCObjectData, IFCFilterCondition,
    AIModel, IFCMapping, PredictionHistory
)

# =============================================================================
# IFC 관련 Admin
# =============================================================================

@admin.register(IFCProject)
class IFCProjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_processed', 'objects_count', 'created_at', 'file_size', 'project_actions']
    list_filter = ['is_processed', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at', 'processing_info']
    
    fieldsets = (
        ('기본 정보', {
            'fields': ('name', 'description')
        }),
        ('파일', {
            'fields': ('ifc_file', 'converted_obj')
        }),
        ('처리 상태', {
            'fields': ('is_processed', 'processing_error', 'processing_info')
        }),
        ('생성 정보', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def objects_count(self, obj):
        count = IFCObjectData.objects.filter(project=obj).count()
        if count > 0:
            url = reverse('admin:ifc_ai_prediction_ifcobjectdata_changelist')
            return format_html(
                '<a href="{}?project__id={}" target="_blank">{} 개</a>',
                url, obj.id, count
            )
        return '0 개'
    objects_count.short_description = '객체 수'
    
    def file_size(self, obj):
        if obj.ifc_file:
            try:
                size = obj.ifc_file.size
                if size < 1024:
                    return f'{size} bytes'
                elif size < 1024 * 1024:
                    return f'{size / 1024:.1f} KB'
                else:
                    return f'{size / (1024 * 1024):.1f} MB'
            except:
                return '알 수 없음'
        return '-'
    file_size.short_description = '파일 크기'
    
    def project_actions(self, obj):  # actions → project_actions로 변경
        action_buttons = []
        if obj.is_processed:
            predict_url = reverse('ifc_ai_prediction:prediction_page', args=[obj.id])
            action_buttons.append(f'<a href="{predict_url}" target="_blank" class="button">예측하기</a>')
            
            history_url = reverse('ifc_ai_prediction:prediction_history', args=[obj.id])
            action_buttons.append(f'<a href="{history_url}" target="_blank" class="button">이력보기</a>')
        return format_html(' '.join(action_buttons))
    project_actions.short_description = '액션'
    
    def processing_info(self, obj):
        summary = obj.get_ifc_objects_summary()
        info_html = f"""
        <div style="background: #f8f9fa; padding: 10px; border-radius: 4px;">
            <strong>처리 정보:</strong><br>
            • 총 객체 수: {summary['total_count']}개<br>
            • 처리 상태: {'완료' if summary['is_processed'] else '미완료'}<br>
        """
        
        if summary['class_counts']:
            info_html += "<strong>클래스별 개수:</strong><br>"
            for class_name, count in list(summary['class_counts'].items())[:5]:
                info_html += f"• {class_name}: {count}개<br>"
            if len(summary['class_counts']) > 5:
                info_html += f"• 외 {len(summary['class_counts']) - 5}개 클래스...<br>"
        
        info_html += "</div>"
        return mark_safe(info_html)
    processing_info.short_description = '처리 정보'

@admin.register(IFCObjectData)
class IFCObjectDataAdmin(admin.ModelAdmin):
    list_display = ['global_id', 'name', 'ifc_class', 'project', 'cost_items_display', 'total_amount']
    list_filter = ['project', 'ifc_class', 'created_at']
    search_fields = ['global_id', 'name', 'ifc_class', 'cost_items']
    readonly_fields = ['created_at', 'attributes_preview']
    
    fieldsets = (
        ('기본 정보', {
            'fields': ('project', 'global_id', 'name', 'ifc_class', 'spatial_container')
        }),
        ('비용 정보', {
            'fields': ('cost_items', 'total_amount')
        }),
        ('속성 정보', {
            'fields': ('attributes_preview',),
            'classes': ('collapse',)
        }),
        ('생성 정보', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def cost_items_display(self, obj):
        if obj.cost_items:
            codes = obj.cost_items.split('+')
            if len(codes) > 3:
                return f"{', '.join(codes[:3])}... ({len(codes)}개)"
            return obj.cost_items.replace('+', ', ')
        return '-'
    cost_items_display.short_description = '공사코드'
    
    def attributes_preview(self, obj):
        attributes = obj.get_all_attributes()
        
        preview_html = "<div style='background: #f8f9fa; padding: 10px; border-radius: 4px;'>"
        preview_html += "<strong>모든 속성:</strong><br>"
        
        # 주요 속성들 먼저 표시
        main_attrs = ['GlobalId', 'Name', 'IfcClass', 'SpatialContainer']
        for attr in main_attrs:
            if attr in attributes:
                preview_html += f"<strong>{attr}:</strong> {attributes[attr]}<br>"
        
        # 나머지 속성들
        other_attrs = {k: v for k, v in attributes.items() if k not in main_attrs}
        if other_attrs:
            preview_html += "<br><strong>기타 속성:</strong><br>"
            for key, value in list(other_attrs.items())[:10]:  # 최대 10개만 표시
                preview_html += f"• {key}: {value}<br>"
            if len(other_attrs) > 10:
                preview_html += f"• 외 {len(other_attrs) - 10}개 속성...<br>"
        
        preview_html += "</div>"
        return mark_safe(preview_html)
    attributes_preview.short_description = '속성 미리보기'

@admin.register(IFCFilterCondition)
class IFCFilterConditionAdmin(admin.ModelAdmin):
    list_display = ['session_key', 'order', 'attribute_name', 'condition', 'value', 'relation']
    list_filter = ['condition', 'relation', 'created_at']
    search_fields = ['session_key', 'attribute_name', 'value']
    ordering = ['session_key', 'order']

# =============================================================================
# AI 모델 관련 Admin
# =============================================================================

@admin.register(AIModel)
class AIModelAdmin(admin.ModelAdmin):
    list_display = ['name', 'input_columns_display', 'output_columns_display', 'performance_metrics', 'created_at', 'model_actions']
    list_filter = ['created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at', 'metadata_preview']
    
    fieldsets = (
        ('기본 정보', {
            'fields': ('name', 'description', 'model_file')
        }),
        ('성능 지표', {
            'fields': ('rmse', 'mae', 'r2_score')
        }),
        ('메타데이터', {
            'fields': ('metadata_preview',),
            'classes': ('collapse',)
        }),
        ('생성 정보', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def input_columns_display(self, obj):
        cols = obj.input_columns
        if len(cols) > 3:
            return f"{', '.join(cols[:3])}... ({len(cols)}개)"
        return ', '.join(cols)
    input_columns_display.short_description = '입력 컬럼'
    
    def output_columns_display(self, obj):
        return ', '.join(obj.output_columns)
    output_columns_display.short_description = '출력 컬럼'
    
    def performance_metrics(self, obj):
        metrics = []
        if obj.rmse:
            metrics.append(f"RMSE: {obj.rmse:.4f}")
        if obj.mae:
            metrics.append(f"MAE: {obj.mae:.4f}")
        if obj.r2_score:
            metrics.append(f"R²: {obj.r2_score:.4f}")
        return ' | '.join(metrics) if metrics else '-'
    performance_metrics.short_description = '성능 지표'
    
    def model_actions(self, obj):  # actions → model_actions로 변경
        mappings_count = IFCMapping.objects.filter(ai_model=obj).count()
        predictions_count = PredictionHistory.objects.filter(mapping__ai_model=obj).count()
        
        return format_html(
            '<div style="font-size: 0.9em;">'
            '매핑: {}개<br>'
            '예측: {}개'
            '</div>',
            mappings_count, predictions_count
        )
    model_actions.short_description = '사용 현황'
    
    def metadata_preview(self, obj):
        metadata_html = "<div style='background: #f8f9fa; padding: 10px; border-radius: 4px;'>"
        metadata_html += "<strong>전체 메타데이터:</strong><br>"
        metadata_html += f"<pre>{json.dumps(obj.metadata, indent=2, ensure_ascii=False)}</pre>"
        metadata_html += "</div>"
        return mark_safe(metadata_html)
    metadata_preview.short_description = '메타데이터'

# =============================================================================
# 매핑 및 예측 관련 Admin
# =============================================================================

@admin.register(IFCMapping)
class IFCMappingAdmin(admin.ModelAdmin):
    list_display = ['name', 'project', 'ai_model', 'predictions_count', 'created_at', 'mapping_actions']
    list_filter = ['created_at', 'ai_model', 'project']
    search_fields = ['name', 'project__name', 'ai_model__name']
    readonly_fields = ['created_at', 'updated_at', 'input_mappings_preview']
    
    fieldsets = (
        ('기본 정보', {
            'fields': ('name', 'project', 'ai_model')
        }),
        ('입력 매핑', {
            'fields': ('input_mappings_preview',),
            'classes': ('collapse',)
        }),
        ('생성 정보', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def predictions_count(self, obj):
        count = PredictionHistory.objects.filter(mapping=obj).count()
        if count > 0:
            url = reverse('admin:ifc_ai_prediction_predictionhistory_changelist')
            return format_html(
                '<a href="{}?mapping__id={}" target="_blank">{} 개</a>',
                url, obj.id, count
            )
        return '0 개'
    predictions_count.short_description = '예측 수'
    
    def mapping_actions(self, obj):  # actions → mapping_actions로 변경
        predict_url = reverse('ifc_ai_prediction:prediction_page', args=[obj.project.id])
        history_url = reverse('ifc_ai_prediction:prediction_history', args=[obj.project.id])
        
        return format_html(
            '<a href="{}" target="_blank" class="button">예측하기</a> '
            '<a href="{}" target="_blank" class="button">이력보기</a>',
            predict_url, history_url
        )
    mapping_actions.short_description = '액션'
    
    def input_mappings_preview(self, obj):
        mappings_html = "<div style='background: #f8f9fa; padding: 10px; border-radius: 4px;'>"
        mappings_html += "<strong>입력 매핑 설정:</strong><br>"
        
        for column, mapping in obj.input_mappings.items():
            mappings_html += f"<strong>{column}:</strong> "
            if mapping.get('type') == 'manual':
                mappings_html += f"직접입력 ({mapping.get('value', 0)})"
            elif mapping.get('type') == 'ifc_aggregation':
                attr = mapping.get('aggregation_attribute', '-')
                func = mapping.get('aggregation_function', '-')
                mappings_html += f"집계 ({func}({attr}))"
            else:
                mappings_html += "알 수 없음"
            mappings_html += "<br>"
        
        mappings_html += "</div>"
        return mark_safe(mappings_html)
    input_mappings_preview.short_description = '입력 매핑'

@admin.register(PredictionHistory)
class PredictionHistoryAdmin(admin.ModelAdmin):
    list_display = ['id', 'mapping', 'prediction_value', 'confidence', 'execution_time', 'created_at', 'prediction_actions']
    list_filter = ['created_at', 'mapping__ai_model', 'mapping__project']
    search_fields = ['mapping__name', 'mapping__project__name', 'mapping__ai_model__name']
    readonly_fields = ['created_at', 'prediction_details', 'input_values_preview']
    
    fieldsets = (
        ('기본 정보', {
            'fields': ('mapping', 'execution_time', 'created_at')
        }),
        ('입력 데이터', {
            'fields': ('input_values_preview',),
            'classes': ('collapse',)
        }),
        ('예측 결과', {
            'fields': ('prediction_details',),
        }),
    )
    
    def prediction_value(self, obj):
        value = obj.prediction_result.get('value', 0)
        return f"{value:.2f}"
    prediction_value.short_description = '예측값'
    
    def confidence(self, obj):
        conf = obj.prediction_range.get('confidence', 0)
        return f"{conf * 100:.1f}%"
    confidence.short_description = '신뢰도'
    
    def prediction_actions(self, obj):  # actions → prediction_actions로 변경
        predict_url = reverse('ifc_ai_prediction:prediction_page', args=[obj.mapping.project.id])
        return format_html(
            '<a href="{}" target="_blank" class="button">새 예측</a>',
            predict_url
        )
    prediction_actions.short_description = '액션'
    
    def prediction_details(self, obj):
        result = obj.prediction_result
        range_info = obj.prediction_range
        
        details_html = """
        <div style='background: #f8f9fa; padding: 10px; border-radius: 4px;'>
            <strong>예측 결과:</strong><br>
            • 예측값: {:.4f}<br>
            • 신뢰도: {:.1f}%<br>
            • 최솟값: {:.4f}<br>
            • 최댓값: {:.4f}<br>
            • 오차범위: ±{:.4f}
        </div>
        """.format(
            result.get('value', 0),
            range_info.get('confidence', 0) * 100,
            range_info.get('min', 0),
            range_info.get('max', 0),
            (range_info.get('max', 0) - range_info.get('min', 0)) / 2
        )
        
        return mark_safe(details_html)
    prediction_details.short_description = '예측 상세'
    
    def input_values_preview(self, obj):
        values_html = "<div style='background: #f8f9fa; padding: 10px; border-radius: 4px;'>"
        values_html += "<strong>입력값:</strong><br>"
        
        for key, value in obj.input_values.items():
            values_html += f"• {key}: {value}<br>"
        
        values_html += "</div>"
        return mark_safe(values_html)
    input_values_preview.short_description = '입력값'

# =============================================================================
# Admin 사이트 커스터마이징
# =============================================================================

# Admin 사이트 제목 설정
admin.site.site_header = "IFC AI 예측 시스템 관리"
admin.site.site_title = "IFC AI 예측"
admin.site.index_title = "IFC AI 예측 시스템"

print("✅ IFC AI Prediction Admin 설정 완료 (오류 수정됨)")
print("🔧 수정사항:")
print("   - actions → project_actions/model_actions/mapping_actions/prediction_actions")
print("   - Django Admin 예약어 충돌 해결")