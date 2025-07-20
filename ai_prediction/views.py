from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.files.storage import default_storage
from django.utils import timezone
import json
import zipfile
import os
import tempfile
import base64
from io import BytesIO
from .models import AIModel, PredictionHistory

# PDF 생성을 위한 import
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, black, blue, red, green
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

# 한글 폰트 등록 (static 폴더 사용)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from django.conf import settings

# static 폴더에서 한글 폰트 등록
def register_korean_font_from_static():
    """static 폴더에 있는 한글 폰트를 등록합니다."""
    try:
        # static 폴더 경로
        static_root = settings.STATICFILES_DIRS[0] if settings.STATICFILES_DIRS else settings.STATIC_ROOT
        
        # 가능한 폰트 파일 이름들
        font_files = [
            'fonts/NanumGothic.ttf',
            'fonts/AppleGothic.ttf',
            'fonts/malgun.ttf',
            'fonts/gulim.ttf',
            'css/NanumGothic.ttf',  # css 폴더에 있을 수도 있음
        ]
        
        for font_file in font_files:
            font_path = os.path.join(static_root, font_file)
            if os.path.exists(font_path):
                try:
                    pdfmetrics.registerFont(TTFont('KoreanFont', font_path))
                    print(f"✅ 한글 폰트 등록 성공: {font_path}")
                    return True
                except Exception as e:
                    print(f"❌ 폰트 등록 실패: {font_path} - {e}")
                    continue
        
        # static 폰트가 없으면 시스템 폰트 시도
        print("static 폰트를 찾을 수 없습니다. 시스템 폰트를 시도합니다.")
        return register_system_korean_font()
        
    except Exception as e:
        print(f"static 폰트 등록 오류: {e}")
        return register_system_korean_font()

# 시스템 폰트 등록 (백업용)
def register_system_korean_font():
    """시스템 한글 폰트를 등록합니다."""
    try:
        import platform
        system = platform.system()
        
        if system == "Darwin":  # macOS
            font_paths = [
                "/Library/Fonts/AppleGothic.ttf",
                "/System/Library/Fonts/AppleSDGothicNeo.ttc",
                "/Library/Fonts/NanumGothic.ttf",
            ]
        elif system == "Windows":
            font_paths = [
                "C:/Windows/Fonts/malgun.ttf",
                "C:/Windows/Fonts/gulim.ttc",
            ]
        else:  # Linux
            font_paths = [
                "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
            ]
        
        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    pdfmetrics.registerFont(TTFont('KoreanFont', font_path))
                    print(f"✅ 시스템 한글 폰트 등록 성공: {font_path}")
                    return True
                except Exception as e:
                    print(f"❌ 시스템 폰트 등록 실패: {font_path} - {e}")
                    continue
        
        print("❌ 한글 폰트 등록 실패 - 기본 폰트 사용")
        return False
        
    except Exception as e:
        print(f"❌ 시스템 폰트 등록 오류: {e}")
        return False

# 한글 폰트 등록 실행
KOREAN_FONT_REGISTERED = register_korean_font_from_static()

def model_upload(request):
    """AI 모델 업로드 페이지"""
    if request.method == 'POST':
        try:
            name = request.POST.get('name')
            description = request.POST.get('description')
            model_file = request.FILES.get('model_file')
            
            if not name:
                return JsonResponse({'error': '모델 이름을 입력해주세요.'}, status=400)
            
            if not model_file:
                return JsonResponse({'error': '모델 파일을 선택해주세요.'}, status=400)
                
            # 파일 확장자 검증
            if not model_file.name.endswith('.zip'):
                return JsonResponse({'error': 'ZIP 파일만 업로드 가능합니다.'}, status=400)
            
            # ZIP 파일에서 메타데이터 추출
            metadata = extract_metadata_from_zip(model_file)
            
            # AI 모델 저장
            ai_model = AIModel.objects.create(
                name=name,
                description=description or '',
                model_file=model_file,
                metadata=metadata,
                rmse=metadata.get('rmse'),
                mae=metadata.get('mae'),
                r2_score=metadata.get('r2_score')
            )
            
            return JsonResponse({
                'success': True,
                'model_id': ai_model.id,
                'message': '모델이 성공적으로 업로드되었습니다.'
            })
            
        except Exception as e:
            return JsonResponse({'error': f'업로드 중 오류가 발생했습니다: {str(e)}'}, status=500)
    
    # 업로드된 모델 목록
    models = AIModel.objects.all().order_by('-created_at')
    return render(request, 'ai_prediction/model_upload.html', {'models': models})

