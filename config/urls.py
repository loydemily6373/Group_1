from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include
from accounts.views import admin_home, index_view, login_view, signup_view
urlpatterns = [
    path('accounts/', include('accounts.urls')),
    path('', index_view, name='index'),
    path('login/', login_view, name="login"),
    # The signup page is a normal HTML route; the form submits to /accounts/register/ via JavaScript.
    path('signup/', signup_view, name='signup'),
    # Admin has a dedicated page route separate from Django's built-in admin URL namespace.
    path('admin-home/', admin_home, name='admin_home'),
    path('sellers/', include('sellers.urls')),
    path('buyer/', include('buyers.urls')),
    path('admin/', include('admin.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)