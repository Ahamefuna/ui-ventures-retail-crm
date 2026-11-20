"""Views for the UI Ventures Retail CRM & RFM Analytics web application."""

import csv
from datetime import datetime, timedelta
from decimal import Decimal
import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F, ProtectedError, Q, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from crm.decorators import role_required
from crm.forms import (
    CustomerForm,
    LoginForm,
    ProductForm,
    StaffCreateForm,
    StaffUpdateForm,
    SupportTicketCreateForm,
    SupportTicketUpdateForm,
)
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
from crm.services import (
    CheckoutValidationError,
    POINT_NAIRA_VALUE,
    compute_rfm_segments,
    dispatch_retention_alert,
    settle_retail_transaction,
)


def _default_landing_for_user(user):
    if user.is_superuser or user.role in {User.Role.ADMIN, User.Role.MANAGER}:
        return "crm:dashboard"
    if user.role == User.Role.ATTENDANT:
        return "crm:pos"
    return "crm:my_portal"


def home_redirect_view(request):
    if not request.user.is_authenticated:
        return redirect("crm:login")
    return redirect(_default_landing_for_user(request.user))


def login_view(request):
    if request.user.is_authenticated:
        return redirect(_default_landing_for_user(request.user))

    form = LoginForm(request=request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        login(request, user)
        next_url = request.POST.get("next") or request.GET.get("next")
        if next_url and next_url.startswith("/"):
            return redirect(next_url)
        return redirect(_default_landing_for_user(user))

    return render(
        request,
        "crm/login.html",
        {
            "form": form,
            "next": request.GET.get("next", ""),
        },
    )


@login_required
def logout_view(request):
    logout(request)
    messages.info(request, "You have been signed out securely.")
    return redirect("crm:login")


@role_required(User.Role.ADMIN, User.Role.MANAGER)
def dashboard_view(request):
    total_customers = Customer.objects.count()
    active_buyers = RFMSegment.objects.count()

    sales_agg = Transaction.objects.aggregate(
        total_sales=Sum("net_amount"),
        txn_count=Count("id"),
        total_discount=Sum("discount_amount"),
    )
    total_sales = sales_agg["total_sales"] or Decimal("0.00")
    txn_count = sales_agg["txn_count"] or 0

    points_agg = Customer.objects.aggregate(total_points=Sum("loyalty_points"))
    active_loyalty_points = points_agg["total_points"] or 0
    loyalty_naira_value = Decimal(active_loyalty_points) * POINT_NAIRA_VALUE

    open_tickets = SupportTicket.objects.filter(status=SupportTicket.Status.OPEN).count()
    in_progress_tickets = SupportTicket.objects.filter(
        status=SupportTicket.Status.IN_PROGRESS
    ).count()

    # Monthly retail revenue for the last 6 months (inclusive of current month)
    now = timezone.now()
    six_months_ago = (now.replace(day=1) - timedelta(days=155)).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    monthly_qs = (
        Transaction.objects.filter(txn_date__gte=six_months_ago)
        .annotate(month=TruncMonth("txn_date"))
        .values("month")
        .annotate(revenue=Sum("net_amount"), orders=Count("id"))
        .order_by("month")
    )
    monthly_labels = [entry["month"].strftime("%b %Y") for entry in monthly_qs]
    monthly_revenue = [float(entry["revenue"] or 0) for entry in monthly_qs]
    monthly_orders = [int(entry["orders"] or 0) for entry in monthly_qs]

    # RFM tier distribution in fixed institutional display order
    tier_order = [
        RFMSegment.TierLabel.CHAMPIONS,
        RFMSegment.TierLabel.LOYAL,
        RFMSegment.TierLabel.POTENTIAL,
        RFMSegment.TierLabel.AT_RISK,
    ]
    tier_counts_map = {
        row["tier_label"]: row["total"]
        for row in RFMSegment.objects.values("tier_label").annotate(total=Count("id"))
    }
    rfm_labels = list(tier_order)
    rfm_counts = [tier_counts_map.get(tier, 0) for tier in tier_order]

    # Top 5 RFM Champions
    top_champions = (
        RFMSegment.objects.filter(tier_label=RFMSegment.TierLabel.CHAMPIONS)
        .select_related("customer")
        .order_by("-monetary_total", "-frequency_count")[:5]
    )
    if not top_champions:
        top_champions = (
            RFMSegment.objects.select_related("customer")
            .order_by("-monetary_total")[:5]
        )

    low_stock_products = Product.objects.filter(
        stock_qty__lte=F("reorder_level")
    ).order_by("stock_qty")[:6]

    recent_transactions = Transaction.objects.select_related(
        "customer", "attended_by"
    ).order_by("-txn_date")[:8]

    return render(
        request,
        "crm/dashboard.html",
        {
            "active_nav": "dashboard",
            "total_customers": total_customers,
            "active_buyers": active_buyers,
            "total_sales": total_sales,
            "txn_count": txn_count,
            "active_loyalty_points": active_loyalty_points,
            "loyalty_naira_value": loyalty_naira_value,
            "open_tickets": open_tickets,
            "in_progress_tickets": in_progress_tickets,
            "monthly_labels_json": json.dumps(monthly_labels),
            "monthly_revenue_json": json.dumps(monthly_revenue),
            "monthly_orders_json": json.dumps(monthly_orders),
            "rfm_labels_json": json.dumps(rfm_labels),
            "rfm_counts_json": json.dumps(rfm_counts),
            "top_champions": top_champions,
            "low_stock_products": low_stock_products,
            "recent_transactions": recent_transactions,
        },
    )


@role_required(User.Role.ADMIN, User.Role.MANAGER, User.Role.ATTENDANT)
def customers_list_view(request):
    query = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()
    tier = request.GET.get("tier", "").strip()

    qs = Customer.objects.select_related("rfm_segment").annotate(
        txn_count=Count("transactions", distinct=True),
        total_spend=Sum("transactions__net_amount"),
    )

    if query:
        qs = qs.filter(
            Q(full_name__icontains=query)
            | Q(phone__icontains=query)
            | Q(cust_code__icontains=query)
            | Q(email__icontains=query)
        )
    if category:
        qs = qs.filter(category=category)
    if tier:
        qs = qs.filter(rfm_segment__tier_label=tier)

    qs = qs.order_by("cust_code")
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "crm/customers.html",
        {
            "active_nav": "customers",
            "page_obj": page_obj,
            "total_matching": paginator.count,
            "query": query,
            "selected_category": category,
            "selected_tier": tier,
            "category_choices": Customer.Category.choices,
            "tier_choices": RFMSegment.TierLabel.choices,
            "customer_form": CustomerForm(),
        },
    )


