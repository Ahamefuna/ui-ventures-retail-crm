"""Tests for atomic POS settlement, stock deduction, loyalty accrual, and 50% cap."""

from decimal import Decimal
import json
import pytest

from django.urls import reverse

from crm.models import LoyaltyLedger, Transaction, TransactionItem
from crm.services import (
    CheckoutValidationError,
    calculate_max_redeemable_points,
    settle_retail_transaction,
)


@pytest.mark.django_db
def test_atomic_checkout_deducts_stock_and_accrues_1_percent_points(
    attendant_user, sample_customer, sample_products
):
    book, notebook = sample_products
    sample_customer.loyalty_points = 0
    sample_customer.save()

    # Gross = 4000*1 + 1000*2 = 6000.00 -> 1% earn = 60 pts
    txn = settle_retail_transaction(
        customer=sample_customer,
        attended_by=attendant_user,
        cart_items=[
            {"product_id": book.id, "quantity": 1},
            {"product_id": notebook.id, "quantity": 2},
        ],
        points_to_redeem=0,
        payment_ref="POS-TEST-1001",
    )

    book.refresh_from_db()
    notebook.refresh_from_db()
    sample_customer.refresh_from_db()

    assert txn.gross_amount == Decimal("6000.00")
    assert txn.discount_amount == Decimal("0.00")
    assert txn.net_amount == Decimal("6000.00")
    assert txn.items.count() == 2
    assert book.stock_qty == 9
    assert notebook.stock_qty == 18
    assert sample_customer.loyalty_points == 60

    ledger = list(LoyaltyLedger.objects.filter(transaction=txn))
    assert len(ledger) == 1
    assert ledger[0].action_type == LoyaltyLedger.ActionType.EARN
    assert ledger[0].points_delta == 60
    assert ledger[0].balance_after == 60


@pytest.mark.django_db
def test_loyalty_redemption_50_percent_cap_and_dual_ledger_entries(
    attendant_user, sample_customer, sample_products
):
    book, _ = sample_products
    # Customer has 500 pts (₦5,000), gross is ₦4,000 -> 50% cap is ₦2,000 = 200 pts
    assert calculate_max_redeemable_points(500, Decimal("4000.00")) == 200

    txn = settle_retail_transaction(
        customer=sample_customer,
        attended_by=attendant_user,
        cart_items=[{"product_id": book.id, "quantity": 1}],
        points_to_redeem=200,
        payment_ref="POS-TEST-1002",
    )

    sample_customer.refresh_from_db()
    assert txn.gross_amount == Decimal("4000.00")
    assert txn.discount_amount == Decimal("2000.00")
    assert txn.net_amount == Decimal("2000.00")
    # 500 - 200 redeemed + 20 earned (1% of 2000) = 320
    assert sample_customer.loyalty_points == 320

    entries = list(LoyaltyLedger.objects.filter(transaction=txn).order_by("id"))
    assert len(entries) == 2
    assert entries[0].action_type == LoyaltyLedger.ActionType.REDEEM
    assert entries[0].points_delta == -200
    assert entries[0].balance_after == 300
    assert entries[1].action_type == LoyaltyLedger.ActionType.EARN
    assert entries[1].points_delta == 20
    assert entries[1].balance_after == 320


@pytest.mark.django_db
def test_redemption_above_50_percent_cap_is_rejected_atomically(
    attendant_user, sample_customer, sample_products
):
    book, _ = sample_products
    initial_stock = book.stock_qty
    initial_points = sample_customer.loyalty_points

    with pytest.raises(CheckoutValidationError, match="50% cap"):
        settle_retail_transaction(
            customer=sample_customer,
            attended_by=attendant_user,
            cart_items=[{"product_id": book.id, "quantity": 1}],
            points_to_redeem=201,  # ₦2,010 > 50% of ₦4,000
            payment_ref="POS-TEST-1003",
        )

    book.refresh_from_db()
    sample_customer.refresh_from_db()
    assert book.stock_qty == initial_stock
    assert sample_customer.loyalty_points == initial_points
    assert Transaction.objects.count() == 0


@pytest.mark.django_db
def test_redemption_exceeding_customer_balance_is_rejected(
    attendant_user, sample_customer, sample_products
):
    book, _ = sample_products
    sample_customer.loyalty_points = 50
    sample_customer.save()

    with pytest.raises(CheckoutValidationError, match="only has 50"):
        settle_retail_transaction(
            customer=sample_customer,
            attended_by=attendant_user,
            cart_items=[{"product_id": book.id, "quantity": 1}],
            points_to_redeem=100,
            payment_ref="POS-TEST-1004",
        )

    assert Transaction.objects.count() == 0


@pytest.mark.django_db
def test_insufficient_stock_rolls_back_entire_transaction(
    attendant_user, sample_customer, sample_products
):
    book, notebook = sample_products
    initial_notebook_stock = notebook.stock_qty
    initial_points = sample_customer.loyalty_points

    with pytest.raises(CheckoutValidationError, match="Insufficient stock"):
        settle_retail_transaction(
            customer=sample_customer,
            attended_by=attendant_user,
            cart_items=[
                {"product_id": notebook.id, "quantity": 2},
                {"product_id": book.id, "quantity": 999},
            ],
            points_to_redeem=10,
            payment_ref="POS-TEST-1005",
        )

    notebook.refresh_from_db()
    sample_customer.refresh_from_db()
    assert notebook.stock_qty == initial_notebook_stock
    assert sample_customer.loyalty_points == initial_points
    assert Transaction.objects.count() == 0
    assert TransactionItem.objects.count() == 0


@pytest.mark.django_db
def test_pos_checkout_view_redirects_to_printable_receipt(
    client, attendant_user, sample_customer, sample_products
):
    book, _ = sample_products
    client.force_login(attendant_user)

    resp = client.post(
        reverse("crm:pos"),
        data={
            "customer_id": sample_customer.id,
            "payment_ref": "POS-VIEW-9001",
            "points_to_redeem": "50",
            "cart_payload": json.dumps([{"product_id": book.id, "quantity": 1}]),
        },
    )
    assert resp.status_code == 302
    txn = Transaction.objects.get(payment_ref="POS-VIEW-9001")
    assert resp.url == reverse("crm:receipt", kwargs={"txn_id": txn.id})

    receipt_resp = client.get(resp.url)
    assert receipt_resp.status_code == 200
    assert txn.receipt_no in receipt_resp.content.decode()
