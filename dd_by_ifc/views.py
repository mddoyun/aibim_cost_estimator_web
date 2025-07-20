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
def go_dd_by_ifc(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        use = request.POST.get('use')
        ifc_file = request.FILES['ifc_file']

        project = Project.objects.create(name=name, use=use, ifc_file=ifc_file)
        ifc_path = project.ifc_file.path

        try:
            # 변환: IFC → OBJ
            obj_filename = os.path.splitext(os.path.basename(ifc_path))[0] + '.obj'
            obj_path = os.path.join(os.path.dirname(ifc_path), obj_filename)
            
            print(f"🔄 IFC 파일 경로: {ifc_path}")
            print(f"🎯 OBJ 저장 경로: {obj_path}")
            
            # 변환 실행
            convert_ifc_to_obj(ifc_path, obj_path)

            # OBJ 파일이 실제로 생성되었는지 확인
            if os.path.exists(obj_path):
                print(f"✅ OBJ 파일 생성 확인: {obj_path}")
                print(f"📏 OBJ 파일 크기: {os.path.getsize(obj_path)} bytes")
                
                # OBJ 파일을 FileField에 저장
                with open(obj_path, 'rb') as f:
                    # upload_to가 이미 'converted_objs/'로 설정되어 있으므로 파일명만 전달
                    project.converted_obj.save(obj_filename, File(f), save=True)
                
                print(f"✅ OBJ 파일 DB 저장 완료")
                print(f"📁 저장된 경로: {project.converted_obj.path}")
                print(f"🌐 URL: {project.converted_obj.url}")
                
                # 원본 OBJ 파일 삭제 (중복 방지)
                if os.path.exists(obj_path) and obj_path != project.converted_obj.path:
                    os.remove(obj_path)
            else:
                print(f"❌ OBJ 파일이 생성되지 않았습니다: {obj_path}")
                
        except Exception as e:
            print(f"❌ OBJ 변환 중 오류: {e}")
            import traceback
            traceback.print_exc()

        # IFC 객체 처리
        process_ifc_objects(project)

        return redirect('go_dd_by_ifc_result', project_id=project.id)

    return render(request, 'dd_by_ifc.html')

def go_dd_by_ifc_result(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    # 브라우저에서 직접 fetch 할 수 있도록 절대 URL 생성
    ifc_abs_url = request.build_absolute_uri(project.ifc_file.url) if project.ifc_file else ""
    return render(
        request,
        'dd_by_ifc_result.html',
        {
            'project': project,
            'ifc_abs_url': ifc_abs_url,
        }
    )

# API 엔드포인트들

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

@csrf_exempt
@require_http_methods(["POST"])
def add_cost_code_to_objects(request):
    """선택된 객체들에 공사코드 추가"""
    object_ids = request.POST.getlist('object_ids[]')
    cost_code = request.POST.get('cost_code')
    
    if not object_ids or not cost_code:
        return JsonResponse({'error': '필수 파라미터가 누락되었습니다.'}, status=400)
    
    try:
        # 공사코드가 존재하는지 확인
        CostCode.objects.get(code=cost_code)
        
        # IFC 파일과 모델 정보 가져오기
        project = None
        ifc_model = None
        
        # 객체들에 코드 추가 (데이터베이스)
        objects = IFCObject.objects.filter(global_id__in=object_ids)
        updated_count = 0
        
        for obj in objects:
            # 첫 번째 객체에서 프로젝트 정보 가져오기
            if not project:
                project = obj.project
        
        # IFC 파일에 직접 저장
        if project and project.ifc_file:
            try:
                ifc_model = ifcopenshell.open(project.ifc_file.path)
                
                for obj in objects:
                    try:
                        # GlobalId로 IFC 객체 찾기
                        ifc_entity = ifc_model.by_guid(obj.global_id)
                        
                        # 기존 CostItems 속성 가져오기 (cnv_general PropertySet에서)
                        psets = ifcopenshell.util.element.get_psets(ifc_entity)
                        current_cost_items = psets.get("cnv_general", {}).get("CostItems", "")
                        
                        # 새로운 코드 추가 (+ 구분자)
                        existing_codes = set([c.strip() for c in current_cost_items.split("+") if c.strip()])
                        existing_codes.add(cost_code)
                        new_cost_items = "+".join(sorted(existing_codes))
                        
                        # cnv_general PropertySet 찾기
                        target_pset = None
                        target_rel = None
                        target_pset_name = "cnv_general"
                        
                        for rel in ifc_entity.IsDefinedBy or []:
                            if rel.is_a("IfcRelDefinesByProperties"):
                                pset = rel.RelatingPropertyDefinition
                                if hasattr(pset, 'Name') and pset.Name == target_pset_name:
                                    target_pset = pset
                                    target_rel = rel
                                    break
                        
                        # cnv_general PropertySet이 없으면 생성
                        if not target_pset:
                            # IfcPropertySet 생성
                            target_pset = ifc_model.create_entity("IfcPropertySet")
                            target_pset.GlobalId = ifcopenshell.guid.new()
                            target_pset.OwnerHistory = ifc_entity.OwnerHistory
                            target_pset.Name = target_pset_name
                            target_pset.Description = None
                            target_pset.HasProperties = []
                            
                            # IfcRelDefinesByProperties 생성
                            target_rel = ifc_model.create_entity("IfcRelDefinesByProperties")
                            target_rel.GlobalId = ifcopenshell.guid.new()
                            target_rel.OwnerHistory = ifc_entity.OwnerHistory
                            target_rel.Name = None
                            target_rel.Description = None
                            target_rel.RelatedObjects = [ifc_entity]
                            target_rel.RelatingPropertyDefinition = target_pset
                        
                        # CostItems 속성 찾기
                        cost_property = None
                        properties_list = list(target_pset.HasProperties) if target_pset.HasProperties else []
                        
                        for prop in properties_list:
                            if hasattr(prop, 'Name') and prop.Name == "CostItems":
                                cost_property = prop
                                break
                        
                        # CostItems 속성이 없으면 생성
                        if not cost_property:
                            # IfcPropertySingleValue 생성
                            cost_property = ifc_model.create_entity("IfcPropertySingleValue")
                            cost_property.Name = "CostItems"
                            cost_property.Description = None
                            cost_property.NominalValue = ifc_model.create_entity("IfcText", new_cost_items)
                            cost_property.Unit = None
                            
                            # PropertySet에 추가
                            properties_list.append(cost_property)
                            target_pset.HasProperties = properties_list
                        else:
                            # 기존 속성 값 업데이트
                            cost_property.NominalValue = ifc_model.create_entity("IfcText", new_cost_items)
                        
                        # 데이터베이스도 업데이트
                        obj.cost_items = new_cost_items
                        obj.save()
                        obj.calculate_total_amount()
                        updated_count += 1
                        
                        print(f"✅ IFC 객체 {obj.global_id} CostItems 업데이트 성공: {new_cost_items}")
                        
                    except Exception as e:
                        print(f"❌ IFC 객체 {obj.global_id} 업데이트 실패: {e}")
                        import traceback
                        traceback.print_exc()
                        continue
                
                # 수정된 IFC 파일 저장
                ifc_model.write(project.ifc_file.path)
                print(f"✅ IFC 파일 저장 완료: {project.ifc_file.path}")
                
            except Exception as e:
                print(f"❌ IFC 파일 업데이트 실패: {e}")
                import traceback
                traceback.print_exc()
                return JsonResponse({'error': f'IFC 파일 업데이트 실패: {str(e)}'}, status=500)
        
        return JsonResponse({
            'success': True, 
            'message': f'{updated_count}개 객체에 코드가 추가되었습니다.',
            'updated_objects': updated_count
        })
    
    except CostCode.DoesNotExist:
        return JsonResponse({'error': '존재하지 않는 공사코드입니다.'}, status=400)
    except Exception as e:
        print(f"❌ 전체 프로세스 실패: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def remove_cost_code_from_objects(request):
    """선택된 객체들에서 공사코드 제거"""
    object_ids = request.POST.getlist('object_ids[]')
    cost_code = request.POST.get('cost_code')
    
    if not object_ids or not cost_code:
        return JsonResponse({'error': '필수 파라미터가 누락되었습니다.'}, status=400)
    
    try:
        project = None
        ifc_model = None
        updated_count = 0
        
        # 첫 번째 객체에서 프로젝트 정보 가져오기
        first_obj = IFCObject.objects.filter(global_id__in=object_ids).first()
        if first_obj:
            project = first_obj.project
        
        # IFC 파일에서 제거
        if project and project.ifc_file:
            try:
                ifc_model = ifcopenshell.open(project.ifc_file.path)
                
                objects = IFCObject.objects.filter(global_id__in=object_ids)
                for obj in objects:
                    try:
                        ifc_entity = ifc_model.by_guid(obj.global_id)
                        
                        # 기존 CostItems 속성 가져오기 (cnv_general PropertySet에서)
                        psets = ifcopenshell.util.element.get_psets(ifc_entity)
                        current_cost_items = psets.get("cnv_general", {}).get("CostItems", "")
                        target_pset = None
                        
                        # cnv_general PropertySet 찾기
                        for rel in ifc_entity.IsDefinedBy or []:
                            if rel.is_a("IfcRelDefinesByProperties"):
                                pset = rel.RelatingPropertyDefinition
                                if hasattr(pset, 'Name') and pset.Name == "cnv_general":
                                    target_pset = pset
                                    break
                        
                        if target_pset:
                            # 코드 제거 (+ 구분자)
                            existing_codes = set([c.strip() for c in current_cost_items.split("+") if c.strip()])
                            existing_codes.discard(cost_code)
                            new_cost_items = "+".join(sorted(existing_codes))
                            
                            # CostItems 속성 찾기 및 업데이트
                            if hasattr(target_pset, 'HasProperties') and target_pset.HasProperties:
                                for prop in target_pset.HasProperties:
                                    if hasattr(prop, 'Name') and prop.Name == "CostItems":
                                        prop.NominalValue = ifc_model.create_entity("IfcText", new_cost_items)
                                        break
                            
                            # 데이터베이스도 업데이트
                            obj.cost_items = new_cost_items
                            obj.save()
                            obj.calculate_total_amount()
                            updated_count += 1
                            
                            print(f"✅ IFC 객체 {obj.global_id} CostItems 코드 제거 성공: {new_cost_items}")
                        
                    except Exception as e:
                        print(f"❌ IFC 객체 {obj.global_id} 업데이트 실패: {e}")
                        import traceback
                        traceback.print_exc()
                        continue
                
                # 수정된 IFC 파일 저장
                ifc_model.write(project.ifc_file.path)
                print(f"✅ IFC 파일 저장 완료: {project.ifc_file.path}")
                
            except Exception as e:
                print(f"❌ IFC 파일 업데이트 실패: {e}")
                import traceback
                traceback.print_exc()
                return JsonResponse({'error': f'IFC 파일 업데이트 실패: {str(e)}'}, status=500)
        
        return JsonResponse({
            'success': True, 
            'message': f'{updated_count}개 객체에서 코드가 제거되었습니다.',
            'updated_objects': updated_count
        })
    
    except Exception as e:
        print(f"❌ 전체 프로세스 실패: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["GET"])
def download_ifc_file(request, project_id):
    """수정된 IFC 파일 다운로드"""
    project = get_object_or_404(Project, id=project_id)
    
    if not project.ifc_file:
        return JsonResponse({'error': 'IFC 파일이 없습니다.'}, status=404)
    
    try:
        # 파일 경로
        file_path = project.ifc_file.path
        
        # 파일이 존재하는지 확인
        if not os.path.exists(file_path):
            return JsonResponse({'error': 'IFC 파일을 찾을 수 없습니다.'}, status=404)
        
        # 파일 응답 생성
        with open(file_path, 'rb') as file:
            response = HttpResponse(file.read(), content_type='application/octet-stream')
            filename = f"{project.name}_updated.ifc"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
            
    except Exception as e:
        return JsonResponse({'error': f'파일 다운로드 실패: {str(e)}'}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def get_object_details(request):
    """선택된 객체들의 상세 정보 반환"""
    object_ids = request.POST.getlist('object_ids[]')
    
    if not object_ids:
        return JsonResponse({'details': [], 'total_amount': 0})
    
    objects = IFCObject.objects.filter(global_id__in=object_ids)
    
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
