from django.shortcuts import render

# Create your views here.

def go_sd_by_ifc(request):
  if request.method == 'POST':
    return render(request, 'sd_by_ifc.html')
  

  return render(request, 'sd_by_ifc.html')

def go_sd_by_ifc_result(request, project_id):
  return render(request, 'sd_by_ifc_result.html')
