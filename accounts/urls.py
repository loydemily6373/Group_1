from django.urls import path
from .views import RegisterView, BuyerView, SellerView, AdminView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [

    path('register/', RegisterView.as_view()),
    path('login/', TokenObtainPairView.as_view()),
    path('refresh/', TokenRefreshView.as_view()),

    path('buyer/', BuyerView.as_view()),
    path('seller/', SellerView.as_view()),
    path('admin/', AdminView.as_view()),
    
]