@role_required(User.Role.ADMIN, User.Role.MANAGER, User.Role.ATTENDANT)
@require_POST
def customer_create_view(request):
    form = CustomerForm(request.POST)
    if form.is_valid():
        customer = form.save()
        messages.success(
            request,
            f"Customer {customer.full_name} ({customer.cust_code}) registered successfully.",
        )
        return redirect("crm:customer_detail", customer_id=customer.pk)
    for field, errs in form.errors.items():
        for err in errs:
            messages.error(request, f"{field.replace('_', ' ').title()}: {err}")
    return redirect("crm:customers")


@role_required(User.Role.ADMIN, User.Role.MANAGER, User.Role.ATTENDANT)
def customer_detail_view(request, customer_id):
    customer = get_object_or_404(
        Customer.objects.select_related("rfm_segment", "user"), pk=customer_id
    )
    transactions = (
        customer.transactions.select_related("attended_by")
        .prefetch_related("items__product")
        .order_by("-txn_date")[:50]
    )
    loyalty_entries = customer.loyalty_entries.select_related("transaction").order_by(
        "-recorded_at", "-id"
    )[:50]
    tickets = customer.support_tickets.select_related("assigned_to").order_by(
        "-created_at"
    )
    spend_summary = customer.transactions.aggregate(
        total_spend=Sum("net_amount"),
        total_discount=Sum("discount_amount"),
        txn_count=Count("id"),
    )

    return render(
        request,
        "crm/customer_detail.html",
        {
            "active_nav": "customers",
            "customer": customer,
            "edit_form": CustomerForm(instance=customer),
            "transactions": transactions,
            "loyalty_entries": loyalty_entries,
            "tickets": tickets,
            "total_spend": spend_summary["total_spend"] or Decimal("0.00"),
            "total_discount": spend_summary["total_discount"] or Decimal("0.00"),
            "txn_count": spend_summary["txn_count"] or 0,
        },
    )


