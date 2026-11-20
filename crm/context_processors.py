"""Global template context processor for live sidebar badges and session metadata."""

from django.db.models import F
from django.utils import timezone

from crm.models import Product, SupportTicket


def crm_navigation_context(request):
    """Provide lightweight live counts for sidebar alert badges."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}

    ctx = {
        "nav_today": timezone.localdate(),
    }

    if user.is_staff_member:
        ctx["nav_open_tickets_count"] = SupportTicket.objects.filter(
            status=SupportTicket.Status.OPEN
        ).count()
    else:
        customer = getattr(user, "customer_profile", None)
        ctx["nav_open_tickets_count"] = (
            SupportTicket.objects.filter(
                customer=customer, status=SupportTicket.Status.OPEN
            ).count()
            if customer
            else 0
        )

    if user.is_manager_or_admin:
        ctx["nav_low_stock_count"] = Product.objects.filter(
            stock_qty__lte=F("reorder_level")
        ).count()

    return ctx
