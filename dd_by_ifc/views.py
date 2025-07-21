# dd_by_ifc/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Sum
from django.contrib import messages
from .models import Project, IFCObject, CostCode, ObjectIdMap
import os
import json
import csv
from collections import defaultdict
import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element
from django.core.files import File
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from .models import IFCObject
from django.db import transaction
# ./dd_by_ifc/views.py

from django.shortcuts import redirect
from django.contrib import messages

def delete_project(request, project_id):
    from .models import Project
    project = Project.objects.filter(id=project_id).first()
    if project:
        project.delete()
        messages.success(request, "프로젝트가 삭제되었습니다.")
    else:
        messages.error(request, "프로젝트를 찾을 수 없습니다.")
    return redirect('dd_by_ifc:project_list')


def convert_ifc_to_obj(ifc_path, obj_path):
    import ifcopenshell
    import ifcopenshell.geom

    try:
        # 디렉토리가 없으면 생성
        os.makedirs(os.path.dirname(obj_path), exist_ok=True)
        
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        model = ifcopenshell.open(ifc_path)
        
        print(f"🔄 IFC → OBJ 변환 시작: {ifc_path}")
        
        # 모든 3D 객체 가져오기
        products = []
        for ifc_type in ["IfcProduct", "IfcElement", "IfcBuildingElement"]:
            products.extend(model.by_type(ifc_type))
        
        # 중복 제거
        products = list(set(products))
        print(f"📦 변환할 IFC 객체 수: {len(products)}개")
        
        shape_reps = []
        processed_count = 0
        
        for elem in products:
            try:
                # 기하학적 표현이 있는지 확인
                if hasattr(elem, 'Representation') and elem.Representation:
                    shape = ifcopenshell.geom.create_shape(settings, elem)
                    verts = shape.geometry.verts
                    faces = shape.geometry.faces
                    
                    if len(verts) > 0 and len(faces) > 0:
                        shape_reps.append((verts, faces))
                        processed_count += 1
                        
                        if processed_count % 100 == 0:
                            print(f"  처리 중... {processed_count}개 완료")
                            
            except Exception as e:
                # 개별 객체 실패는 무시
                continue

        print(f"✅ 기하학적 형상 추출 완료: {processed_count}개")

        # OBJ 파일 작성
        with open(obj_path, "w") as f:
            f.write("# OBJ file generated from IFC\n")
            f.write(f"# Total objects: {len(shape_reps)}\n\n")
            
            vertex_offset = 1
            
            for idx, (verts, faces) in enumerate(shape_reps):
                f.write(f"# Object {idx}\n")
                f.write(f"o Object_{idx}\n")
                
                # 정점 쓰기
                for i in range(0, len(verts), 3):
                    f.write(f"v {verts[i]:.6f} {verts[i+1]:.6f} {verts[i+2]:.6f}\n")
                
                # 면 쓰기
                for i in range(0, len(faces), 3):
                    f.write(f"f {faces[i]+vertex_offset} {faces[i+1]+vertex_offset} {faces[i+2]+vertex_offset}\n")
                
                vertex_offset += len(verts) // 3
                f.write("\n")
        
        # 파일 크기 확인
        file_size = os.path.getsize(obj_path)
        print(f"✅ OBJ 파일 생성 완료: {obj_path} ({file_size:,} bytes)")
        
        # 빈 파일이면 기본 박스 생성
        if file_size < 100 or len(shape_reps) == 0:
            print("⚠️ 변환된 객체가 없거나 파일이 너무 작습니다. 기본 박스를 생성합니다.")
            create_default_box_obj(obj_path)
            
    except Exception as e:
        print(f"❌ IFC → OBJ 변환 실패: {e}")
        import traceback
        traceback.print_exc()
        
        # 실패 시 기본 박스 생성
        create_default_box_obj(obj_path)

def create_default_box_obj(obj_path):
    """기본 박스 OBJ 파일 생성"""
    try:
        with open(obj_path, "w") as f:
            f.write("# Default box geometry\n")
            f.write("o Box\n")
            # 정점 (큐브의 8개 꼭지점)
            f.write("v -1.0 -1.0 -1.0\n")
            f.write("v 1.0 -1.0 -1.0\n")  
            f.write("v 1.0 1.0 -1.0\n")
            f.write("v -1.0 1.0 -1.0\n")
            f.write("v -1.0 -1.0 1.0\n")
            f.write("v 1.0 -1.0 1.0\n")
            f.write("v 1.0 1.0 1.0\n")
            f.write("v -1.0 1.0 1.0\n")
            # 면 (큐브의 6개 면)
            f.write("f 1 2 3 4\n")  # 앞면
            f.write("f 5 8 7 6\n")  # 뒷면
            f.write("f 1 5 6 2\n")  # 아래면
            f.write("f 2 6 7 3\n")  # 오른쪽면
            f.write("f 3 7 8 4\n")  # 위면
            f.write("f 5 1 4 8\n")  # 왼쪽면
        print(f"✅ 기본 박스 OBJ 파일 생성: {obj_path}")
    except Exception as e:
        print(f"❌ 기본 박스 생성 실패: {e}")

def process_ifc_objects(project):
    """IFC 파일에서 객체들을 추출하여 데이터베이스에 저장"""
    try:
        ifc_path = project.ifc_file.path
        model = ifcopenshell.open(ifc_path)
        
        # 기존 객체 삭제
        IFCObject.objects.filter(project=project).delete()
        
        # IFC 객체 추출
        objects = model.by_type("IfcProduct")
        
        for obj in objects:
            # 기본 정보
            global_id = getattr(obj, "GlobalId", "")
            name = getattr(obj, "Name", "") or ""
            ifc_class = obj.is_a()
            
            # 수량 정보 추출
            quantities = {}
            all_quantity_keys = set()
            
            for rel in getattr(obj, "IsDefinedBy", []):
                if rel.is_a("IfcRelDefinesByProperties"):
                    prop_def = rel.RelatingPropertyDefinition
                    if prop_def.is_a("IfcElementQuantity"):
                        for q in prop_def.Quantities:
                            if hasattr(q, "Name"):
                                full_key = q.Name
                                short_key = full_key.split(".")[-1]  # 'Width', 'Height' 등만 사용
                                
                                for attr in ["LengthValue", "AreaValue", "VolumeValue", "CountValue", "WeightValue"]:
                                    if hasattr(q, attr):
                                        value = getattr(q, attr)
                                        all_quantity_keys.add(short_key)
                                        
                                        # flat: 'Width' 형태
                                        quantities[short_key] = value
                                        
                                        # dict 구조도 유지
                                        if "." in full_key:
                                            outer, inner = full_key.split(".", 1)
                                            if outer not in quantities or not isinstance(quantities[outer], dict):
                                                quantities[outer] = {}
                                            quantities[outer][inner] = value
                                        break
            
            # 속성 정보 추출 (Psets)
            properties = {}
            all_pset_keys = set()
            cost_items = ""
            
            try:
                psets = ifcopenshell.util.element.get_psets(obj)
                for pset_name, props in psets.items():
                    if isinstance(props, dict):
                        for prop_name, prop_value in props.items():
                            key = f"{pset_name}.{prop_name}"
                            properties[key] = prop_value
                            all_pset_keys.add(key)
                            
                            # CostItems 속성 찾기 (cnv_general PropertySet에서)
                            if pset_name == "cnv_general" and prop_name == "CostItems":
                                cost_items = str(prop_value) if prop_value else ""
            except Exception as e:
                print(f"⚠️ Pset 파싱 오류: {e}")
            
            # 공간 정보
            spatial_container = ""
            try:
                spatial_names = []
                for rel in obj.ContainedInStructure or []:
                    if rel.is_a("IfcRelContainedInSpatialStructure"):
                        container = rel.RelatingStructure
                        spatial_names.append(f"{container.is_a()}:{getattr(container, 'Name', '')}")
                spatial_container = ", ".join(spatial_names)
            except:
                pass
            
            # IFC 객체 생성
            ifc_obj = IFCObject.objects.create(
                project=project,
                global_id=global_id,
                name=name,
                ifc_class=ifc_class,
                spatial_container=spatial_container,
                quantities=quantities,
                properties=properties,
                cost_items=cost_items  # CostItems 값
            )
            
            # 총금액 계산
            ifc_obj.calculate_total_amount()
        
        # 처리 완료 표시
        project.is_processed = True
        project.processing_error = None
        project.save()
        
    except Exception as e:
        print(f"IFC 파일 처리 오류: {e}")
        project.is_processed = False
        project.processing_error = str(e)
        project.save()