@role_required(User.Role.ADMIN, User.Role.MANAGER, User.Role.ATTENDANT)
@require_POST
def customer_edit_view(request, customer_id):
    customer = get_object_or_404(Customer, pk=customer_id)
    form = CustomerForm(request.POST, instance=customer)
    if form.is_valid():
        form.save()
        messages.success(request, f"Profile updated for {customer.full_name}.")
    else:
        for field, errs in form.errors.items():
            for err in errs:
                messages.error(request, f"{field.replace('_', ' ').title()}: {err}")
    return redirect("crm:customer_detail", customer_id=customer.pk)


@role_required(User.Role.ADMIN, User.Role.MANAGER)
@require_POST
def customer_adjust_points_view(request, customer_id):
    customer = get_object_or_404(Customer, pk=customer_id)
    try:
        delta = int(request.POST.get("points_delta", "0"))
    except ValueError:
        messages.error(request, "Point adjustment must be a valid integer.")
        return redirect("crm:customer_detail", customer_id=customer.pk)

    if delta == 0:
        messages.warning(request, "Point adjustment delta cannot be zero.")
        return redirect("crm:customer_detail", customer_id=customer.pk)

    with transaction.atomic():
        locked = Customer.objects.select_for_update().get(pk=customer.pk)
        new_balance = locked.loyalty_points + delta
        if new_balance < 0:
            messages.error(
                request,
                f"Adjustment rejected: balance cannot drop below 0 (current balance: {locked.loyalty_points}).",
            )
            return redirect("crm:customer_detail", customer_id=customer.pk)

        locked.loyalty_points = new_balance
        locked.save(update_fields=["loyalty_points"])
        LoyaltyLedger.objects.create(
            customer=locked,
            transaction=None,
            action_type=LoyaltyLedger.ActionType.ADJUST,
            points_delta=delta,
            balance_after=new_balance,
        )

    messages.success(
        request,
        f"Loyalty balance adjusted by {delta:+d} pts. New balance: {new_balance} pts.",
    )
    return redirect("crm:customer_detail", customer_id=customer.pk)


@role_required(User.Role.ADMIN, User.Role.MANAGER, User.Role.ATTENDANT)
def pos_checkout_view(request):
    if request.method == "POST":
        customer_id = request.POST.get("customer_id")
        payment_ref = request.POST.get("payment_ref", "").strip()
        points_to_redeem = request.POST.get("points_to_redeem", "0")
        cart_json = request.POST.get("cart_payload", "[]")

        try:
            customer = Customer.objects.get(pk=int(customer_id))
        except (TypeError, ValueError, Customer.DoesNotExist):
            messages.error(request, "Select a valid registered customer before checkout.")
            return redirect("crm:pos")

        try:
            cart_items = json.loads(cart_json)
        except json.JSONDecodeError:
            messages.error(request, "Invalid cart data submitted. Please try again.")
            return redirect("crm:pos")

        try:
            txn = settle_retail_transaction(
                customer=customer,
                attended_by=request.user,
                cart_items=cart_items,
                points_to_redeem=points_to_redeem,
                payment_ref=payment_ref,
                recalculate_rfm=True,
            )
            messages.success(
                request,
                f"Transaction {txn.receipt_no} settled successfully (Net: ₦{txn.net_amount:,.2f}).",
            )
            return redirect("crm:receipt", txn_id=txn.pk)
        except CheckoutValidationError as exc:
            messages.error(request, str(exc))
            return redirect("crm:pos")

    customers = list(
        Customer.objects.order_by("full_name").values(
            "id",
            "cust_code",
            "full_name",
            "phone",
            "category",
            "loyalty_points",
            "rfm_segment__tier_label",
        )
    )
    for c in customers:
        c["rfm_tier"] = c.pop("rfm_segment__tier_label") or "Unsegmented"
    products = list(
        Product.objects.order_by("category", "product_name").values(
            "id", "sku_code", "product_name", "category", "unit_price", "stock_qty"
        )
    )
    for item in products:
        item["unit_price"] = float(item["unit_price"])

    return render(
        request,
        "crm/pos.html",
        {
            "active_nav": "pos",
            "customers": customers,
            "customers_json": json.dumps(customers),
            "products": products,
            "products_json": json.dumps(products),
            "product_categories": [c[0] for c in Product.Category.choices],
            "point_naira_value": int(POINT_NAIRA_VALUE),
        },
    )


