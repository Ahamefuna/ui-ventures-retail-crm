"""Shared pytest fixtures for UI Ventures Retail CRM tests."""

from decimal import Decimal
import pytest

from crm.models import Customer, Product, User

TEST_PASSWORD = "Password123!"


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        email="test.admin@uiventures.ui.edu.ng",
        password=TEST_PASSWORD,
        staff_code="UIV-TST-001",
        full_name="Test Admin",
        role=User.Role.ADMIN,
        is_staff=True,
    )


@pytest.fixture
def manager_user(db):
    return User.objects.create_user(
        email="test.manager@uiventures.ui.edu.ng",
        password=TEST_PASSWORD,
        staff_code="UIV-TST-002",
        full_name="Test Manager",
        role=User.Role.MANAGER,
        is_staff=True,
    )


@pytest.fixture
def attendant_user(db):
    return User.objects.create_user(
        email="test.attendant@uiventures.ui.edu.ng",
        password=TEST_PASSWORD,
        staff_code="UIV-TST-003",
        full_name="Test Attendant",
        role=User.Role.ATTENDANT,
    )


@pytest.fixture
def customer_user(db):
    user = User.objects.create_user(
        email="test.student@ui.edu.ng",
        password=TEST_PASSWORD,
        full_name="Tobi Adeyemi",
        role=User.Role.CUSTOMER,
    )
    Customer.objects.create(
        user=user,
        cust_code="UIV-T01",
        full_name=user.full_name,
        phone="08039990001",
        email=user.email,
        category=Customer.Category.UG,
        loyalty_points=500,
    )
    return user


@pytest.fixture
def sample_customer(customer_user):
    return customer_user.customer_profile


@pytest.fixture
def sample_products(db):
    p1 = Product.objects.create(
        sku_code="BK-T01",
        product_name="Algorithms Textbook",
        category=Product.Category.BOOKS,
        unit_price=Decimal("4000.00"),
        stock_qty=10,
        reorder_level=3,
    )
    p2 = Product.objects.create(
        sku_code="ST-T02",
        product_name="UI Exercise Book",
        category=Product.Category.STATIONERY,
        unit_price=Decimal("1000.00"),
        stock_qty=20,
        reorder_level=5,
    )
    return p1, p2