# =============================================================================
# 새로운 뷰 함수들 (프로젝트 리스트 방식으로 변경)
# =============================================================================

def project_list(request):
    """DD 프로젝트 목록 페이지"""
    try:
        projects = Project.objects.all().order_by('-created_at')
        
        # 각 프로젝트의 요약 정보 추가
        for project in projects:
            try:
                project.objects_count = IFCObject.objects.filter(project=project).count()
                project.total_amount = IFCObject.objects.filter(project=project).aggregate(
                    total=Sum('total_amount')
                )['total'] or 0
            except Exception as e:
                project.objects_count = 0
                project.total_amount = 0
                print(f"프로젝트 {project.id} 요약 정보 계산 오류: {e}")
        
        context = {
            'projects': projects,
        }
        
        return render(request, 'dd_by_ifc/project_list.html', context)
        
    except Exception as e:
        print(f"❌ DD 프로젝트 목록 로드 오류: {e}")
        import traceback
        traceback.print_exc()
        
        context = {
            'projects': [],
            'error_message': f'프로젝트 로드 중 오류: {str(e)}'
        }
        
        return render(request, 'dd_by_ifc/project_list.html', context)

def upload_project(request):
    """새 프로젝트 업로드 페이지"""
    if request.method == 'POST':
        try:
            name = request.POST.get('name')
            use = request.POST.get('use', '')
            ifc_file = request.FILES.get('ifc_file')

            if not name or not ifc_file:
                messages.error(request, '프로젝트명과 IFC 파일을 모두 입력해주세요.')
                return render(request, 'dd_by_ifc/upload.html')

            # 프로젝트 생성
            project = Project.objects.create(
                name=name,
                use=use,
                ifc_file=ifc_file,
                is_processed=False
            )
            
            # IFC → OBJ 변환
            try:
                ifc_path = project.ifc_file.path
                obj_filename = os.path.splitext(os.path.basename(ifc_path))[0] + '.obj'
                obj_path = os.path.join(os.path.dirname(ifc_path), obj_filename)
                
                print(f"🔄 IFC → OBJ 변환 시작")
                convert_ifc_to_obj(ifc_path, obj_path)

                if os.path.exists(obj_path):
                    with open(obj_path, 'rb') as f:
                        project.converted_obj.save(obj_filename, File(f), save=True)
                    
                    if os.path.exists(obj_path) and obj_path != project.converted_obj.path:
                        os.remove(obj_path)
                        
            except Exception as e:
                print(f"❌ OBJ 변환 중 오류: {e}")

            # IFC 객체 처리
            print(f"📦 IFC 객체 처리 시작")
            process_ifc_objects(project)
            
            messages.success(request, f'프로젝트 "{name}"이 업로드되고 처리되었습니다.')
            return redirect('dd_by_ifc:project_detail', project_id=project.id)

        except Exception as e:
            print(f"❌ 업로드 중 오류: {e}")
            import traceback
            traceback.print_exc()
            
            messages.error(request, f'업로드 중 오류가 발생했습니다: {str(e)}')
            return render(request, 'dd_by_ifc/upload.html')

    return render(request, 'dd_by_ifc/upload.html')

def project_detail(request, project_id):
    """프로젝트 상세 작업 페이지 (기존 dd_by_ifc_result)"""
    try:
        project = get_object_or_404(Project, id=project_id)
        
        if not project.is_processed:
            messages.warning(request, '프로젝트가 아직 처리 중입니다. 잠시 후 다시 시도해주세요.')
            return redirect('dd_by_ifc:project_list')
        
        # 브라우저에서 직접 fetch 할 수 있도록 절대 URL 생성
        ifc_abs_url = request.build_absolute_uri(project.ifc_file.url) if project.ifc_file else ""
        
        context = {
            'project': project,
            'ifc_abs_url': ifc_abs_url,
        }
        
        return render(request, 'dd_by_ifc/project_detail.html', context)
        
    except Exception as e:
        print(f"❌ 프로젝트 상세 페이지 오류: {e}")
        messages.error(request, f'오류가 발생했습니다: {str(e)}')
        return redirect('dd_by_ifc:project_list')

# 기존 뷰 함수들 (dd_by_ifc_result에서 사용하던 것들)
def go_dd_by_ifc(request):
    """기존 업로드 방식 - 프로젝트 목록으로 리다이렉트"""
    return redirect('dd_by_ifc:project_list')

def go_dd_by_ifc_result(request, project_id):
    """기존 URL 호환성을 위한 리다이렉트"""
    return redirect('dd_by_ifc:project_detail', project_id=project_id)

# API 엔드포인트들 (기존 코드 유지)