@login_required
def receipt_view(request, txn_id):
    txn = get_object_or_404(
        Transaction.objects.select_related("customer", "customer__user", "attended_by")
        .prefetch_related("items__product", "loyalty_entries"),
        pk=txn_id,
    )

    if not request.user.is_staff_member:
        if txn.customer.user_id != request.user.id:
            return render(request, "403.html", status=403)

    redeemed_entry = next(
        (e for e in txn.loyalty_entries.all() if e.action_type == LoyaltyLedger.ActionType.REDEEM),
        None,
    )
    earned_entry = next(
        (e for e in txn.loyalty_entries.all() if e.action_type == LoyaltyLedger.ActionType.EARN),
        None,
    )

    return render(
        request,
        "crm/receipt.html",
        {
            "active_nav": "pos" if request.user.is_staff_member else "my_portal",
            "txn": txn,
            "redeemed_points": abs(redeemed_entry.points_delta) if redeemed_entry else 0,
            "earned_points": earned_entry.points_delta if earned_entry else 0,
        },
    )


@role_required(User.Role.ADMIN, User.Role.MANAGER)
def rfm_view(request):
    selected_tier = request.GET.get("tier", "").strip()
    query = request.GET.get("q", "").strip()

    all_segments = RFMSegment.objects.select_related("customer")
    total_segmented = all_segments.count()

    tier_defs = [
        (RFMSegment.TierLabel.CHAMPIONS, "champions", "bi-trophy-fill", "R≥4, F≥4, M≥4"),
        (RFMSegment.TierLabel.LOYAL, "loyal", "bi-award-fill", "R≥3, F≥3, M≥3"),
        (RFMSegment.TierLabel.POTENTIAL, "potential", "bi-graph-up-arrow", "R≥3, F≤2"),
        (RFMSegment.TierLabel.AT_RISK, "atrisk", "bi-exclamation-triangle-fill", "Dormant / Declining"),
    ]

    tier_stats_raw = {
        row["tier_label"]: row
        for row in all_segments.values("tier_label").annotate(
            count=Count("id"),
            spend=Sum("monetary_total"),
        )
    }

    tier_cards = []
    for label, slug, icon, rule in tier_defs:
        stat = tier_stats_raw.get(label, {"count": 0, "spend": Decimal("0.00")})
        count = stat["count"] or 0
        share = round((count / total_segmented) * 100, 1) if total_segmented else 0.0
        tier_cards.append(
            {
                "label": label,
                "slug": slug,
                "icon": icon,
                "rule": rule,
                "count": count,
                "share": share,
                "spend": stat["spend"] or Decimal("0.00"),
                "default_message": RFMSegment.RECOMMENDED_ACTIONS[label],
            }
        )

    qs = all_segments
    if selected_tier:
        qs = qs.filter(tier_label=selected_tier)
    if query:
        qs = qs.filter(
            Q(customer__full_name__icontains=query)
            | Q(customer__cust_code__icontains=query)
            | Q(customer__phone__icontains=query)
        )

    qs = qs.order_by("-r_score", "-f_score", "-m_score", "-monetary_total")
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    last_updated = RFMSegment.objects.order_by("-updated_at").values_list(
        "updated_at", flat=True
    ).first()

    recent_alerts = []
    alert_log_path = settings.LOGS_DIR / "retention_alerts.log"
    if alert_log_path.exists():
        try:
            lines = alert_log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            for raw in reversed(lines[-8:]):
                if "RETENTION_ALERT" not in raw:
                    continue
                timestamp = raw[1:20] if raw.startswith("[") and len(raw) >= 20 else ""
                parts = [p.strip() for p in raw.split("|")[1:]]
                parsed = {"timestamp": timestamp, "tier": "", "recipients": "", "dispatched_by": "", "message": ""}
                for part in parts:
                    if "=" in part:
                        k, v = part.split("=", 1)
                        k = k.strip()
                        if k in parsed:
                            parsed[k] = v.strip()
                recent_alerts.append(parsed)
        except OSError:
            recent_alerts = []

    return render(
        request,
        "crm/rfm.html",
        {
            "active_nav": "rfm",
            "tier_cards": tier_cards,
            "total_segmented": total_segmented,
            "page_obj": page_obj,
            "selected_tier": selected_tier,
            "query": query,
            "tier_choices": RFMSegment.TierLabel.choices,
            "last_updated": last_updated,
            "recent_alerts": recent_alerts,
            "recommended_actions_json": json.dumps(
                {str(k): v for k, v in RFMSegment.RECOMMENDED_ACTIONS.items()}
            ),
        },
    )


