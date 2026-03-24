from django import forms
from .models import Product


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        # Seller-controlled fields only. Approval and lifecycle fields are managed in the view/admin flow.
        fields = [
            'product_name',
            'category',
            'price',
            'stock',
            'description',
        ]