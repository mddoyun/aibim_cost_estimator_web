# ifc_ai_prediction/__init__.py

"""
IFC AI Prediction App

IFC 모델 데이터를 AI 모델의 입력으로 활용하여 예측을 수행하는 Django 앱입니다.

주요 기능:
- IFC 파일 업로드 및 3D 모델 변환
- IFC 객체 데이터 추출 및 관리
- AI 모델과 IFC 데이터 매핑
- 조건별 데이터 집계 및 필터링
- 예측 실행 및 결과 관리
- PDF 보고서 생성

Author: AIBIM Team
Version: 1.0.0
"""

default_app_config = 'ifc_ai_prediction.apps.IFCAIPredictionConfig'