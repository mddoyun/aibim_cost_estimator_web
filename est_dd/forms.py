from django import forms

class UploadIFCForm(forms.Form):
    file = forms.FileField()