def extract_metadata_from_zip(zip_file):
    """ZIP 파일에서 메타데이터 추출"""
    try:
        # 임시 파일로 저장
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as temp_file:
            for chunk in zip_file.chunks():
                temp_file.write(chunk)
            temp_file.flush()
            
            # ZIP 파일 읽기
            with zipfile.ZipFile(temp_file.name, 'r') as zip_ref:
                # 메타데이터 파일 찾기
                metadata_file = None
                for filename in zip_ref.namelist():
                    if filename.endswith('metadata.json'):
                        metadata_file = filename
                        break
                
                if not metadata_file:
                    raise ValueError("메타데이터 파일(metadata.json)을 찾을 수 없습니다.")
                
                # 메타데이터 읽기
                with zip_ref.open(metadata_file) as f:
                    metadata = json.load(f)
                
                # 필수 필드 검증
                if 'inputColumns' not in metadata:
                    raise ValueError("메타데이터에 inputColumns가 없습니다.")
                if 'outputColumns' not in metadata:
                    raise ValueError("메타데이터에 outputColumns가 없습니다.")
                
                return metadata
                
    except zipfile.BadZipFile:
        raise ValueError("올바른 ZIP 파일이 아닙니다.")
    except json.JSONDecodeError:
        raise ValueError("메타데이터 파일이 올바른 JSON 형식이 아닙니다.")
    finally:
        # 임시 파일 삭제
        try:
            os.unlink(temp_file.name)
        except:
            pass

def prediction_page(request, model_id):
    """예측 페이지"""
    ai_model = get_object_or_404(AIModel, id=model_id)
    
    # 최근 예측 이력
    recent_predictions = PredictionHistory.objects.filter(
        ai_model=ai_model
    ).order_by('-created_at')[:5]
    
    context = {
        'ai_model': ai_model,
        'recent_predictions': recent_predictions
    }
    
    return render(request, 'ai_prediction/prediction.html', context)

