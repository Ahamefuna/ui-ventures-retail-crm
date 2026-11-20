"""Core business logic: atomic POS settlement, loyalty engine, RFM analytics, and alerts."""

from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
import logging

from django.db import transaction
from django.db.models import Count, Max, Sum
from django.utils import timezone
import pandas as pd

from crm.models import (
    Customer,
    LoyaltyLedger,
    Product,
    RFMSegment,
    Transaction,
    TransactionItem,
)

retention_logger = logging.getLogger("crm.retention")

POINT_EARN_RATE = Decimal("0.01")  # 1 loyalty point per ₦100 of net spend
POINT_NAIRA_VALUE = Decimal("10.00")  # 1 loyalty point = ₦10 discount
MAX_REDEMPTION_RATIO = Decimal("0.50")  # Redemption capped at 50% of gross total


class CheckoutValidationError(ValueError):
    """Raised when a POS checkout violates stock, cart, or loyalty redemption rules."""


def calculate_max_redeemable_points(customer_points: int, gross_amount: Decimal) -> int:
    """Return the maximum integer points redeemable under the 50% cap and user balance."""
    if gross_amount <= Decimal("0.00") or customer_points <= 0:
        return 0
    max_discount = (gross_amount * MAX_REDEMPTION_RATIO).quantize(
        Decimal("0.01"), rounding=ROUND_FLOOR
    )
    cap_points = int((max_discount / POINT_NAIRA_VALUE).to_integral_value(rounding=ROUND_FLOOR))
    return max(0, min(int(customer_points), cap_points))


