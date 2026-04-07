from functools import wraps

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from rest_framework.permissions import BasePermission


ROLE_HOME_REDIRECTS = {
    'buyer': 'buyer_home',
    'seller': 'seller_home',
    'admin': 'admin_home',
}


def role_required(*allowed_roles):
    
    def decorator(view_func):
        @login_required(login_url='login')
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            user_role = getattr(request.user, 'role', None)
            if user_role not in allowed_roles:
                redirect_route = ROLE_HOME_REDIRECTS.get(user_role, 'index')
                return redirect(redirect_route)
            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator

class IsBuyer(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'buyer' # defines buyer permissions


class IsSeller(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'seller' # defines seller permissions


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'admin' # defines admin permissions