@role_required(User.Role.ADMIN, User.Role.MANAGER)
@require_POST
def rfm_recompute_view(request):
    count = compute_rfm_segments()
    messages.success(
        request,
        f"RFM quintile scoring completed live across {count} active customers.",
    )
    return redirect("crm:rfm")


@role_required(User.Role.ADMIN, User.Role.MANAGER)
@require_POST
def rfm_dispatch_alert_view(request):
    tier_label = request.POST.get("tier_label", "").strip()
    message_text = request.POST.get("campaign_message", "").strip()
    try:
        result = dispatch_retention_alert(
            tier_label=tier_label,
            message=message_text,
            dispatched_by=request.user,
        )
        messages.success(
            request,
            f"Retention alert dispatched to {result['recipient_count']} customers in "
            f"'{result['tier_label']}' tier and logged to retention audit trail.",
        )
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("crm:rfm")


@login_required
def tickets_view(request):
    status_filter = request.GET.get("status", "").strip()
    category_filter = request.GET.get("category", "").strip()
    query = request.GET.get("q", "").strip()

    is_customer_user = not request.user.is_staff_member
    customer_profile = getattr(request.user, "customer_profile", None)

    if is_customer_user:
        if customer_profile is None:
            base_qs = SupportTicket.objects.none()
        else:
            base_qs = SupportTicket.objects.filter(customer=customer_profile)
    else:
        base_qs = SupportTicket.objects.all()

    base_qs = base_qs.select_related("customer", "assigned_to")

    counts = {
        "total": base_qs.count(),
        "open": base_qs.filter(status=SupportTicket.Status.OPEN).count(),
        "in_progress": base_qs.filter(status=SupportTicket.Status.IN_PROGRESS).count(),
        "resolved": base_qs.filter(status=SupportTicket.Status.RESOLVED).count(),
    }

    qs = base_qs
    if status_filter:
        qs = qs.filter(status=status_filter)
    if category_filter:
        qs = qs.filter(category=category_filter)
    if query:
        qs = qs.filter(
            Q(ticket_code__icontains=query)
            | Q(subject__icontains=query)
            | Q(customer__full_name__icontains=query)
            | Q(customer__cust_code__icontains=query)
        )

    paginator = Paginator(qs.order_by("-created_at"), 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    staff_members = User.objects.filter(
        role__in=[User.Role.ADMIN, User.Role.MANAGER, User.Role.ATTENDANT],
        is_active=True,
    ).order_by("full_name")

    create_form = SupportTicketCreateForm(
        for_customer=customer_profile if is_customer_user else None
    )

    return render(
        request,
        "crm/tickets.html",
        {
            "active_nav": "tickets",
            "page_obj": page_obj,
            "counts": counts,
            "status_filter": status_filter,
            "category_filter": category_filter,
            "query": query,
            "status_choices": SupportTicket.Status.choices,
            "category_choices": SupportTicket.Category.choices,
            "create_form": create_form,
            "staff_members": staff_members,
            "is_customer_user": is_customer_user,
        },
    )


@login_required
@require_POST
def ticket_create_view(request):
    is_customer_user = not request.user.is_staff_member
    customer_profile = getattr(request.user, "customer_profile", None)

    if is_customer_user and customer_profile is None:
        messages.error(request, "No customer profile is linked to your account.")
        return redirect("crm:my_portal")

    form = SupportTicketCreateForm(
        request.POST,
        for_customer=customer_profile if is_customer_user else None,
    )
    if form.is_valid():
        ticket = form.save(commit=False)
        if is_customer_user:
            ticket.customer = customer_profile
        ticket.status = SupportTicket.Status.OPEN
        ticket.save()
        messages.success(
            request,
            f"Support ticket {ticket.ticket_code} submitted successfully.",
        )
    else:
        for field, errs in form.errors.items():
            for err in errs:
                messages.error(request, f"{field.replace('_', ' ').title()}: {err}")

    next_target = request.POST.get("next_view", "")
    if next_target == "my_portal" or is_customer_user:
        if next_target == "my_portal":
            return redirect("crm:my_portal")
    return redirect("crm:tickets")


@role_required(User.Role.ADMIN, User.Role.MANAGER, User.Role.ATTENDANT)
@require_POST
def ticket_update_view(request, ticket_id):
    ticket = get_object_or_404(SupportTicket, pk=ticket_id)
    form = SupportTicketUpdateForm(request.POST, instance=ticket)
    if form.is_valid():
        updated = form.save()
        messages.success(
            request,
            f"Ticket {updated.ticket_code} updated to {updated.get_status_display()}.",
        )
    else:
        for field, errs in form.errors.items():
            for err in errs:
                messages.error(request, f"{field.replace('_', ' ').title()}: {err}")
    return redirect("crm:tickets")


def _parse_report_filters(request):
    start_str = request.GET.get("start_date", "").strip()
    end_str = request.GET.get("end_date", "").strip()
    category = request.GET.get("category", "").strip()

    tz = timezone.get_current_timezone()
    start_dt = None
    end_dt = None

    if start_str:
        try:
            start_dt = timezone.make_aware(
                datetime.strptime(start_str, "%Y-%m-%d"), tz
            )
        except ValueError:
            start_str = ""
    if end_str:
        try:
            end_dt = timezone.make_aware(
                datetime.strptime(end_str, "%Y-%m-%d") + timedelta(days=1) - timedelta(seconds=1),
                tz,
            )
        except ValueError:
            end_str = ""

    return start_str, end_str, category, start_dt, end_dt


@role_required(User.Role.ADMIN, User.Role.MANAGER)
def reports_view(request):
    start_str, end_str, category, start_dt, end_dt = _parse_report_filters(request)

    txn_qs = Transaction.objects.all()
    item_qs = TransactionItem.objects.select_related("product", "transaction")

    if start_dt:
        txn_qs = txn_qs.filter(txn_date__gte=start_dt)
        item_qs = item_qs.filter(transaction__txn_date__gte=start_dt)
    if end_dt:
        txn_qs = txn_qs.filter(txn_date__lte=end_dt)
        item_qs = item_qs.filter(transaction__txn_date__lte=end_dt)
    if category:
        item_qs = item_qs.filter(product__category=category)
        txn_qs = txn_qs.filter(items__product__category=category).distinct()

    sales_summary = txn_qs.aggregate(
        txn_count=Count("id"),
        gross_total=Sum("gross_amount"),
        discount_total=Sum("discount_amount"),
        net_total=Sum("net_amount"),
    )
    units_sold = item_qs.aggregate(units=Sum("quantity"))["units"] or 0

    category_breakdown = list(
        item_qs.values("product__category")
        .annotate(
            units=Sum("quantity"),
            revenue=Sum("line_subtotal"),
            orders=Count("transaction_id", distinct=True),
        )
        .order_by("-revenue")
    )

    rfm_breakdown = list(
        RFMSegment.objects.values("tier_label")
        .annotate(
            customers=Count("id"),
            total_spend=Sum("monetary_total"),
            total_orders=Sum("frequency_count"),
        )
        .order_by("-total_spend")
    )

    cat_labels = [row["product__category"] for row in category_breakdown]
    cat_revenue = [float(row["revenue"] or 0) for row in category_breakdown]

    return render(
        request,
        "crm/reports.html",
        {
            "active_nav": "reports",
            "start_date": start_str,
            "end_date": end_str,
            "selected_category": category,
            "category_choices": Product.Category.choices,
            "txn_count": sales_summary["txn_count"] or 0,
            "gross_total": sales_summary["gross_total"] or Decimal("0.00"),
            "discount_total": sales_summary["discount_total"] or Decimal("0.00"),
            "net_total": sales_summary["net_total"] or Decimal("0.00"),
            "units_sold": units_sold,
            "category_breakdown": category_breakdown,
            "rfm_breakdown": rfm_breakdown,
            "cat_labels_json": json.dumps(cat_labels),
            "cat_revenue_json": json.dumps(cat_revenue),
        },
    )


@role_required(User.Role.ADMIN, User.Role.MANAGER)
def export_sales_csv_view(request):
    start_str, end_str, category, start_dt, end_dt = _parse_report_filters(request)

    qs = Transaction.objects.select_related("customer", "attended_by").order_by("-txn_date")
    if start_dt:
        qs = qs.filter(txn_date__gte=start_dt)
    if end_dt:
        qs = qs.filter(txn_date__lte=end_dt)
    if category:
        qs = qs.filter(items__product__category=category).distinct()

    response = HttpResponse(content_type="text/csv")
    filename = f"uiventures_sales_report_{timezone.now().strftime('%Y%m%d_%H%M')}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(
        [
            "Receipt No",
            "Transaction Date",
            "Customer Code",
            "Customer Name",
            "Category",
            "Attended By",
            "Payment Ref",
            "Gross Amount (NGN)",
            "Discount Amount (NGN)",
            "Net Amount (NGN)",
        ]
    )
    for txn in qs:
        writer.writerow(
            [
                txn.receipt_no,
                timezone.localtime(txn.txn_date).strftime("%Y-%m-%d %H:%M:%S"),
                txn.customer.cust_code,
                txn.customer.full_name,
                txn.customer.category,
                txn.attended_by.full_name,
                txn.payment_ref,
                f"{txn.gross_amount:.2f}",
                f"{txn.discount_amount:.2f}",
                f"{txn.net_amount:.2f}",
            ]
        )
    return response


