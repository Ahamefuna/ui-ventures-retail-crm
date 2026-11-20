"""Role-based access control decorators for UI Ventures CRM views."""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.shortcuts import render


def role_required(*allowed_roles):
    """Restrict view access to users whose role is in allowed_roles (403 otherwise)."""

    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            user = request.user
            if user.is_superuser or user.role in allowed_roles:
                return view_func(request, *args, **kwargs)
            return render(request, "403.html", status=403)

        return _wrapped

    return decorator
