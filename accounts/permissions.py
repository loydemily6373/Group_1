from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission


def role_required(*allowed_roles):
    
    def decorator(view_func):
        @login_required(login_url='login')
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            
            if getattr(request.user, 'role', None) not in allowed_roles:
                raise PermissionDenied("You do not have permission to view this page.")
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