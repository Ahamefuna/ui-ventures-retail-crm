"""Tests for authentication (Email & Staff Code) and role-based access control."""

import pytest
from django.urls import reverse

from crm.tests.conftest import TEST_PASSWORD


@pytest.mark.django_db
def test_login_supports_email_and_staff_code(client, manager_user):
    # Login with email
    resp = client.post(
        reverse("crm:login"),
        {"identifier": manager_user.email, "password": TEST_PASSWORD},
    )
    assert resp.status_code == 302
    assert resp.url == reverse("crm:dashboard")
    client.logout()

    # Login with staff_code
    resp = client.post(
        reverse("crm:login"),
        {"identifier": manager_user.staff_code, "password": TEST_PASSWORD},
    )
    assert resp.status_code == 302
    assert resp.url == reverse("crm:dashboard")


@pytest.mark.django_db
def test_customer_cannot_access_staff_or_manager_routes(client, customer_user):
    client.force_login(customer_user)

    forbidden_urls = [
        reverse("crm:dashboard"),
        reverse("crm:customers"),
        reverse("crm:pos"),
        reverse("crm:rfm"),
        reverse("crm:reports"),
        reverse("crm:products"),
        reverse("crm:staff"),
    ]
    for url in forbidden_urls:
        assert client.get(url).status_code == 403, f"Expected 403 for Customer on {url}"

    # Allowed customer self-service routes
    assert client.get(reverse("crm:my_portal")).status_code == 200
    assert client.get(reverse("crm:tickets")).status_code == 200


@pytest.mark.django_db
def test_attendant_blocked_from_admin_and_manager_only_routes(client, attendant_user):
    client.force_login(attendant_user)

    forbidden_urls = [
        reverse("crm:dashboard"),
        reverse("crm:rfm"),
        reverse("crm:reports"),
        reverse("crm:products"),
        reverse("crm:staff"),
        reverse("crm:my_portal"),
    ]
    for url in forbidden_urls:
        assert client.get(url).status_code == 403, f"Expected 403 for Attendant on {url}"

    # Allowed attendant routes
    assert client.get(reverse("crm:customers")).status_code == 200
    assert client.get(reverse("crm:pos")).status_code == 200
    assert client.get(reverse("crm:tickets")).status_code == 200


@pytest.mark.django_db
def test_manager_access_and_admin_only_staff_restriction(client, manager_user, admin_user):
    client.force_login(manager_user)
    for url in [
        reverse("crm:dashboard"),
        reverse("crm:customers"),
        reverse("crm:pos"),
        reverse("crm:rfm"),
        reverse("crm:reports"),
        reverse("crm:products"),
        reverse("crm:tickets"),
    ]:
        assert client.get(url).status_code == 200

    # Staff administration is strictly Admin-only
    assert client.get(reverse("crm:staff")).status_code == 403

    client.force_login(admin_user)
    assert client.get(reverse("crm:staff")).status_code == 200
