from django.shortcuts import render, redirect
from sd_by_input.models import InputData, OutputData
import csv
import os
from django.conf import settings

# Create your views here.
def go_sd_by_input(request):
    if request.method == "POST":
        # POST 요청에서 데이터를 처리합니다.
        project_name = request.POST["project_name"]
        total_room_count = request.POST["total_room_count"]
        total_area = request.POST["total_area"]
        ground_level = request.POST["ground_level"]
        basement_level = request.POST["basement_level"]
        site_area = request.POST["site_area"]
        budget = request.POST["budget"]
        inputValues=InputData.objects.create(
            project_name=project_name,
            total_room_count=total_room_count,
            total_area=total_area,
            ground_level=ground_level,
            basement_level=basement_level,
            site_area=site_area,
            budget=budget
        )
        return redirect(f"/sd_by_input_result/{inputValues.id}")  # 결과 페이지로 리다이렉트합니다.
    return render(request,"sd_by_input.html")

def go_sd_by_input_result(request, inputValuesId):
    inputData = InputData.objects.get(id=inputValuesId)
    print(inputData.total_area)
    
    csv_path = os.path.join(settings.BASE_DIR, 'static', 'references', 'Rawdata_Col.csv')  
    print(csv_path)

    data = []
    columns = []
    # CSV 파일 로드
    with open(csv_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        columns = reader.fieldnames
        for row in reader:
            data.append(row)




    context = {
        "inputData": inputData,
        'columns': columns,
        'data': data,
    }



    return render(request,"sd_by_input_result.html",context)