@csrf_exempt
def predict_api(request, model_id):
    """예측 API"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    ai_model = get_object_or_404(AIModel, id=model_id)
    
    try:
        # 입력 데이터 파싱
        input_data = json.loads(request.body)
        
        # 입력 데이터 검증
        expected_columns = ai_model.input_columns
        if not all(col in input_data for col in expected_columns):
            return JsonResponse({
                'error': f'Missing required columns: {expected_columns}'
            }, status=400)
        
        # 입력 데이터 정리
        input_values = [float(input_data[col]) for col in expected_columns]
        
        # 예측 결과 (실제로는 TensorFlow.js에서 처리됨)
        # 여기서는 프론트엔드에서 처리할 수 있도록 필요한 정보만 반환
        
        response_data = {
            'success': True,
            'input_data': input_values,
            'input_columns': expected_columns,
            'output_columns': ai_model.output_columns,
            'model_path': ai_model.model_file.url,
            'rmse': ai_model.rmse,
            'mae': ai_model.mae,
            'r2_score': ai_model.r2_score
        }
        
        return JsonResponse(response_data)
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def save_prediction(request, model_id):
    """예측 결과 저장"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    ai_model = get_object_or_404(AIModel, id=model_id)
    
    try:
        data = json.loads(request.body)
        
        # 예측 이력 저장
        prediction_history = PredictionHistory.objects.create(
            ai_model=ai_model,
            input_data=data.get('input_data', {}),
            prediction_result=data.get('prediction_result', {}),
            prediction_range=data.get('prediction_range', {})
        )
        
        return JsonResponse({
            'success': True,
            'prediction_id': prediction_history.id
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def get_model_metadata(request, model_id):
    """모델 메타데이터 조회 API"""
    ai_model = get_object_or_404(AIModel, id=model_id)
    
    return JsonResponse({
        'id': ai_model.id,
        'name': ai_model.name,
        'description': ai_model.description,
        'input_columns': ai_model.input_columns,
        'output_columns': ai_model.output_columns,
        'rmse': ai_model.rmse,
        'mae': ai_model.mae,
        'r2_score': ai_model.r2_score,
        'model_file_url': ai_model.model_file.url,
        'created_at': ai_model.created_at.isoformat()
    })

def model_list(request):
    """모델 목록 페이지"""
    models = AIModel.objects.all().order_by('-created_at')
    return render(request, 'ai_prediction/model_list.html', {'models': models})

@csrf_exempt
def delete_model(request, model_id):
    """모델 삭제 API"""
    if request.method != 'DELETE':
        return JsonResponse({'error': 'DELETE method required'}, status=405)
    
    try:
        ai_model = get_object_or_404(AIModel, id=model_id)
        
        # 파일 삭제
        if ai_model.model_file:
            ai_model.model_file.delete()
        
        # 모델 삭제
        ai_model.delete()
        
        return JsonResponse({'success': True, 'message': 'Model deleted successfully'})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def generate_prediction_pdf(request, model_id):
    """예측 결과 PDF 생성"""
    ai_model = get_object_or_404(AIModel, id=model_id)
    
    # POST 요청에서 예측 데이터 받기
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            input_data = data.get('input_data', {})
            prediction_result = data.get('prediction_result', {})
            prediction_range = data.get('prediction_range', {})
            chart_image = data.get('chart_image', '')  # base64 인코딩된 차트 이미지
            
            # PDF 생성
            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4, 
                                    topMargin=0.75*inch, bottomMargin=0.75*inch,
                                    leftMargin=0.75*inch, rightMargin=0.75*inch)
            
            # 스타일 설정 (한글 폰트 강제 적용)
            styles = getSampleStyleSheet()
            
            # 한글 폰트 사용
            font_name = 'KoreanFont' if KOREAN_FONT_REGISTERED else 'Helvetica'
            bold_font = 'KoreanFont' if KOREAN_FONT_REGISTERED else 'Helvetica-Bold'
            
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Title'],
                fontSize=16,
                spaceAfter=30,
                textColor=HexColor('#1f4e79'),
                alignment=TA_CENTER,
                fontName=bold_font
            )
            
            heading_style = ParagraphStyle(
                'CustomHeading',
                parent=styles['Heading2'],
                fontSize=12,
                spaceAfter=12,
                textColor=HexColor('#2c5282'),
                alignment=TA_LEFT,
                fontName=bold_font
            )
            
            normal_style = ParagraphStyle(
                'CustomNormal',
                parent=styles['Normal'],
                fontSize=9,
                spaceAfter=6,
                alignment=TA_LEFT,
                fontName=font_name
            )
            
            # PDF 콘텐츠 생성 (한글 버전)
            content = []
            
            # 제목
            content.append(Paragraph("AI 예측 결과 보고서", title_style))
            content.append(Spacer(1, 20))
            
            # 모델 정보 섹션
            content.append(Paragraph("모델 정보", heading_style))
            
            model_info_data = [
                ['모델 이름', ai_model.name],
                ['모델 설명', ai_model.description or '설명 없음'],
                ['생성일', ai_model.created_at.strftime('%Y-%m-%d %H:%M:%S')],
                ['입력 변수', ', '.join(ai_model.input_columns)],
                ['출력 변수', ', '.join(ai_model.output_columns)],
            ]
            
            if ai_model.rmse:
                model_info_data.extend([
                    ['RMSE', f"{ai_model.rmse:.4f}"],
                    ['MAE', f"{ai_model.mae:.4f}"],
                    ['R² 점수', f"{ai_model.r2_score:.4f}"],
                ])
            
            model_table = Table(model_info_data, colWidths=[2*inch, 4*inch])
            model_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), HexColor('#f7fafc')),
                ('TEXTCOLOR', (0, 0), (-1, -1), black),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, -1), font_name),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 1, HexColor('#e2e8f0')),
                ('FONTNAME', (0, 0), (0, -1), bold_font),
            ]))
            
            content.append(model_table)
            content.append(Spacer(1, 20))
            
            # 입력 데이터 섹션
            content.append(Paragraph("입력 데이터", heading_style))
            
            input_data_list = []
            for col in ai_model.input_columns:
                value = input_data.get(col, 'N/A')
                input_data_list.append([col, str(value)])
            
            input_table = Table(input_data_list, colWidths=[2*inch, 4*inch])
            input_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), HexColor('#f0f9ff')),
                ('TEXTCOLOR', (0, 0), (-1, -1), black),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, -1), font_name),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 1, HexColor('#e2e8f0')),
                ('FONTNAME', (0, 0), (0, -1), bold_font),
            ]))
            
            content.append(input_table)
            content.append(Spacer(1, 20))
            
            # 예측 결과 섹션
            content.append(Paragraph("예측 결과", heading_style))
            
            prediction_value = prediction_result.get('value', 0)
            min_value = prediction_range.get('min', 0)
            max_value = prediction_range.get('max', 0)
            confidence = prediction_range.get('confidence', 0)
            
            result_data = [
                ['예측값', f"{prediction_value:.2f}"],
                ['최솟값', f"{min_value:.2f}"],
                ['최댓값', f"{max_value:.2f}"],
                ['신뢰도', f"{confidence * 100:.1f}%"],
                ['오차 범위', f"±{(max_value - min_value) / 2:.2f}"],
            ]
            
            result_table = Table(result_data, colWidths=[2*inch, 4*inch])
            result_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), HexColor('#f0fff4')),
                ('TEXTCOLOR', (0, 0), (-1, -1), black),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, -1), font_name),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 1, HexColor('#e2e8f0')),
                ('FONTNAME', (0, 0), (0, -1), bold_font),
                ('BACKGROUND', (0, 0), (0, 0), HexColor('#22c55e')),
                ('TEXTCOLOR', (0, 0), (0, 0), HexColor('#ffffff')),
            ]))
            
            content.append(result_table)
            content.append(Spacer(1, 20))
            
            # 차트 이미지 추가 (프론트엔드에서 생성된 이미지)
            if chart_image:
                try:
                    # base64 이미지 디코딩
                    if ',' in chart_image:
                        chart_data = base64.b64decode(chart_image.split(',')[1])
                        chart_buffer = BytesIO(chart_data)
                        
                        content.append(Paragraph("예측 결과 차트", heading_style))
                        chart_img = Image(chart_buffer, width=5*inch, height=3*inch)
                        content.append(chart_img)
                        content.append(Spacer(1, 20))
                    else:
                        # base64 데이터가 올바르지 않은 경우 텍스트 요약으로 대체
                        content.append(Paragraph("예측 결과 요약", heading_style))
                        chart_text = f"""
                        예측값: {prediction_value:.2f}<br/>
                        최솟값: {min_value:.2f}<br/>
                        최댓값: {max_value:.2f}<br/>
                        오차 범위: ±{(max_value - min_value) / 2:.2f}
                        """
                        content.append(Paragraph(chart_text, normal_style))
                        content.append(Spacer(1, 20))
                except Exception as e:
                    print(f"차트 이미지 처리 오류: {e}")
                    # 오류 발생 시 텍스트 요약으로 대체
                    content.append(Paragraph("예측 결과 요약", heading_style))
                    chart_text = f"""
                    예측값: {prediction_value:.2f}<br/>
                    최솟값: {min_value:.2f}<br/>
                    최댓값: {max_value:.2f}<br/>
                    오차 범위: ±{(max_value - min_value) / 2:.2f}
                    """
                    content.append(Paragraph(chart_text, normal_style))
                    content.append(Spacer(1, 20))
            else:
                # 차트 이미지가 없는 경우 텍스트 요약
                content.append(Paragraph("예측 결과 요약", heading_style))
                chart_text = f"""
                예측값: {prediction_value:.2f}<br/>
                최솟값: {min_value:.2f}<br/>
                최댓값: {max_value:.2f}<br/>
                오차 범위: ±{(max_value - min_value) / 2:.2f}
                """
                content.append(Paragraph(chart_text, normal_style))
                content.append(Spacer(1, 20))
            
            # 생성 정보
            content.append(Spacer(1, 30))
            content.append(Paragraph("보고서 생성 정보", heading_style))
            
            generation_info = [
                ['생성일시', timezone.now().strftime('%Y-%m-%d %H:%M:%S')],
                ['시스템', 'AIBIM Cost Estimator'],
                ['버전', '1.0'],
            ]
            
            generation_table = Table(generation_info, colWidths=[2*inch, 4*inch])
            generation_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), HexColor('#fef3c7')),
                ('TEXTCOLOR', (0, 0), (-1, -1), black),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, -1), font_name),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 1, HexColor('#e2e8f0')),
                ('FONTNAME', (0, 0), (0, -1), bold_font),
            ]))
            
            content.append(generation_table)
            
            # PDF 빌드
            doc.build(content)
            
            # 응답 생성
            buffer.seek(0)
            response = HttpResponse(buffer.read(), content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="prediction_report_{ai_model.name}_{timezone.now().strftime("%Y%m%d_%H%M%S")}.pdf"'
            
            return response
            
        except Exception as e:
            return JsonResponse({'error': f'PDF 생성 오류: {str(e)}'}, status=500)
    
    return JsonResponse({'error': 'POST method required'}, status=405)