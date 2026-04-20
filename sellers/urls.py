from django.urls import path
from . import views

urlpatterns = [
    path('', views.seller_home, name='seller_home'),
    path('listings/', views.product_list, name='product_list'),
    path('listings/create/', views.product_creation, name='product_creation'),
    path('listings/edit/<int:id>/', views.product_edit, name='product_edit'),
    path('listings/delete/<int:id>/', views.product_delete, name='product_delete'),
    path('shipping-address/', views.seller_shipping_address, name='seller_shipping_address'),
    path('orders/', views.seller_order_history, name='seller_order_history'),
    path('orders/items/<int:item_id>/status/', views.update_order_item_status, name='update_order_item_status'),
    path('orders/items/<int:item_id>/return/', views.request_return, name='request_return'),
    path('returns/buyer/', views.buyer_return_requests, name='buyer_return_requests'),
    path('returns/seller/', views.seller_return_requests, name='seller_return_requests'),
    path('returns/<int:return_id>/approve/', views.approve_return, name='approve_return'),
    path('returns/<int:return_id>/reject/', views.reject_return, name='reject_return'),
    path('webhooks/', views.webhook_settings, name='webhook_settings'),
    path('webhooks/toggle/', views.toggle_webhook, name='toggle_webhook'),
    path('notifications/<int:notification_id>/dismiss/', views.dismiss_notification, name='dismiss_notification'),
]