@csrf_exempt
@require_http_methods(["GET"])
def get_ifc_objects(request, project_id):
    """IFC 객체 목록 반환"""
    project = get_object_or_404(Project, id=project_id)
    objects = IFCObject.objects.filter(project=project)
    
    # 검색 필터
    search = request.GET.get('search', '')
    if search:
        objects = objects.filter(
            Q(name__icontains=search) | 
            Q(ifc_class__icontains=search) |
            Q(global_id__icontains=search)
        )
    
    # 데이터 직렬화
    object_data = []
    all_headers = set(['GlobalId', 'Name', 'IfcClass', 'CostItems', '총금액', 'SpatialContainer'])
    
    for obj in objects:
        row_data = {
            'GlobalId': obj.global_id,
            'Name': obj.name,
            'IfcClass': obj.ifc_class,
            'CostItems': obj.cost_items,
            '총금액': float(obj.total_amount),
            'SpatialContainer': obj.spatial_container,
            'Quantities': obj.quantities,
            'Properties': obj.properties
        }
        
        # 수량 정보를 flat하게 추가
        for key, value in obj.quantities.items():
            if isinstance(value, (int, float)):
                row_data[key] = value
                all_headers.add(key)
        
        # 속성 정보 추가
        for key, value in obj.properties.items():
            row_data[key] = value
            all_headers.add(key)
        
        object_data.append(row_data)
    
    return JsonResponse({
        'objects': object_data,
        'headers': list(all_headers),
        'total_count': len(object_data)
    })

@csrf_exempt
@require_http_methods(["POST"])
def search_cost_codes(request):
    """공사코드 검색"""
    query = request.POST.get('query', '').strip()
    
    if not query:
        return JsonResponse({'results': []})
    
    codes = CostCode.objects.filter(
        Q(code__icontains=query) |
        Q(name__icontains=query)
    )[:20]
    
    results = []
    for code in codes:
        results.append({
            'code': code.code,
            'name': code.name,
            'specification': code.specification,
            'unit': code.unit,
            'formula': code.formula,
            'total_cost': float(code.total_cost),
            'display': f"{code.code} - {code.name} ({code.specification}, {code.unit})"
        })
    
    return JsonResponse({'results': results})

# dd_by_ifc/views.py (수정된 부분)

# views.py - IFC PropertySet 수정 로직 완전 개선

import ifcopenshell.util.element
import ifcopenshell.api

def update_ifc_cost_items_v2(ifc_model, ifc_entity, cost_items_value):
    """IFC 엔티티의 CostItems 속성을 업데이트하는 개선된 함수"""
    try:
        print(f"🔧 PropertySet 업데이트 시작: {ifc_entity.GlobalId} -> {cost_items_value}")
        
        # 현재 PropertySet 상태 확인
        current_psets = ifcopenshell.util.element.get_psets(ifc_entity)
        print(f"📋 현재 PropertySets: {list(current_psets.keys())}")
        
        # cnv_general PropertySet 찾기
        cnv_general_pset = None
        cnv_general_rel = None
        
        for rel in getattr(ifc_entity, 'IsDefinedBy', []) or []:
            if rel.is_a("IfcRelDefinesByProperties"):
                pset = rel.RelatingPropertyDefinition
                if hasattr(pset, 'Name') and pset.Name == "cnv_general":
                    cnv_general_pset = pset
                    cnv_general_rel = rel
                    break
        
        # PropertySet이 없으면 새로 생성
        if not cnv_general_pset:
            print("🆕 cnv_general PropertySet 생성")
            
            # ifcopenshell.api 사용하여 PropertySet 생성
            cnv_general_pset = ifcopenshell.api.run("pset.add_pset", ifc_model,
                product=ifc_entity,
                name="cnv_general"
            )
            print(f"✅ PropertySet 생성 완료: {cnv_general_pset}")
        
        # CostItems 속성 추가/수정
        try:
            # 기존 CostItems 속성이 있는지 확인
            has_cost_items = False
            if hasattr(cnv_general_pset, 'HasProperties') and cnv_general_pset.HasProperties:
                for prop in cnv_general_pset.HasProperties:
                    if hasattr(prop, 'Name') and prop.Name == "CostItems":
                        # 기존 속성 값 수정
                        if hasattr(prop, 'NominalValue'):
                            prop.NominalValue.wrappedValue = cost_items_value
                        else:
                            prop.NominalValue = ifc_model.create_entity("IfcText", cost_items_value)
                        has_cost_items = True
                        print(f"🔄 기존 CostItems 속성 수정: {cost_items_value}")
                        break
            
            # 속성이 없으면 새로 추가
            if not has_cost_items:
                print("🆕 CostItems 속성 새로 추가")
                ifcopenshell.api.run("pset.edit_pset", ifc_model,
                    pset=cnv_general_pset,
                    properties={"CostItems": cost_items_value}
                )
                print(f"✅ CostItems 속성 추가 완료: {cost_items_value}")
        
        except Exception as e:
            print(f"❌ CostItems 속성 처리 실패: {e}")
            # 대안: 직접 속성 생성
            try:
                cost_property = ifc_model.create_entity("IfcPropertySingleValue")
                cost_property.Name = "CostItems"
                cost_property.Description = None
                cost_property.NominalValue = ifc_model.create_entity("IfcText", cost_items_value)
                cost_property.Unit = None
                
                # PropertySet에 추가
                properties_list = list(getattr(cnv_general_pset, 'HasProperties', []) or [])
                properties_list.append(cost_property)
                cnv_general_pset.HasProperties = properties_list
                print(f"✅ 직접 속성 생성 완료: {cost_items_value}")
            except Exception as e2:
                print(f"❌ 직접 속성 생성도 실패: {e2}")
                return False
        
        # 업데이트 후 검증
        updated_psets = ifcopenshell.util.element.get_psets(ifc_entity)
        cost_items_check = updated_psets.get("cnv_general", {}).get("CostItems", "")
        print(f"🔍 업데이트 검증: {cost_items_check}")
        
        if cost_items_check == cost_items_value:
            print(f"✅ PropertySet 업데이트 성공: {cost_items_value}")
            return True
        else:
            print(f"❌ PropertySet 업데이트 실패: 예상={cost_items_value}, 실제={cost_items_check}")
            return False
        
    except Exception as e:
        print(f"❌ PropertySet 업데이트 전체 실패: {e}")
        import traceback
        traceback.print_exc()
        return False



@csrf_exempt
@require_http_methods(["POST"])
def add_cost_code_to_objects(request):
    object_ids = request.POST.getlist('object_ids[]')
    project_id = request.POST.get('project_id')  # ← 프로젝트 ID 추가
    cost_code = request.POST.get('cost_code')

    if not object_ids or not project_id or not cost_code:
        return JsonResponse({'error': '필수 파라미터가 누락되었습니다.'}, status=400)

    updated_count = 0
    with transaction.atomic():
        # 프로젝트 별로만 필터!
        objects = IFCObject.objects.filter(project_id=project_id, global_id__in=object_ids)
        for obj in objects:
            # CostItems(공사코드) 필드는 CSV 저장 (중복제거 및 정렬)
            codes = set([c.strip() for c in (obj.cost_items or "").split('+') if c.strip()])
            codes.add(cost_code)
            obj.cost_items = '+'.join(sorted(codes))
            obj.save()
            updated_count += 1

    return JsonResponse({
        'success': True,
        'message': f'{updated_count}개 객체에 공사코드가 추가되었습니다.',
        'updated_objects': updated_count
    })


