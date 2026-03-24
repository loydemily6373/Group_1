from django.urls import path
from . import views

urlpatterns = [
    path('', views.seller_home, name='seller_home'),
    path('products/', views.product_list, name='product_list'),
    path('products/create/', views.product_creation, name='product_creation'),
    path('products/edit/<int:id>/', views.product_edit, name='product_edit'),
    path('products/delete/<int:id>/', views.product_delete, name='product_delete'),
    path('shipping-address/', views.seller_shipping_address, name='seller_shipping_address'),
    path('orders/', views.seller_order_history, name='seller_order_history'),
    path('orders/items/<int:item_id>/status/', views.update_order_item_status, name='update_order_item_status'),
]