@role_required(User.Role.ADMIN, User.Role.MANAGER)
def export_rfm_csv_view(request):
    response = HttpResponse(content_type="text/csv")
    filename = f"uiventures_rfm_segments_{timezone.now().strftime('%Y%m%d_%H%M')}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(
        [
            "Customer Code",
            "Customer Name",
            "Phone",
            "Category",
            "Loyalty Points",
            "Recency (Days)",
            "Frequency (Txns)",
            "Monetary Total (NGN)",
            "R Score",
            "F Score",
            "M Score",
            "RFM Code",
            "Tier Label",
            "Recommended Action",
        ]
    )
    segments = RFMSegment.objects.select_related("customer").order_by(
        "-r_score", "-f_score", "-m_score", "-monetary_total"
    )
    for seg in segments:
        writer.writerow(
            [
                seg.customer.cust_code,
                seg.customer.full_name,
                seg.customer.phone,
                seg.customer.category,
                seg.customer.loyalty_points,
                seg.recency_days,
                seg.frequency_count,
                f"{seg.monetary_total:.2f}",
                seg.r_score,
                seg.f_score,
                seg.m_score,
                seg.rfm_code,
                seg.tier_label,
                seg.recommended_action,
            ]
        )
    return response


@role_required(User.Role.ADMIN, User.Role.MANAGER)
def products_view(request):
    query = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()
    low_stock_only = request.GET.get("low_stock") == "1"

    all_products = Product.objects.all()
    total_skus = all_products.count()
    low_stock_count = all_products.filter(stock_qty__lte=F("reorder_level")).count()
    total_units = all_products.aggregate(units=Sum("stock_qty"))["units"] or 0

    qs = all_products
    if query:
        qs = qs.filter(
            Q(sku_code__icontains=query) | Q(product_name__icontains=query)
        )
    if category:
        qs = qs.filter(category=category)
    if low_stock_only:
        qs = qs.filter(stock_qty__lte=F("reorder_level"))

    paginator = Paginator(qs.order_by("category", "sku_code"), 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "crm/products.html",
        {
            "active_nav": "products",
            "page_obj": page_obj,
            "total_skus": total_skus,
            "low_stock_count": low_stock_count,
            "total_units": total_units,
            "query": query,
            "selected_category": category,
            "low_stock_only": low_stock_only,
            "category_choices": Product.Category.choices,
            "product_form": ProductForm(),
        },
    )