@transaction.atomic
def settle_retail_transaction(
    *,
    customer: Customer,
    attended_by,
    cart_items: list[dict],
    points_to_redeem: int = 0,
    payment_ref: str = "",
    txn_date=None,
    recalculate_rfm: bool = True,
) -> Transaction:
    """
    Execute an atomic POS checkout:
      1. Validate cart lines and lock inventory rows.
      2. Enforce stock availability and deduct product stock_qty.
      3. Enforce loyalty balance and 50% gross redemption cap.
      4. Persist Transaction, TransactionItem rows, and immutable LoyaltyLedger entries.
      5. Optionally trigger RFM recalculation.
    """
    if not cart_items:
        raise CheckoutValidationError("Cart cannot be empty. Add at least one product.")

    try:
        points_to_redeem = int(points_to_redeem or 0)
    except (TypeError, ValueError) as exc:
        raise CheckoutValidationError("Points to redeem must be a whole number.") from exc

    if points_to_redeem < 0:
        raise CheckoutValidationError("Points to redeem cannot be negative.")

    payment_ref = (payment_ref or "").strip()
    if not payment_ref:
        raise CheckoutValidationError("Payment reference is required to complete checkout.")

    # Aggregate duplicate product entries cleanly before locking
    aggregated_qty: dict[int, int] = {}
    for entry in cart_items:
        product_id = entry.get("product_id")
        if product_id is None and entry.get("product") is not None:
            product_id = entry["product"].pk
        try:
            product_id = int(product_id)
            qty = int(entry.get("quantity", 0))
        except (TypeError, ValueError) as exc:
            raise CheckoutValidationError("Invalid product or quantity supplied.") from exc

        if qty <= 0:
            raise CheckoutValidationError("Item quantity must be at least 1.")
        aggregated_qty[product_id] = aggregated_qty.get(product_id, 0) + qty

    # Lock customer and requested products in deterministic order to avoid deadlocks
    locked_customer = Customer.objects.select_for_update().get(pk=customer.pk)
    product_ids = sorted(aggregated_qty.keys())
    locked_products = {
        p.pk: p
        for p in Product.objects.select_for_update().filter(pk__in=product_ids)
    }

    if len(locked_products) != len(product_ids):
        raise CheckoutValidationError("One or more selected products do not exist.")

    gross_amount = Decimal("0.00")
    prepared_lines = []
    for pid in product_ids:
        product = locked_products[pid]
        qty = aggregated_qty[pid]
        if product.stock_qty < qty:
            raise CheckoutValidationError(
                f"Insufficient stock for {product.product_name} ({product.sku_code}): "
                f"requested {qty}, available {product.stock_qty}."
            )
        line_subtotal = (product.unit_price * qty).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        gross_amount += line_subtotal
        prepared_lines.append((product, qty, product.unit_price, line_subtotal))

    # Validate loyalty point redemption against balance and 50% gross cap
    if points_to_redeem > locked_customer.loyalty_points:
        raise CheckoutValidationError(
            f"Cannot redeem {points_to_redeem} points; customer only has "
            f"{locked_customer.loyalty_points} available."
        )

    discount_amount = (Decimal(points_to_redeem) * POINT_NAIRA_VALUE).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    max_discount_allowed = (gross_amount * MAX_REDEMPTION_RATIO).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    if discount_amount > max_discount_allowed:
        max_pts = calculate_max_redeemable_points(locked_customer.loyalty_points, gross_amount)
        raise CheckoutValidationError(
            f"Redemption exceeds the 50% cap (₦{max_discount_allowed:,.2f}). "
            f"Maximum redeemable for this order is {max_pts} points."
        )

    net_amount = (gross_amount - discount_amount).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    effective_date = txn_date or timezone.now()

    txn = Transaction.objects.create(
        customer=locked_customer,
        attended_by=attended_by,
        gross_amount=gross_amount,
        discount_amount=discount_amount,
        net_amount=net_amount,
        payment_ref=payment_ref,
        txn_date=effective_date,
    )

    items_to_create = []
    for product, qty, unit_price, line_subtotal in prepared_lines:
        product.stock_qty -= qty
        product.save(update_fields=["stock_qty"])
        items_to_create.append(
            TransactionItem(
                transaction=txn,
                product=product,
                quantity=qty,
                unit_price_at_sale=unit_price,
                line_subtotal=line_subtotal,
            )
        )
    TransactionItem.objects.bulk_create(items_to_create)

    # Immutable loyalty ledger entries: separate REDEEM and EARN rows when both apply
    current_balance = locked_customer.loyalty_points

    if points_to_redeem > 0:
        current_balance -= points_to_redeem
        LoyaltyLedger.objects.create(
            customer=locked_customer,
            transaction=txn,
            action_type=LoyaltyLedger.ActionType.REDEEM,
            points_delta=-points_to_redeem,
            balance_after=current_balance,
            recorded_at=effective_date,
        )

    points_earned = int(
        (net_amount * POINT_EARN_RATE).to_integral_value(rounding=ROUND_FLOOR)
    )
    if points_earned > 0:
        current_balance += points_earned
        LoyaltyLedger.objects.create(
            customer=locked_customer,
            transaction=txn,
            action_type=LoyaltyLedger.ActionType.EARN,
            points_delta=points_earned,
            balance_after=current_balance,
            recorded_at=effective_date,
        )

    if current_balance != locked_customer.loyalty_points:
        locked_customer.loyalty_points = current_balance
        locked_customer.save(update_fields=["loyalty_points"])

    if recalculate_rfm:
        compute_rfm_segments()

    return txn


def classify_rfm_tier(r_score: int, f_score: int, m_score: int) -> str:
    """Assign retention tier strictly using UI Ventures RFM classification rules."""
    if r_score >= 4 and f_score >= 4 and m_score >= 4:
        return RFMSegment.TierLabel.CHAMPIONS
    if r_score >= 3 and f_score >= 3 and m_score >= 3:
        return RFMSegment.TierLabel.LOYAL
    if r_score >= 3 and f_score <= 2:
        return RFMSegment.TierLabel.POTENTIAL
    return RFMSegment.TierLabel.AT_RISK


