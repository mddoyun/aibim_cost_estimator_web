from django.shortcuts import render
from .forms import UploadIFCForm
from .models import UploadedIFC
import ifcopenshell

def upload_ifc(request):
    if request.method == 'POST':
        form = UploadIFCForm(request.POST, request.FILES)
        if form.is_valid():
            # 파일 저장
            uploaded_file = request.FILES['file']
            uploaded_ifc = UploadedIFC.objects.create(file=uploaded_file)
            # 저장된 파일의 경로
            file_path = uploaded_ifc.file.path
            # IFC 파일 읽기
            ifc_model = ifcopenshell.open(file_path)
            # 예시: 벽 객체 추출
            walls = ifc_model.by_type("IfcWall")
            wall_count = len(walls)
            return render(request, 'upload.html', {'wall_count': wall_count})
    else:
        form = UploadIFCForm()
    return render(request, 'upload.html', {'form': form})
