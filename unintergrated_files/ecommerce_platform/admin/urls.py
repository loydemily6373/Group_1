from django.urls import path
from . import views

urlpatterns = [
    # for product requests page
    path('admin-product-requests/', views.product_requests, name='product_requests'),
    path('approve-product/<int:product_id>/', views.approve_product, name='approve_product'),
    path('reject-product/<int:product_id>/', views.reject_product, name='reject_product'),

    # for seller requests page
    path('admin-seller-requests/', views.seller_requests, name='seller_requests'),
    path('approve-seller/<int:request_id>/', views.approve_seller, name='approve_seller'),
    path('reject-seller/<int:request_id>/', views.reject_seller, name='reject_seller'),
]