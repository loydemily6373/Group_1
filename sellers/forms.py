from django import forms
from .models import Product


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        # Seller-controlled fields only. Approval and lifecycle fields are managed in the view/admin flow.
        fields = [
            'image',
            'product_name',
            'category',
            'price',
            'stock',
            'description',
        ]
        widgets = {
            'image': forms.ClearableFileInput(attrs={'accept': 'image/png,image/jpeg'}),
        }


class DiscountForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['discount_percent', 'discount_start_date', 'discount_end_date']
        widgets = {
            'discount_percent': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': 'Discount %',
                'min': '0',
                'max': '100',
                'step': '0.01',
            }),
            'discount_start_date': forms.DateTimeInput(attrs={
                'class': 'form-input',
                'type': 'datetime-local',
            }),
            'discount_end_date': forms.DateTimeInput(attrs={
                'class': 'form-input',
                'type': 'datetime-local',
            }),
        }
        labels = {
            'discount_percent': 'Discount Percentage (%)',
            'discount_start_date': 'Start Date & Time',
            'discount_end_date': 'End Date & Time',
        }

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('discount_start_date')
        end = cleaned_data.get('discount_end_date')
        if start and end and end <= start:
            raise forms.ValidationError('End date must be after the start date.')
        return cleaned_data