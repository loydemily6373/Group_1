from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
import re

from admin.models import SellerApprovalRequest
from buyers.models import SellerShippingAddress

from .models import User

class RegisterSerializer(serializers.ModelSerializer):
    # Keep the password write-only so it is never returned in API responses.
    password = serializers.CharField(write_only=True)
    # Limit self-service registration to buyer and seller accounts only.
    role = serializers.ChoiceField(choices=[('buyer', 'Buyer'), ('seller', 'Seller')])
    seller_address_label = serializers.CharField(write_only=True, required=False, allow_blank=False)
    seller_recipient_name = serializers.CharField(write_only=True, required=False, allow_blank=False)
    seller_address_line_1 = serializers.CharField(write_only=True, required=False, allow_blank=False)
    seller_address_line_2 = serializers.CharField(write_only=True, required=False, allow_blank=True)
    seller_city = serializers.CharField(write_only=True, required=False, allow_blank=False)
    seller_state = serializers.CharField(write_only=True, required=False, allow_blank=False)
    seller_postal_code = serializers.CharField(write_only=True, required=False, allow_blank=False)
    seller_country = serializers.CharField(write_only=True, required=False, allow_blank=False)
    seller_phone_number = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        # These fields match the signup form so the browser and API stay in sync.
        fields = [
            'username',
            'password',
            'first_name',
            'last_name',
            'email',
            'role',
            'seller_address_label',
            'seller_recipient_name',
            'seller_address_line_1',
            'seller_address_line_2',
            'seller_city',
            'seller_state',
            'seller_postal_code',
            'seller_country',
            'seller_phone_number',
        ]

    def validate(self, attrs):
        password = attrs.get('password', '')
        password_errors = []

        if len(password) < 8:
            password_errors.append('Password must be at least 8 characters long.')
        if not re.search(r'[A-Z]', password):
            password_errors.append('Password must contain at least one capital letter.')
        if not re.search(r'\d', password):
            password_errors.append('Password must contain at least one number.')
        if password_errors:
            raise serializers.ValidationError({'password': password_errors})

        if attrs.get('role') != 'seller':
            return attrs

        required_fields = [
            'seller_address_label',
            'seller_recipient_name',
            'seller_address_line_1',
            'seller_city',
            'seller_state',
            'seller_postal_code',
            'seller_country',
        ]
        missing_fields = {
            field: 'This field is required for seller accounts.'
            for field in required_fields
            if not attrs.get(field)
        }
        if missing_fields:
            raise serializers.ValidationError(missing_fields)

        return attrs

    def create(self, validated_data):
        seller_address_data = {
            'label': validated_data.pop('seller_address_label', ''),
            'recipient_name': validated_data.pop('seller_recipient_name', ''),
            'address_line_1': validated_data.pop('seller_address_line_1', ''),
            'address_line_2': validated_data.pop('seller_address_line_2', ''),
            'city': validated_data.pop('seller_city', ''),
            'state': validated_data.pop('seller_state', ''),
            'postal_code': validated_data.pop('seller_postal_code', ''),
            'country': validated_data.pop('seller_country', ''),
            'phone_number': validated_data.pop('seller_phone_number', ''),
        }

        # Use Django's create_user helper so the password is hashed correctly.
        user = User.objects.create_user(
            username=validated_data['username'],
            password=validated_data['password'],
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            email=validated_data['email'],
            role=validated_data['role'],
        )

        # Seller accounts require admin approval before they can log in and access seller pages.
        if user.role == 'seller':
            user.is_active = False
            user.save(update_fields=['is_active'])
            SellerShippingAddress.objects.create(
                seller=user,
                is_default=True,
                **seller_address_data,
            )
            SellerApprovalRequest.submit_user(user)

        return user


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        # Add the role to the token so later protected pages can read it if needed.
        token = super().get_token(user)
        token['role'] = user.role
        return token

    def validate(self, attrs):
        # Give pending seller accounts a clearer message than the generic invalid-credentials response.
        username = attrs.get(self.username_field)
        pending_seller = User.objects.filter(username=username, role='seller', is_active=False).first()
        if pending_seller is not None:
            raise AuthenticationFailed('Your seller account is waiting for admin approval before you can log in.')

        # Keep the normal access/refresh response and append role metadata for redirects.
        data = super().validate(attrs)
        data['role'] = self.user.role
        data['username'] = self.user.username
        return data