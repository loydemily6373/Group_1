from sellers.forms import *

from sellers.forms import *
from django import forms
from .models import Product


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = '__all__'
        widgets = {
            'discount_start_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'discount_end_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }
