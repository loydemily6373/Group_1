from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import LoginTokenView, RegisterView

urlpatterns = [
    # Keep account API routes separate from page routes so they never override each other.
    path('register/', RegisterView.as_view(), name='account_register_api'),
    path('token/', LoginTokenView.as_view(), name='account_token_api'),
    path('token/refresh/', TokenRefreshView.as_view(), name='account_token_refresh_api'),
]
