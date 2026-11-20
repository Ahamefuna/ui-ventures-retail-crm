"""Tests for the Support Ticket lifecycle (Open -> In_Progress -> Resolved) and isolation."""

import pytest
from django.urls import reverse

from crm.models import Customer, SupportTicket


@pytest.mark.django_db
def test_support_ticket_full_lifecycle(client, customer_user, manager_user):
    # 1. Customer submits a new ticket -> starts as Open
    client.force_login(customer_user)
    resp = client.post(
        reverse("crm:ticket_create"),
        {
            "category": SupportTicket.Category.LOYALTY_DISPUTE,
            "subject": "Missing loyalty points from Tuesday book purchase",
            "description": "Purchased Discrete Mathematics textbook but points not credited.",
        },
    )
    assert resp.status_code == 302
    ticket = SupportTicket.objects.get(subject__icontains="Missing loyalty points")
    assert ticket.status == SupportTicket.Status.OPEN
    assert ticket.customer == customer_user.customer_profile
    assert ticket.ticket_code.startswith("TCK-")

    # Customer cannot directly update ticket status via staff endpoint
    blocked = client.post(
        reverse("crm:ticket_update", kwargs={"ticket_id": ticket.id}),
        {"status": SupportTicket.Status.RESOLVED, "resolution_note": "Self-resolved"},
    )
    assert blocked.status_code == 403

    # 2. Manager assigns ticket and moves it to In_Progress
    client.force_login(manager_user)
    resp2 = client.post(
        reverse("crm:ticket_update", kwargs={"ticket_id": ticket.id}),
        {
            "assigned_to": manager_user.id,
            "status": SupportTicket.Status.IN_PROGRESS,
            "resolution_note": "Reviewing POS receipt and loyalty ledger.",
        },
    )
    assert resp2.status_code == 302
    ticket.refresh_from_db()
    assert ticket.status == SupportTicket.Status.IN_PROGRESS
    assert ticket.assigned_to == manager_user

    # 3. Manager resolves the ticket with final resolution note
    resp3 = client.post(
        reverse("crm:ticket_update", kwargs={"ticket_id": ticket.id}),
        {
            "assigned_to": manager_user.id,
            "status": SupportTicket.Status.RESOLVED,
            "resolution_note": "Verified receipt and credited missing 58 loyalty points.",
        },
    )
    assert resp3.status_code == 302
    ticket.refresh_from_db()
    assert ticket.status == SupportTicket.Status.RESOLVED
    assert "58 loyalty points" in ticket.resolution_note


@pytest.mark.django_db
def test_customer_only_sees_own_tickets_in_queue(client, customer_user):
    other_customer = Customer.objects.create(
        cust_code="UIV-T99",
        full_name="Other Shopper",
        phone="08039990099",
        category=Customer.Category.PG,
    )
    own_ticket = SupportTicket.objects.create(
        customer=customer_user.customer_profile,
        category=SupportTicket.Category.PRODUCT_INQUIRY,
        subject="Own Inquiry Visible",
        description="Checking textbook stock.",
    )
    other_ticket = SupportTicket.objects.create(
        customer=other_customer,
        category=SupportTicket.Category.DAMAGED_ITEM,
        subject="Private Other Customer Ticket",
        description="Should not leak to other customer.",
    )

    client.force_login(customer_user)
    resp = client.get(reverse("crm:tickets"))
    html = resp.content.decode()
    assert resp.status_code == 200
    assert own_ticket.subject in html
    assert other_ticket.subject not in html
