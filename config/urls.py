from django.urls import path, include
from accounts.views import admin_home, index_view, login_view, signup_view
from buyers.views import buyer_homepage, buyer_order_history, add_to_cart, update_cart, remove_from_cart, cart_view, checkout_view
urlpatterns = [
    path('accounts/', include('accounts.urls')),
    path('', index_view, name='index'),
    path('login/', login_view, name="login"),
    # The signup page is a normal HTML route; the form submits to /accounts/register/ via JavaScript.
    path('signup/', signup_view, name='signup'),
    # Admin has a dedicated page route separate from Django's built-in admin URL namespace.
    path('admin-home/', admin_home, name='admin_home'),
    path('buyer/', buyer_homepage, name='buyer_home'),
    path('buyer/orders/', buyer_order_history, name='buyer_order_history'),
    path('cart/', cart_view, name="cart_view"),
    path('cart/add/<int:product_id>/', add_to_cart, name="add_to_cart"),
    path('cart/update/<int:product_id>/', update_cart, name='update_cart'),
    path('cart/remove/<int:product_id>/', remove_from_cart, name='remove_from_cart'),
    path('checkout/', checkout_view, name="checkout"),
    path('products/', include('products.urls')),
    path('admin/', include('admin.urls')),
]