@role_required(User.Role.ADMIN, User.Role.MANAGER)
@require_POST
def product_create_view(request):
    form = ProductForm(request.POST)
    if form.is_valid():
        product = form.save()
        messages.success(
            request,
            f"Product {product.product_name} ({product.sku_code}) added to catalog.",
        )
    else:
        for field, errs in form.errors.items():
            for err in errs:
                messages.error(request, f"{field.replace('_', ' ').title()}: {err}")
    return redirect("crm:products")


@role_required(User.Role.ADMIN, User.Role.MANAGER)
@require_POST
def product_edit_view(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    form = ProductForm(request.POST, instance=product)
    if form.is_valid():
        form.save()
        messages.success(request, f"Product {product.sku_code} updated.")
    else:
        for field, errs in form.errors.items():
            for err in errs:
                messages.error(request, f"{field.replace('_', ' ').title()}: {err}")
    return redirect("crm:products")


@role_required(User.Role.ADMIN, User.Role.MANAGER)
@require_POST
def product_delete_view(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    sku = product.sku_code
    try:
        product.delete()
        messages.success(request, f"Product {sku} removed from catalog.")
    except ProtectedError:
        messages.error(
            request,
            f"Cannot delete {sku} because it is referenced by historical sales receipts. "
            "Set stock quantity to 0 instead.",
        )
    return redirect("crm:products")


@role_required(User.Role.ADMIN)
def staff_view(request):
    staff_users = User.objects.filter(
        role__in=[User.Role.ADMIN, User.Role.MANAGER, User.Role.ATTENDANT]
    ).order_by("role", "full_name")

    return render(
        request,
        "crm/staff.html",
        {
            "active_nav": "staff",
            "staff_users": staff_users,
            "create_form": StaffCreateForm(),
            "role_choices": [
                (User.Role.ADMIN, "Admin"),
                (User.Role.MANAGER, "Manager"),
                (User.Role.ATTENDANT, "Attendant"),
            ],
        },
    )


@role_required(User.Role.ADMIN)
@require_POST
def staff_create_view(request):
    form = StaffCreateForm(request.POST)
    if form.is_valid():
        user = form.save()
        messages.success(
            request,
            f"Staff account created for {user.full_name} ({user.staff_code} — {user.role}).",
        )
    else:
        for field, errs in form.errors.items():
            for err in errs:
                messages.error(request, f"{field.replace('_', ' ').title()}: {err}")
    return redirect("crm:staff")


@role_required(User.Role.ADMIN)
@require_POST
def staff_edit_view(request, user_id):
    staff_member = get_object_or_404(
        User,
        pk=user_id,
        role__in=[User.Role.ADMIN, User.Role.MANAGER, User.Role.ATTENDANT],
    )
    form = StaffUpdateForm(request.POST, instance=staff_member)
    if form.is_valid():
        updated = form.save()
        messages.success(request, f"Staff account updated for {updated.full_name}.")
    else:
        for field, errs in form.errors.items():
            for err in errs:
                messages.error(request, f"{field.replace('_', ' ').title()}: {err}")
    return redirect("crm:staff")


@role_required(User.Role.CUSTOMER)
def my_portal_view(request):
    customer = getattr(request.user, "customer_profile", None)
    if customer is None:
        customer = Customer.objects.filter(email__iexact=request.user.email).first()
        if customer and customer.user_id is None:
            customer.user = request.user
            customer.save(update_fields=["user"])

    if customer is None:
        return render(
            request,
            "crm/my_portal.html",
            {
                "active_nav": "my_portal",
                "customer": None,
                "transactions": [],
                "loyalty_entries": [],
                "tickets": [],
                "ticket_form": None,
            },
        )

    transactions = (
        customer.transactions.select_related("attended_by")
        .prefetch_related("items__product")
        .order_by("-txn_date")[:30]
    )
    loyalty_entries = customer.loyalty_entries.select_related("transaction").order_by(
        "-recorded_at", "-id"
    )[:30]
    tickets = customer.support_tickets.select_related("assigned_to").order_by(
        "-created_at"
    )
    spend_agg = customer.transactions.aggregate(
        total_spend=Sum("net_amount"),
        txn_count=Count("id"),
    )
    rfm_segment = RFMSegment.objects.filter(customer=customer).first()

    return render(
        request,
        "crm/my_portal.html",
        {
            "active_nav": "my_portal",
            "customer": customer,
            "rfm_segment": rfm_segment,
            "total_spend": spend_agg["total_spend"] or Decimal("0.00"),
            "txn_count": spend_agg["txn_count"] or 0,
            "transactions": transactions,
            "loyalty_entries": loyalty_entries,
            "tickets": tickets,
            "ticket_form": SupportTicketCreateForm(for_customer=customer),
        },
    )
