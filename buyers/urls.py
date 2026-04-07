from django.urls import path
from . import views

urlpatterns = [
    path('', views.buyer_homepage, name='buyer_home'),
    path('compare/', views.compare_products, name='compare_products'),
    path('orders/', views.buyer_order_history, name='buyer_order_history'),
    path('cart/', views.cart_view, name="cart_view"),
    path('cart/add/<int:product_id>/', views.add_to_cart, name="add_to_cart"),
    path('cart/update/<int:product_id>/', views.update_cart, name='update_cart'),
    path('cart/remove/<int:product_id>/', views.remove_from_cart, name='remove_from_cart'),
    path('checkout/', views.checkout_view, name="checkout"),
]