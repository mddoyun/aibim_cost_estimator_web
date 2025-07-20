#ai_learning/views.py
from django.shortcuts import render

# Create your views here.
def go_ai_learning(request):
    return render(request, "ai_learning.html")