"""Custom template filters for Naira formatting, initials, and semantic badges."""

from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def naira(value):
    """Format a numeric value in Nigerian Naira with thousand separators."""
    try:
        amount = Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        amount = Decimal("0.00")
    return f"₦{amount:,.2f}"


@register.filter
def naira_int(value):
    """Format a numeric value in Nigerian Naira rounded to whole Naira."""
    try:
        amount = Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        amount = Decimal("0")
    return f"₦{amount:,.0f}"


@register.filter
def initials(full_name):
    """Return 1-2 uppercase initials for avatar chips."""
    parts = [p for p in str(full_name or "").strip().split() if p]
    if not parts:
        return "UI"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return f"{parts[0][0]}{parts[-1][0]}".upper()


@register.filter
def tier_badge_class(tier_label):
    """Return institutional CSS badge class for an RFM retention tier."""
    mapping = {
        "Champions": "badge-tier-champions",
        "Loyal Customers": "badge-tier-loyal",
        "Potential Loyalists": "badge-tier-potential",
        "At-Risk / Dormant": "badge-tier-atrisk",
    }
    return mapping.get(tier_label, "badge-tier-neutral")


@register.filter
def ticket_status_badge(status):
    """Return institutional CSS badge class for a support ticket status."""
    mapping = {
        "Open": "badge-status-open",
        "In_Progress": "badge-status-progress",
        "Resolved": "badge-status-resolved",
    }
    return mapping.get(status, "badge-tier-neutral")


@register.filter
def ticket_status_label(status):
    """Return human-readable label for a support ticket status."""
    mapping = {
        "Open": "Open",
        "In_Progress": "In Progress",
        "Resolved": "Resolved",
    }
    return mapping.get(status, status)
