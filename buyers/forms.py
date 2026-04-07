from django import forms

from .models import BuyerShippingAddress, PaymentMethod, SellerShippingAddress


class BuyerShippingAddressForm(forms.ModelForm):
    class Meta:
        model = BuyerShippingAddress
        fields = [
            'label',
            'recipient_name',
            'address_line_1',
            'address_line_2',
            'city',
            'state',
            'postal_code',
            'country',
            'phone_number',
        ]


class PaymentMethodForm(forms.Form):
    # Collect the full card number so the saved payment record can keep the full test value and last four digits.
    label = forms.CharField(max_length=100)
    cardholder_name = forms.CharField(max_length=150)
    card_brand = forms.ChoiceField(choices=PaymentMethod.CARD_BRAND_CHOICES)
    card_number = forms.CharField(min_length=12, max_length=19)
    expiry_month = forms.IntegerField(min_value=1, max_value=12)
    expiry_year = forms.IntegerField(min_value=2025, max_value=2100)

    def clean_card_number(self):
        card_number = ''.join(character for character in self.cleaned_data['card_number'] if character.isdigit())
        if len(card_number) < 12:
            raise forms.ValidationError('Enter a valid card number.')
        return card_number


class SellerShippingAddressForm(forms.ModelForm):
    class Meta:
        model = SellerShippingAddress
        fields = [
            'label',
            'recipient_name',
            'address_line_1',
            'address_line_2',
            'city',
            'state',
            'postal_code',
            'country',
            'phone_number',
        ]
