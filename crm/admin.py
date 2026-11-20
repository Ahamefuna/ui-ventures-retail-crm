"""Django admin registration for UI Ventures Retail CRM models."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from crm.models import (
    Customer,
    LoyaltyLedger,
    Product,
    RFMSegment,
    SupportTicket,
    Transaction,
    TransactionItem,
    User,
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("email", "full_name", "staff_code", "role", "is_active", "created_at")
    list_filter = ("role", "is_active")
    search_fields = ("email", "full_name", "staff_code")
    ordering = ("-created_at",)
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("full_name", "staff_code", "role")}),
        (
            "Permissions",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Important dates", {"fields": ("last_login",)}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "full_name", "staff_code", "role", "password1", "password2"),
            },
        ),
    )


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("cust_code", "full_name", "phone", "category", "loyalty_points", "created_at")
    list_filter = ("category",)
    search_fields = ("cust_code", "full_name", "phone", "email")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("sku_code", "product_name", "category", "unit_price", "stock_qty", "reorder_level")
    list_filter = ("category",)
    search_fields = ("sku_code", "product_name")


class TransactionItemInline(admin.TabularInline):
    model = TransactionItem
    extra = 0
    readonly_fields = ("product", "quantity", "unit_price_at_sale", "line_subtotal")


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        "receipt_no",
        "customer",
        "attended_by",
        "gross_amount",
        "discount_amount",
        "net_amount",
        "txn_date",
    )
    list_filter = ("txn_date",)
    search_fields = ("receipt_no", "payment_ref", "customer__full_name", "customer__cust_code")
    inlines = [TransactionItemInline]


@admin.register(LoyaltyLedger)
class LoyaltyLedgerAdmin(admin.ModelAdmin):
    list_display = ("customer", "action_type", "points_delta", "balance_after", "transaction", "recorded_at")
    list_filter = ("action_type",)
    search_fields = ("customer__cust_code", "customer__full_name")


@admin.register(RFMSegment)
class RFMSegmentAdmin(admin.ModelAdmin):
    list_display = (
        "customer",
        "recency_days",
        "frequency_count",
        "monetary_total",
        "r_score",
        "f_score",
        "m_score",
        "tier_label",
        "updated_at",
    )
    list_filter = ("tier_label",)
    search_fields = ("customer__cust_code", "customer__full_name")


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ("ticket_code", "customer", "category", "subject", "status", "assigned_to", "created_at")
    list_filter = ("status", "category")
    search_fields = ("ticket_code", "subject", "customer__full_name")