@csrf_exempt
@require_http_methods(["POST"])
def remove_cost_code_from_objects(request):
    object_ids = request.POST.getlist('object_ids[]')
    project_id = request.POST.get('project_id')  # ← 프로젝트 ID 추가
    cost_code = request.POST.get('cost_code')

    if not object_ids or not project_id or not cost_code:
        return JsonResponse({'error': '필수 파라미터가 누락되었습니다.'}, status=400)

    updated_count = 0
    with transaction.atomic():
        # 프로젝트 별로만 필터!
        objects = IFCObject.objects.filter(project_id=project_id, global_id__in=object_ids)
        for obj in objects:
            codes = [c.strip() for c in (obj.cost_items or "").split('+') if c.strip()]
            codes = [c for c in codes if c != cost_code]
            obj.cost_items = '+'.join(sorted(set(codes)))
            obj.save()
            updated_count += 1

    return JsonResponse({
        'success': True,
        'message': f'{updated_count}개 객체에서 공사코드가 제거되었습니다.',
        'updated_objects': updated_count
    })


def update_ifc_cost_items(ifc_model, ifc_entity, cost_items_value):
    """IFC 엔티티의 CostItems 속성을 업데이트하는 헬퍼 함수"""
    try:
        # cnv_general PropertySet 찾기
        target_pset = None
        target_rel = None
        
        for rel in getattr(ifc_entity, 'IsDefinedBy', []) or []:
            if rel.is_a("IfcRelDefinesByProperties"):
                pset = rel.RelatingPropertyDefinition
                if (hasattr(pset, 'Name') and pset.Name == "cnv_general"):
                    target_pset = pset
                    target_rel = rel
                    break
        
        # PropertySet이 없으면 생성
        if not target_pset:
            print(f"🔧 cnv_general PropertySet 생성 중...")
            
            # IfcPropertySet 생성
            target_pset = ifc_model.create_entity("IfcPropertySet")
            target_pset.GlobalId = ifcopenshell.guid.new()
            target_pset.OwnerHistory = getattr(ifc_entity, 'OwnerHistory', None)
            target_pset.Name = "cnv_general"
            target_pset.Description = None
            target_pset.HasProperties = []
            
            # IfcRelDefinesByProperties 생성
            target_rel = ifc_model.create_entity("IfcRelDefinesByProperties")
            target_rel.GlobalId = ifcopenshell.guid.new()
            target_rel.OwnerHistory = getattr(ifc_entity, 'OwnerHistory', None)
            target_rel.Name = None
            target_rel.Description = None
            target_rel.RelatedObjects = [ifc_entity]
            target_rel.RelatingPropertyDefinition = target_pset
            
            print(f"✅ cnv_general PropertySet 생성 완료")
        
        # CostItems 속성 찾기 또는 생성
        cost_property = None
        properties_list = list(getattr(target_pset, 'HasProperties', []) or [])
        
        for prop in properties_list:
            if (hasattr(prop, 'Name') and prop.Name == "CostItems"):
                cost_property = prop
                break
        
        # CostItems 속성이 없으면 생성
        if not cost_property:
            print(f"🔧 CostItems 속성 생성 중...")
            
            cost_property = ifc_model.create_entity("IfcPropertySingleValue")
            cost_property.Name = "CostItems"
            cost_property.Description = None
            cost_property.NominalValue = ifc_model.create_entity("IfcText", cost_items_value)
            cost_property.Unit = None
            
            properties_list.append(cost_property)
            target_pset.HasProperties = properties_list
            
            print(f"✅ CostItems 속성 생성 완료: {cost_items_value}")
        else:
            # 기존 속성 값 업데이트
            if hasattr(cost_property, 'NominalValue') and cost_property.NominalValue:
                cost_property.NominalValue.wrappedValue = cost_items_value
            else:
                cost_property.NominalValue = ifc_model.create_entity("IfcText", cost_items_value)
            
            print(f"✅ CostItems 속성 업데이트 완료: {cost_items_value}")
        
        return True
        
    except Exception as e:
        print(f"❌ PropertySet 업데이트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


@csrf_exempt
@require_http_methods(["GET"])
def download_ifc_file(request, project_id):
    """수정된 IFC 파일 다운로드"""
    project = get_object_or_404(Project, id=project_id)
    
    if not project.ifc_file:
        return JsonResponse({'error': 'IFC 파일이 없습니다.'}, status=404)
    
    try:
        file_path = project.ifc_file.path
        
        if not os.path.exists(file_path):
            return JsonResponse({'error': 'IFC 파일을 찾을 수 없습니다.'}, status=404)
        
        # 파일 크기 확인
        file_size = os.path.getsize(file_path)
        if file_size < 1000:
            return JsonResponse({'error': 'IFC 파일이 손상되었을 수 있습니다.'}, status=500)
        
        # 파일 응답 생성
        with open(file_path, 'rb') as file:
            response = HttpResponse(file.read(), content_type='application/octet-stream')
            filename = f"{project.name}_updated.ifc"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            response['Content-Length'] = file_size
            return response
            
    except Exception as e:
        print(f"❌ 다운로드 실패: {e}")
        return JsonResponse({'error': f'파일 다운로드 실패: {str(e)}'}, status=500)
@csrf_exempt
@require_http_methods(["POST"])
def get_object_details(request):
    object_ids = request.POST.getlist('object_ids[]')
    project_id = request.POST.get('project_id')  # 추가

    if not object_ids or not project_id:
        return JsonResponse({'details': [], 'total_amount': 0})

    # **프로젝트 기준으로 필터링!**
    objects = IFCObject.objects.filter(
        project_id=project_id,
        global_id__in=object_ids
    )
    
    # 코드별 수량 합계 계산
    combined_codes = defaultdict(lambda: {
        'name': '',
        'specification': '',
        'unit': '',
        'formula': '',
        'unit_price': 0,
        'quantity': 0
    })
    
    total_amount = 0
    
    for obj in objects:
        codes = obj.get_cost_codes()
        
        # 수량 계산 컨텍스트 준비
        quantity_context = {**obj.quantities, **obj.properties}
        quantity_context.update({
            'GlobalId': obj.global_id,
            'Name': obj.name,
            'IfcClass': obj.ifc_class,
            'SpatialContainer': obj.spatial_container,
        })
        
        for code in codes:
            try:
                cost_code = CostCode.objects.get(code=code)
                
                if code not in combined_codes:
                    combined_codes[code].update({
                        'name': cost_code.name,
                        'specification': cost_code.specification,
                        'unit': cost_code.unit,
                        'formula': cost_code.formula,
                        'unit_price': float(cost_code.total_cost)
                    })
                
                # 수량 계산
                try:
                    quantity = eval(cost_code.formula, {"__builtins__": None}, quantity_context)
                except:
                    quantity = 0
                
                combined_codes[code]['quantity'] += quantity
                total_amount += quantity * float(cost_code.total_cost)
                
            except CostCode.DoesNotExist:
                continue
    
    # 결과 정리
    details = []
    for code, data in combined_codes.items():
        details.append({
            'code': code,
            'name': data['name'],
            'specification': data['specification'],
            'unit': data['unit'],
            'formula': data['formula'],
            'quantity': data['quantity'],
            'unit_price': data['unit_price'],
            'amount': data['quantity'] * data['unit_price']
        })
    
    return JsonResponse({
        'details': details,
        'total_amount': total_amount
    })

@csrf_exempt
@require_http_methods(["GET"])
def get_summary_table(request, project_id):
    """요약 테이블 데이터 반환"""
    project = get_object_or_404(Project, id=project_id)
    objects = IFCObject.objects.filter(project=project)
    
    # 코드별 그룹 합계 계산
    grouped = defaultdict(lambda: defaultdict(lambda: {
        'code': '',
        'category': '',
        'name': '',
        'specification': '',
        'unit': '',
        'quantity': 0.0,
        'material_unit': 0.0,
        'labor_unit': 0.0,
        'expense_unit': 0.0,
        'total_unit': 0.0,
        'material_amount': 0.0,
        'labor_amount': 0.0,
        'expense_amount': 0.0,
        'total_amount': 0.0
    }))
    
    total_sum = 0.0
    
    for obj in objects:
        codes = obj.get_cost_codes()
        
        # 수량 계산 컨텍스트
        quantity_context = {**obj.quantities, **obj.properties}
        quantity_context.update({
            'GlobalId': obj.global_id,
            'Name': obj.name,
            'IfcClass': obj.ifc_class,
            'SpatialContainer': obj.spatial_container,
        })
        
        for code in codes:
            try:
                cost_code = CostCode.objects.get(code=code)
                
                # 수량 계산
                try:
                    quantity = eval(cost_code.formula, {"__builtins__": None}, quantity_context)
                except:
                    quantity = 0.0
                
                mat_unit = float(cost_code.material_cost)
                lab_unit = float(cost_code.labor_cost)
                exp_unit = float(cost_code.expense_cost)
                total_unit = float(cost_code.total_cost)
                
                group = cost_code.category or "기타"
                item = grouped[group][code]
                
                item.update({
                    'code': code,
                    'category': group,
                    'name': cost_code.name,
                    'specification': cost_code.specification,
                    'unit': cost_code.unit,
                    'material_unit': mat_unit,
                    'labor_unit': lab_unit,
                    'expense_unit': exp_unit,
                    'total_unit': total_unit,
                })
                
                item['quantity'] += quantity
                item['material_amount'] += quantity * mat_unit
                item['labor_amount'] += quantity * lab_unit
                item['expense_amount'] += quantity * exp_unit
                item['total_amount'] += quantity * total_unit
                
                total_sum += quantity * total_unit
                
            except CostCode.DoesNotExist:
                continue
    
    # 결과 정리
    summary_data = []
    for group, codes in grouped.items():
        group_total = sum(item['total_amount'] for item in codes.values())
        
        # 그룹 헤더
        summary_data.append({
            'type': 'group',
            'group': group,
            'total': group_total
        })
        
        # 코드 항목들
        for code, item in sorted(codes.items()):
            summary_data.append({
                'type': 'item',
                **item
            })
    
    return JsonResponse({
        'summary_data': summary_data,
        'total_sum': total_sum
    })


@csrf_exempt
@require_http_methods(["POST"])
def load_cost_codes_from_csv(request):
    """CSV에서 공사코드 로드"""
    if 'csv_file' not in request.FILES:
        return JsonResponse({'error': 'CSV 파일이 없습니다.'}, status=400)
    
    csv_file = request.FILES['csv_file']
    
    try:
        # 기존 코드 삭제 (선택사항)
        # CostCode.objects.all().delete()
        
        decoded_file = csv_file.read().decode('utf-8-sig')
        reader = csv.DictReader(decoded_file.splitlines())
        
        # 헤더 정리
        fieldnames = [fn.strip() for fn in reader.fieldnames]
        
        created_count = 0
        for row in reader:
            code = row.get("코드", "").strip()
            if not code:
                continue
            
            def safe_float(val):
                try:
                    return float(val or 0)
                except:
                    return 0.0
            
            cost_code, created = CostCode.objects.get_or_create(
                code=code,
                defaults={
                    'category': row.get("공종", "").strip(),
                    'name': row.get("명칭", "").strip(),
                    'specification': row.get("규격", "").strip(),
                    'unit': row.get("단위", "").strip(),
                    'formula': row.get("산식", "").strip(),
                    'material_cost': safe_float(row.get("재료비단가")),
                    'labor_cost': safe_float(row.get("노무비단가")),
                    'expense_cost': safe_float(row.get("경비단가")),
                    'total_cost': safe_float(row.get("합계단가")),
                }
            )
            
            if created:
                created_count += 1
        
        return JsonResponse({
            'success': True,
            'message': f'{created_count}개의 새로운 공사코드가 로드되었습니다.',
            'total_codes': CostCode.objects.count()
        })
    
    except Exception as e:
        return JsonResponse({'error': f'CSV 처리 중 오류: {str(e)}'}, status=500)
        

def ifc_to_json(request, project_id):
    # 올바른 필드명 사용
    project = Project.objects.get(id=project_id)
    ifc_path = project.ifc_file.path     # ← 올바른 필드명 사용

    ifc_file = ifcopenshell.open(ifc_path)

    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    settings.set(settings.WELD_VERTICES, True)

    elements = ifc_file.by_type("IfcProduct")
    geometry_data = []

    for element in elements:
        try:
            shape = ifcopenshell.geom.create_shape(settings, element)
            vertices = shape.geometry.verts
            normals = shape.geometry.normals
            faces = shape.geometry.faces

            geometry_data.append({
                'GlobalId': element.GlobalId,
                'type': element.is_a(),
                'vertices': vertices,
                'normals': normals,
                'faces': faces,
            })

        except:
            continue

    return JsonResponse({'geometry_data': geometry_data})


# views.py에 추가할 디버깅용 함수들

@csrf_exempt
@require_http_methods(["GET"])
def debug_ifc_properties(request, project_id):
    """IFC 파일의 PropertySet 상태를 디버깅하는 API"""
    project = get_object_or_404(Project, id=project_id)
    
    if not project.ifc_file or not os.path.exists(project.ifc_file.path):
        return JsonResponse({'error': 'IFC 파일이 없습니다.'}, status=404)
    
    try:
        ifc_model = ifcopenshell.open(project.ifc_file.path)
        
        # 몇 개 객체만 샘플링
        sample_objects = []
        ifc_objects = ifc_model.by_type("IfcProduct")[:10]  # 처음 10개만
        
        for obj in ifc_objects:
            try:
                global_id = getattr(obj, "GlobalId", "")
                name = getattr(obj, "Name", "") or ""
                
                # PropertySet 정보 가져오기
                psets = ifcopenshell.util.element.get_psets(obj)
                
                # cnv_general PropertySet 특별히 확인
                cnv_general = psets.get("cnv_general", {})
                cost_items = cnv_general.get("CostItems", "")
                
                # 데이터베이스의 값과 비교
                try:
                    db_obj = IFCObject.objects.get(project=project, global_id=global_id)
                    db_cost_items = db_obj.cost_items
                except IFCObject.DoesNotExist:
                    db_cost_items = "DB에 없음"
                
                sample_objects.append({
                    'global_id': global_id,
                    'name': name,
                    'ifc_class': obj.is_a(),
                    'psets': list(psets.keys()),
                    'ifc_cost_items': cost_items,
                    'db_cost_items': db_cost_items,
                    'match': cost_items == db_cost_items,
                    'all_cnv_general': cnv_general
                })
                
            except Exception as e:
                sample_objects.append({
                    'global_id': getattr(obj, "GlobalId", "Unknown"),
                    'error': str(e)
                })
        
        # 전체 통계
        total_objects = len(ifc_objects)
        
        return JsonResponse({
            'success': True,
            'file_path': project.ifc_file.path,
            'file_size': os.path.getsize(project.ifc_file.path),
            'total_objects': total_objects,
            'sample_objects': sample_objects,
            'sample_count': len(sample_objects)
        })
        
    except Exception as e:
        return JsonResponse({'error': f'디버깅 실패: {str(e)}'}, status=500)


@csrf_exempt  
@require_http_methods(["POST"])
def force_update_single_object(request):
    """단일 객체의 PropertySet을 강제로 업데이트하는 테스트 API"""
    global_id = request.POST.get('global_id')
    cost_items = request.POST.get('cost_items', '')
    
    if not global_id:
        return JsonResponse({'error': 'global_id가 필요합니다.'}, status=400)
    
    try:
        # 데이터베이스에서 객체 찾기
        ifc_obj = IFCObject.objects.get(global_id=global_id)
        project = ifc_obj.project
        
        if not project.ifc_file or not os.path.exists(project.ifc_file.path):
            return JsonResponse({'error': 'IFC 파일이 없습니다.'}, status=404)
        
        # IFC 파일 열기
        ifc_model = ifcopenshell.open(project.ifc_file.path)
        ifc_entity = ifc_model.by_guid(global_id)
        
        # 업데이트 전 상태
        before_psets = ifcopenshell.util.element.get_psets(ifc_entity)
        before_cost_items = before_psets.get("cnv_general", {}).get("CostItems", "")
        
        print(f"🔍 업데이트 전: {before_cost_items}")
        
        # PropertySet 업데이트
        success = update_ifc_cost_items_v2(ifc_model, ifc_entity, cost_items)
        
        # 업데이트 후 상태 (메모리에서)
        after_psets = ifcopenshell.util.element.get_psets(ifc_entity)
        after_cost_items = after_psets.get("cnv_general", {}).get("CostItems", "")
        
        print(f"🔍 메모리 업데이트 후: {after_cost_items}")
        
        if success:
            # 임시 파일에 저장하여 테스트
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.ifc', delete=False) as tmp_file:
                temp_path = tmp_file.name
            
            try:
                ifc_model.write(temp_path)
                
                # 저장된 파일 다시 열어서 확인
                test_model = ifcopenshell.open(temp_path)
                test_entity = test_model.by_guid(global_id)
                saved_psets = ifcopenshell.util.element.get_psets(test_entity)
                saved_cost_items = saved_psets.get("cnv_general", {}).get("CostItems", "")
                
                print(f"🔍 파일 저장 후: {saved_cost_items}")
                
                # 임시 파일 삭제
                os.unlink(temp_path)
                
                return JsonResponse({
                    'success': True,
                    'global_id': global_id,
                    'before_cost_items': before_cost_items,
                    'after_cost_items': after_cost_items,
                    'saved_cost_items': saved_cost_items,
                    'memory_update_success': after_cost_items == cost_items,
                    'file_save_success': saved_cost_items == cost_items,
                    'before_psets': list(before_psets.keys()),
                    'after_psets': list(after_psets.keys()),
                    'saved_psets': list(saved_psets.keys())
                })
                
            except Exception as save_error:
                return JsonResponse({
                    'success': False,
                    'error': f'파일 저장 테스트 실패: {str(save_error)}',
                    'memory_update_success': after_cost_items == cost_items,
                    'before_cost_items': before_cost_items,
                    'after_cost_items': after_cost_items
                })
        else:
            return JsonResponse({
                'success': False,
                'error': 'PropertySet 업데이트 실패',
                'before_cost_items': before_cost_items,
                'after_cost_items': after_cost_items
            })
            
    except IFCObject.DoesNotExist:
        return JsonResponse({'error': '객체를 찾을 수 없습니다.'}, status=404)
    except Exception as e:
        print(f"❌ 단일 객체 업데이트 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)


# urls.py에 추가할 URL 패턴들
"""
# urls.py에 다음 URL들을 추가하세요:

path('api/debug_ifc/<int:project_id>/', views.debug_ifc_properties, name='debug_ifc_properties'),
path('api/test_update/', views.force_update_single_object, name='force_update_single_object'),
"""

# 프론트엔드에서 사용할 디버깅 스크립트
DEBUG_SCRIPT = """
// 브라우저 콘솔에서 실행할 디버깅 스크립트

// 1. IFC 파일 PropertySet 상태 확인
async function debugIFCProperties() {
    const response = await fetch(`/dd_by_ifc/api/debug_ifc/${PROJECT_ID}/`);
    const data = await response.json();
    console.log('🔍 IFC PropertySet 디버깅 결과:', data);
    
    if (data.success) {
        console.log(`📊 총 객체 수: ${data.total_objects}`);
        console.log(`📂 파일 크기: ${data.file_size} bytes`);
        
        data.sample_objects.forEach((obj, idx) => {
            if (obj.error) {
                console.log(`❌ 객체 ${idx}: ${obj.global_id} - ${obj.error}`);
            } else {
                const match = obj.match ? '✅' : '❌';
                console.log(`${match} 객체 ${idx}: ${obj.global_id}`);
                console.log(`   IFC: "${obj.ifc_cost_items}"`);
                console.log(`   DB:  "${obj.db_cost_items}"`);
                console.log(`   PropertySets: ${obj.psets.join(', ')}`);
            }
        });
    }
    
    return data;
}

// 2. 단일 객체 업데이트 테스트
async function testSingleUpdate(globalId, costItems) {
    const formData = new FormData();
    formData.append('global_id', globalId);
    formData.append('cost_items', costItems);
    
    const response = await fetch('/dd_by_ifc/api/test_update/', {
        method: 'POST',
        body: formData
    });
    
    const data = await response.json();
    console.log('🧪 단일 객체 업데이트 테스트:', data);
    
    return data;
}

// 사용법:
// debugIFCProperties(); // IFC 파일 상태 확인
// testSingleUpdate('1ABC_GLOBAL_ID_123', 'TEST01+TEST02'); // 단일 객체 테스트
"""


# views.py - 완전히 새로운 IFC 파일 생성 방식

import tempfile
import shutil
import time
from collections import defaultdict


def create_new_ifc_with_properties(project):
    """
    원본 IFC 파일을 기반으로 공사코드가 포함된 새로운 IFC 파일 생성 (수정된 버전)
    """
    try:
        print(f"🚀 새로운 IFC 파일 생성 시작: {project.name}")
        
        # 원본 IFC 파일 열기
        original_path = project.ifc_file.path
        original_model = ifcopenshell.open(original_path)
        
        # 엔티티 개수 확인 (수정된 방법)
        try:
            all_entities = list(original_model)
            print(f"📂 원본 파일 로드: {len(all_entities)} 엔티티")
        except:
            # 대안 방법
            products = original_model.by_type("IfcProduct")
            print(f"📂 원본 파일 로드: {len(products)} IfcProduct 엔티티")
        
        # 임시 파일 생성
        temp_dir = os.path.dirname(original_path)
        timestamp = int(time.time())
        new_filename = f"{project.name}_with_costcodes_{timestamp}.ifc"
        new_path = os.path.join(temp_dir, new_filename)
        
        # 원본 파일을 새 경로로 복사 (기본 구조 유지)
        shutil.copy2(original_path, new_path)
        print(f"📋 기본 구조 복사 완료: {new_path}")
        
        # 새 파일 열기
        new_model = ifcopenshell.open(new_path)
        
        # 데이터베이스에서 공사코드 정보 가져오기
        ifc_objects = IFCObject.objects.filter(project=project)
        cost_code_map = {}
        
        for obj in ifc_objects:
            if obj.cost_items.strip():
                cost_code_map[obj.global_id] = obj.cost_items.strip()
        
        print(f"💼 공사코드가 있는 객체: {len(cost_code_map)}개")
        
        # 모든 IfcProduct 객체에 대해 PropertySet 처리
        products = new_model.by_type("IfcProduct")
        updated_count = 0
        total_products = len(products)
        
        print(f"🔄 처리할 IfcProduct 객체: {total_products}개")
        
        for idx, product in enumerate(products):
            try:
                global_id = getattr(product, "GlobalId", "")
                if not global_id:
                    continue
                
                # 진행률 표시
                if idx % 100 == 0 or idx == total_products - 1:
                    progress = (idx + 1) / total_products * 100
                    print(f"📊 진행률: {idx + 1}/{total_products} ({progress:.1f}%)")
                
                # 이 객체의 공사코드 정보 가져오기
                cost_items = cost_code_map.get(global_id, "")
                
                # 기존 cnv_general PropertySet 모두 제거
                remove_existing_cnv_general(new_model, product)
                
                # 공사코드가 있으면 새로운 PropertySet 추가
                if cost_items:
                    success = add_clean_cnv_general(new_model, product, cost_items)
                    if success:
                        updated_count += 1
                        if updated_count <= 10:  # 처음 10개만 로그 출력
                            print(f"✅ {global_id}: {cost_items}")
                    else:
                        print(f"❌ {global_id}: PropertySet 추가 실패")
                
            except Exception as e:
                print(f"⚠️ 객체 {getattr(product, 'GlobalId', 'Unknown')} 처리 실패: {e}")
                continue
        
        print(f"🔄 PropertySet 업데이트 완료: {updated_count}/{total_products}")
        
        # 새 파일 저장
        print(f"💾 파일 저장 중...")
        new_model.write(new_path)
        
        # 저장된 파일 검증
        print(f"🔍 저장된 파일 검증 중...")
        verify_model = ifcopenshell.open(new_path)
        verify_products = verify_model.by_type("IfcProduct")
        
        # 몇 개 객체 샘플링하여 PropertySet 확인
        verification_success = 0
        verification_total = 0
        sample_size = min(10, len([gid for gid in cost_code_map.keys()]))  # 최대 10개 또는 전체 중 작은 수
        
        sampled_global_ids = list(cost_code_map.keys())[:sample_size]
        
        for product in verify_products:
            global_id = getattr(product, "GlobalId", "")
            if global_id in sampled_global_ids:
                expected_cost_items = cost_code_map[global_id]
                
                try:
                    psets = ifcopenshell.util.element.get_psets(product)
                    actual_cost_items = psets.get("cnv_general", {}).get("CostItems", "")
                    
                    verification_total += 1
                    if actual_cost_items == expected_cost_items:
                        verification_success += 1
                        print(f"✅ 검증 성공: {global_id} = {actual_cost_items}")
                    else:
                        print(f"❌ 검증 실패: {global_id} 예상={expected_cost_items}, 실제={actual_cost_items}")
                        
                except Exception as e:
                    print(f"⚠️ 검증 중 오류: {global_id} - {e}")
                    verification_total += 1
        
        verification_rate = (verification_success / verification_total * 100) if verification_total > 0 else 0
        print(f"🔍 검증 결과: {verification_success}/{verification_total} ({verification_rate:.1f}%)")
        
        # 파일 크기 확인
        new_file_size = os.path.getsize(new_path)
        original_file_size = os.path.getsize(original_path)
        size_ratio = new_file_size / original_file_size * 100
        
        print(f"📏 파일 크기: 원본={original_file_size:,} bytes, 새파일={new_file_size:,} bytes ({size_ratio:.1f}%)")
        
        if verification_rate >= 70 and size_ratio >= 50:  # 70% 이상 성공하고 파일크기도 50% 이상이면 OK
            message = f"새 IFC 파일 생성 완료 (검증률: {verification_rate:.1f}%, 크기: {size_ratio:.1f}%)"
            return new_path, message
        else:
            raise Exception(f"품질 검증 실패 - 검증률: {verification_rate:.1f}%, 크기비율: {size_ratio:.1f}%")
        
    except Exception as e:
        print(f"❌ 새 IFC 파일 생성 실패: {e}")
        import traceback
        traceback.print_exc()
        raise


def remove_existing_cnv_general(ifc_model, ifc_entity):
    """기존 cnv_general PropertySet 완전 제거 (수정된 버전)"""
    try:
        rels_to_process = []
        
        # IsDefinedBy 관계에서 cnv_general PropertySet 찾기
        is_defined_by = getattr(ifc_entity, 'IsDefinedBy', None)
        if not is_defined_by:
            return True  # 관계가 없으면 성공으로 간주
        
        for rel in is_defined_by:
            try:
                if rel.is_a("IfcRelDefinesByProperties"):
                    pset = rel.RelatingPropertyDefinition
                    if hasattr(pset, 'Name') and pset.Name == "cnv_general":
                        rels_to_process.append((rel, pset))
            except Exception as e:
                print(f"⚠️ 관계 확인 중 오류: {e}")
                continue
        
        # 찾은 관계들 처리
        for rel, pset in rels_to_process:
            try:
                # 관계에서 이 엔티티 제거
                related_objects = list(rel.RelatedObjects) if rel.RelatedObjects else []
                if ifc_entity in related_objects:
                    related_objects.remove(ifc_entity)
                
                if len(related_objects) == 0:
                    # 다른 객체가 참조하지 않으면 PropertySet과 관계 모두 삭제
                    try:
                        if hasattr(pset, 'HasProperties') and pset.HasProperties:
                            for prop in pset.HasProperties:
                                ifc_model.remove(prop)
                        ifc_model.remove(pset)
                        ifc_model.remove(rel)
                    except Exception as e:
                        print(f"⚠️ PropertySet 삭제 중 오류: {e}")
                else:
                    # 다른 객체가 참조하면 관계만 업데이트
                    rel.RelatedObjects = related_objects
                    
            except Exception as e:
                print(f"⚠️ PropertySet 제거 중 오류: {e}")
                continue
                
        return True
        
    except Exception as e:
        print(f"❌ cnv_general PropertySet 제거 실패: {e}")
        return False


def add_clean_cnv_general(ifc_model, ifc_entity, cost_items_value):
    """완전히 새로운 cnv_general PropertySet 추가 (수정된 버전)"""
    try:
        # 1. PropertySet 생성
        pset = ifc_model.create_entity("IfcPropertySet")
        pset.GlobalId = ifcopenshell.guid.new()
        
        # OwnerHistory 안전하게 가져오기
        try:
            pset.OwnerHistory = getattr(ifc_entity, 'OwnerHistory', None)
        except:
            pset.OwnerHistory = None
            
        pset.Name = "cnv_general"
        pset.Description = "Cost estimation properties"
        
        # 2. CostItems 속성 생성
        cost_property = ifc_model.create_entity("IfcPropertySingleValue")
        cost_property.Name = "CostItems"
        cost_property.Description = "Cost item codes separated by +"
        cost_property.NominalValue = ifc_model.create_entity("IfcText", cost_items_value)
        cost_property.Unit = None
        
        # 3. PropertySet에 속성 연결
        pset.HasProperties = [cost_property]
        
        # 4. 관계 생성
        rel = ifc_model.create_entity("IfcRelDefinesByProperties")
        rel.GlobalId = ifcopenshell.guid.new()
        
        # OwnerHistory 안전하게 가져오기
        try:
            rel.OwnerHistory = getattr(ifc_entity, 'OwnerHistory', None)
        except:
            rel.OwnerHistory = None
            
        rel.Name = "CostItemsRelation"
        rel.Description = None
        rel.RelatedObjects = [ifc_entity]
        rel.RelatingPropertyDefinition = pset
        
        return True
        
    except Exception as e:
        print(f"❌ cnv_general PropertySet 추가 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


@csrf_exempt
@require_http_methods(["GET"])
def download_new_ifc_file(request, project_id):
    """새로운 IFC 파일 생성 후 다운로드 (수정된 버전)"""
    project = get_object_or_404(Project, id=project_id)
    
    if not project.ifc_file:
        return JsonResponse({'error': 'IFC 파일이 없습니다.'}, status=404)
    
    if not os.path.exists(project.ifc_file.path):
        return JsonResponse({'error': 'IFC 파일을 찾을 수 없습니다.'}, status=404)
    
    try:
        print(f"🎯 새 IFC 파일 다운로드 요청: {project.name}")
        
        # 새로운 IFC 파일 생성
        new_file_path, message = create_new_ifc_with_properties(project)
        
        print(f"✅ {message}")
        
        # 파일 응답 생성
        if os.path.exists(new_file_path):
            file_size = os.path.getsize(new_file_path)
            
            # 파일명 안전하게 처리
            safe_project_name = "".join(c for c in project.name if c.isalnum() or c in (' ', '-', '_')).rstrip()
            filename = f"{safe_project_name}_with_costcodes.ifc"
            
            with open(new_file_path, 'rb') as file:
                response = HttpResponse(file.read(), content_type='application/octet-stream')
                response['Content-Disposition'] = f'attachment; filename="{filename}"'
                response['Content-Length'] = file_size
                
                # 임시 파일 정리
                try:
                    os.remove(new_file_path)
                    print(f"🗑️ 임시 파일 삭제: {new_file_path}")
                except Exception as cleanup_error:
                    print(f"⚠️ 임시 파일 삭제 실패: {cleanup_error}")
                
                return response
        else:
            return JsonResponse({'error': '생성된 파일을 찾을 수 없습니다.'}, status=404)
            
    except Exception as e:
        print(f"❌ 새 IFC 파일 생성/다운로드 실패: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': f'새 IFC 파일 생성 실패: {str(e)}'}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def add_cost_code_to_objects_simple(request):
    object_id = request.POST.get('object_id')
    project_id = request.POST.get('project_id')  # 반드시 추가!
    cost_code = request.POST.get('cost_code')

    if not object_id or not project_id or not cost_code:
        return JsonResponse({'error': '필수 파라미터가 누락되었습니다.'}, status=400)

    try:
        obj = IFCObject.objects.get(project_id=project_id, global_id=object_id)
        codes = set([c.strip() for c in (obj.cost_items or "").split('+') if c.strip()])
        codes.add(cost_code)
        obj.cost_items = '+'.join(sorted(codes))
        obj.save()
        return JsonResponse({'success': True, 'message': f'공사코드가 추가되었습니다.'})
    except IFCObject.DoesNotExist:
        return JsonResponse({'error': '해당 객체를 찾을 수 없습니다.'}, status=404)


@csrf_exempt
@require_http_methods(["POST"])
def remove_cost_code_from_objects_simple(request):
    object_id = request.POST.get('object_id')
    project_id = request.POST.get('project_id')  # 반드시 추가!
    cost_code = request.POST.get('cost_code')

    if not object_id or not project_id or not cost_code:
        return JsonResponse({'error': '필수 파라미터가 누락되었습니다.'}, status=400)


    try:
        obj = IFCObject.objects.get(project_id=project_id, global_id=object_id)
        codes = [c.strip() for c in (obj.cost_items or "").split('+') if c.strip()]
        codes = [c for c in codes if c != cost_code]
        obj.cost_items = '+'.join(sorted(set(codes)))
        obj.save()
        return JsonResponse({'success': True, 'message': f'공사코드가 제거되었습니다.'})
    except IFCObject.DoesNotExist:
        return JsonResponse({'error': '해당 객체를 찾을 수 없습니다.'}, status=404)
