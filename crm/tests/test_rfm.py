"""Tests for quintile-based RFM scoring, tier classification, and retention alerts."""

from datetime import timedelta
from decimal import Decimal
import pytest

from django.utils import timezone

from crm.models import Customer, RFMSegment, Transaction
from crm.services import (
    classify_rfm_tier,
    compute_rfm_segments,
    dispatch_retention_alert,
)


def test_classify_rfm_tier_strict_rules():
    assert classify_rfm_tier(5, 5, 5) == RFMSegment.TierLabel.CHAMPIONS
    assert classify_rfm_tier(4, 4, 4) == RFMSegment.TierLabel.CHAMPIONS
    assert classify_rfm_tier(4, 3, 4) == RFMSegment.TierLabel.LOYAL
    assert classify_rfm_tier(3, 3, 3) == RFMSegment.TierLabel.LOYAL
    assert classify_rfm_tier(5, 1, 2) == RFMSegment.TierLabel.POTENTIAL
    assert classify_rfm_tier(3, 2, 5) == RFMSegment.TierLabel.POTENTIAL
    assert classify_rfm_tier(2, 5, 5) == RFMSegment.TierLabel.AT_RISK
    assert classify_rfm_tier(1, 1, 1) == RFMSegment.TierLabel.AT_RISK
    assert classify_rfm_tier(3, 4, 2) == RFMSegment.TierLabel.AT_RISK


@pytest.mark.django_db
def test_compute_rfm_segments_assigns_all_four_tiers_accurately(attendant_user):
    ref_date = timezone.now()

    # Build 20 distinct customers spanning 4 clean behavioral bands (5 per band)
    specs = []
    # 5 Champions: very recent (1-5d), high freq (8-12), high spend (₦40k-₦60k)
    for i in range(5):
        specs.append(("champ", 1 + i, 8 + i, Decimal(str(5000 + i * 500))))
    # 5 Loyal: fairly recent (12-20d), medium-high freq (4-6), solid spend
    for i in range(5):
        specs.append(("loyal", 12 + i * 2, 4 + (i % 3), Decimal(str(3500 + i * 200))))
    # 5 Potential Loyalists: recent (6-10d), low freq (1-2), modest spend
    for i in range(5):
        specs.append(("potential", 6 + i, 1 if i < 3 else 2, Decimal(str(1800 + i * 100))))
    # 5 At-Risk / Dormant: old (90-150d), low freq (1-2), low spend
    for i in range(5):
        specs.append(("dormant", 90 + i * 15, 1, Decimal(str(800 + i * 100))))

    created_customers = {}
    for idx, (group, recency_days, freq, unit_net) in enumerate(specs, start=1):
        cust = Customer.objects.create(
            cust_code=f"UIV-R{idx:02d}",
            full_name=f"RFM Customer {idx}",
            phone=f"0805111{idx:04d}",
            category=Customer.Category.UG,
        )
        created_customers[cust.id] = group

        for t_idx in range(freq):
            # Most recent transaction at exact recency_days ago; older ones spaced earlier
            txn_dt = ref_date - timedelta(days=recency_days + t_idx * 5)
            Transaction.objects.create(
                customer=cust,
                attended_by=attendant_user,
                gross_amount=unit_net,
                discount_amount=Decimal("0.00"),
                net_amount=unit_net,
                payment_ref=f"RFM-{idx}-{t_idx}",
                txn_date=txn_dt,
            )

    processed = compute_rfm_segments(reference_date=ref_date)
    assert processed == 20
    assert RFMSegment.objects.count() == 20

    # Verify all scores are within [1, 5]
    for seg in RFMSegment.objects.all():
        assert 1 <= seg.r_score <= 5
        assert 1 <= seg.f_score <= 5
        assert 1 <= seg.m_score <= 5
        assert seg.tier_label == classify_rfm_tier(seg.r_score, seg.f_score, seg.m_score)

    # Verify top Champions and bottom Dormant groups classified as expected
    champ_tiers = set(
        RFMSegment.objects.filter(
            customer_id__in=[cid for cid, g in created_customers.items() if g == "champ"]
        ).values_list("tier_label", flat=True)
    )
    dormant_tiers = set(
        RFMSegment.objects.filter(
            customer_id__in=[cid for cid, g in created_customers.items() if g == "dormant"]
        ).values_list("tier_label", flat=True)
    )
    potential_tiers = set(
        RFMSegment.objects.filter(
            customer_id__in=[cid for cid, g in created_customers.items() if g == "potential"]
        ).values_list("tier_label", flat=True)
    )

    assert RFMSegment.TierLabel.CHAMPIONS in champ_tiers
    assert dormant_tiers == {RFMSegment.TierLabel.AT_RISK}
    assert RFMSegment.TierLabel.POTENTIAL in potential_tiers

    # Verify idempotent re-computation and retention alert dispatch
    assert compute_rfm_segments(reference_date=ref_date) == 20
    alert = dispatch_retention_alert(
        tier_label=RFMSegment.TierLabel.AT_RISK,
        message="Come back to UI Ventures for 2x loyalty points!",
        dispatched_by=attendant_user,
    )
    assert alert["recipient_count"] >= 5
    assert alert["tier_label"] == RFMSegment.TierLabel.AT_RISK