def _assign_quintiles(series: pd.Series, labels: list[int]) -> pd.Series:
    """Assign 1-5 quintile scores using pd.qcut(..., 5) with rank(method='first')."""
    count = len(series)
    ranked = series.rank(method="first")
    if count >= 5:
        return pd.qcut(ranked, 5, labels=labels).astype(int)

    # Graceful proportional scaling when fewer than 5 customers exist in the database
    if count == 1:
        mid = labels[len(labels) // 2]
        return pd.Series([mid], index=series.index, dtype=int)

    scaled = []
    for r in ranked:
        pos = int(round((r - 1) / (count - 1) * (len(labels) - 1)))
        scaled.append(labels[pos])
    return pd.Series(scaled, index=series.index, dtype=int)


def compute_rfm_segments(reference_date=None) -> int:
    """
    Compute quintile-based RFM scores for all customers with >= 1 completed transaction
    and persist results via RFMSegment.objects.update_or_create().
    """
    ref_dt = reference_date or timezone.now()
    if timezone.is_naive(ref_dt):
        ref_dt = timezone.make_aware(ref_dt, timezone.get_current_timezone())

    aggregated = (
        Transaction.objects.values("customer_id")
        .annotate(
            last_txn=Max("txn_date"),
            frequency_count=Count("id"),
            monetary_total=Sum("net_amount"),
        )
    )

    rows = []
    for rec in aggregated:
        last_txn = rec["last_txn"]
        if timezone.is_naive(last_txn):
            last_txn = timezone.make_aware(last_txn, timezone.get_current_timezone())
        recency_days = max(0, (ref_dt - last_txn).days)
        rows.append(
            {
                "customer_id": rec["customer_id"],
                "recency_days": recency_days,
                "frequency_count": int(rec["frequency_count"]),
                "monetary_total": float(rec["monetary_total"] or Decimal("0.00")),
                "monetary_decimal": (rec["monetary_total"] or Decimal("0.00")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                ),
            }
        )

    if not rows:
        RFMSegment.objects.all().delete()
        return 0

    df = pd.DataFrame(rows)
    df["r_score"] = _assign_quintiles(df["recency_days"], [5, 4, 3, 2, 1])
    df["f_score"] = _assign_quintiles(df["frequency_count"], [1, 2, 3, 4, 5])
    df["m_score"] = _assign_quintiles(df["monetary_total"], [1, 2, 3, 4, 5])

    processed = 0
    with transaction.atomic():
        active_customer_ids = set(df["customer_id"].tolist())
        RFMSegment.objects.exclude(customer_id__in=active_customer_ids).delete()

        for row in df.itertuples(index=False):
            tier = classify_rfm_tier(int(row.r_score), int(row.f_score), int(row.m_score))
            RFMSegment.objects.update_or_create(
                customer_id=int(row.customer_id),
                defaults={
                    "recency_days": int(row.recency_days),
                    "frequency_count": int(row.frequency_count),
                    "monetary_total": row.monetary_decimal,
                    "r_score": int(row.r_score),
                    "f_score": int(row.f_score),
                    "m_score": int(row.m_score),
                    "tier_label": tier,
                },
            )
            processed += 1

    return processed


def dispatch_retention_alert(*, tier_label: str, message: str, dispatched_by) -> dict:
    """Log a simulated retention campaign alert for all customers in the selected RFM tier."""
    valid_tiers = {choice[0] for choice in RFMSegment.TierLabel.choices}
    if tier_label not in valid_tiers:
        raise ValueError(f"Unsupported RFM tier: {tier_label}")

    clean_message = (message or "").strip()
    if not clean_message:
        clean_message = RFMSegment.RECOMMENDED_ACTIONS[tier_label]

    recipients = list(
        RFMSegment.objects.filter(tier_label=tier_label)
        .select_related("customer")
        .values_list("customer__cust_code", "customer__full_name", "customer__phone")
    )
    recipient_count = len(recipients)
    actor = getattr(dispatched_by, "email", str(dispatched_by))

    retention_logger.info(
        "RETENTION_ALERT | tier=%s | recipients=%d | dispatched_by=%s | message=%s",
        tier_label,
        recipient_count,
        actor,
        clean_message,
    )

    return {
        "tier_label": tier_label,
        "recipient_count": recipient_count,
        "message": clean_message,
        "dispatched_by": actor,
        "timestamp": timezone.now(),
    }
