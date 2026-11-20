"""Authentication backend allowing sign-in with either Email or Staff Code."""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

User = get_user_model()


class EmailOrStaffCodeBackend(ModelBackend):
    """Authenticate active users via email address or institutional staff_code."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        identifier = (username or kwargs.get("email") or "").strip()
        if not identifier or not password:
            return None

        user = (
            User.objects.filter(
                Q(email__iexact=identifier) | Q(staff_code__iexact=identifier)
            )
            .order_by("id")
            .first()
        )
        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
