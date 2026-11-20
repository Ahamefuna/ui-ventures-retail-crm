"""Core 3NF relational models for the UI Ventures Retail CRM System."""

from decimal import Decimal
import uuid

from django.conf import settings
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    """Custom manager using email as the unique login identifier."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("role", User.Role.CUSTOMER)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.Role.ADMIN)
        extra_fields.setdefault("full_name", "System Administrator")

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """Custom user supporting staff roles and customer self-service accounts."""

    class Role(models.TextChoices):
        ADMIN = "Admin", "Admin"
        MANAGER = "Manager", "Manager"
        ATTENDANT = "Attendant", "Attendant"
        CUSTOMER = "Customer", "Customer"

    username = None
    staff_code = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text="Unique institutional staff code (blank for customer accounts).",
    )
    full_name = models.CharField(max_length=150)
    email = models.EmailField(unique=True, db_index=True)
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CUSTOMER,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    objects = UserManager()

    class Meta:
        db_table = "crm_user"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["role", "is_active"]),
        ]

    def __str__(self):
        return f"{self.full_name} ({self.role})"

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    @property
    def is_manager_or_admin(self):
        return self.role in {self.Role.ADMIN, self.Role.MANAGER} or self.is_superuser

    @property
    def is_staff_member(self):
        return self.role in {
            self.Role.ADMIN,
            self.Role.MANAGER,
            self.Role.ATTENDANT,
        } or self.is_superuser


class Customer(models.Model):
    """Registered UI Ventures customer profile and loyalty balance."""

    class Category(models.TextChoices):
        UG = "UG", "Undergraduate (UG)"
        PG = "PG", "Postgraduate (PG)"
        ACADEMIC = "Academic", "Academic Staff"
        NON_TEACHING = "Non-Teaching", "Non-Teaching Staff"
        VISITOR = "Visitor", "Campus Visitor"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_profile",
    )
    cust_code = models.CharField(max_length=20, unique=True, db_index=True)
    full_name = models.CharField(max_length=150, db_index=True)
    phone = models.CharField(max_length=20, unique=True, db_index=True)
    email = models.EmailField(blank=True, default="")
    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        default=Category.UG,
        db_index=True,
    )
    loyalty_points = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "crm_customer"
        ordering = ["cust_code"]
        indexes = [
            models.Index(fields=["category", "loyalty_points"]),
        ]

    def save(self, *args, **kwargs):
        if not self.cust_code:
            last = Customer.objects.order_by("-id").first()
            next_num = (last.id + 1) if last else 1
            candidate = f"UIV-{next_num:03d}"
            while Customer.objects.filter(cust_code=candidate).exists():
                next_num += 1
                candidate = f"UIV-{next_num:03d}"
            self.cust_code = candidate
        super().save(*args, **kwargs)

    @property
    def loyalty_naira_value(self):
        return Decimal(self.loyalty_points) * Decimal("10.00")

    def __str__(self):
        return f"{self.cust_code} — {self.full_name}"


class Product(models.Model):
    """Retail catalog item stocked across UI Ventures campus outlets."""

    class Category(models.TextChoices):
        BOOKS = "Books", "Books"
        STATIONERY = "Stationery", "Stationery"
        BAKERY = "Bakery", "Bakery"
        BEVERAGES = "Beverages", "Beverages"
        CONSUMABLES = "Consumables", "Consumables"

    sku_code = models.CharField(max_length=20, unique=True, db_index=True)
    product_name = models.CharField(max_length=180, db_index=True)
    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        db_index=True,
    )
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    stock_qty = models.PositiveIntegerField(default=0)
    reorder_level = models.PositiveIntegerField(default=10)

    class Meta:
        db_table = "crm_product"
        ordering = ["category", "product_name"]
        indexes = [
            models.Index(fields=["category", "stock_qty"]),
        ]

    @property
    def is_low_stock(self):
        return self.stock_qty <= self.reorder_level

    def __str__(self):
        return f"{self.sku_code} — {self.product_name}"


class Transaction(models.Model):
    """Completed POS sales transaction header."""

    receipt_no = models.CharField(max_length=32, unique=True, db_index=True, blank=True)
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="transactions",
    )
    attended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="attended_transactions",
    )
    gross_amount = models.DecimalField(max_digits=10, decimal_places=2)
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    net_amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_ref = models.CharField(max_length=64, db_index=True)
    txn_date = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = "crm_transaction"
        ordering = ["-txn_date"]
        indexes = [
            models.Index(fields=["customer", "txn_date"]),
            models.Index(fields=["txn_date", "net_amount"]),
        ]

    def save(self, *args, **kwargs):
        if not self.receipt_no:
            stamp = (self.txn_date or timezone.now()).strftime("%Y%m%d")
            suffix = uuid.uuid4().hex[:6].upper()
            self.receipt_no = f"UIV-{stamp}-{suffix}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.receipt_no} (₦{self.net_amount:,.2f})"


class TransactionItem(models.Model):
    """Individual line item belonging to a retail transaction."""

    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.CASCADE,
        related_name="items",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="transaction_items",
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price_at_sale = models.DecimalField(max_digits=10, decimal_places=2)
    line_subtotal = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = "crm_transaction_item"
        indexes = [
            models.Index(fields=["transaction", "product"]),
        ]

    def __str__(self):
        return f"{self.product.sku_code} x{self.quantity} ({self.transaction.receipt_no})"


class LoyaltyLedger(models.Model):
    """Immutable audit log of loyalty point accruals, redemptions, and adjustments."""

    class ActionType(models.TextChoices):
        EARN = "EARN", "Earn"
        REDEEM = "REDEEM", "Redeem"
        ADJUST = "ADJUST", "Adjustment"

    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="loyalty_entries",
    )
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="loyalty_entries",
    )
    action_type = models.CharField(
        max_length=10,
        choices=ActionType.choices,
        db_index=True,
    )
    points_delta = models.IntegerField()
    balance_after = models.IntegerField()
    recorded_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = "crm_loyalty_ledger"
        ordering = ["-recorded_at", "-id"]
        indexes = [
            models.Index(fields=["customer", "recorded_at"]),
            models.Index(fields=["action_type", "recorded_at"]),
        ]

    def __str__(self):
        sign = "+" if self.points_delta >= 0 else ""
        return f"{self.customer.cust_code} {self.action_type} {sign}{self.points_delta} (Bal: {self.balance_after})"


class RFMSegment(models.Model):
    """Quintile-based Recency, Frequency, and Monetary segmentation record."""

    class TierLabel(models.TextChoices):
        CHAMPIONS = "Champions", "Champions"
        LOYAL = "Loyal Customers", "Loyal Customers"
        POTENTIAL = "Potential Loyalists", "Potential Loyalists"
        AT_RISK = "At-Risk / Dormant", "At-Risk / Dormant"

    RECOMMENDED_ACTIONS = {
        TierLabel.CHAMPIONS: "Reward with VIP bookshop preview, priority bakery orders, and exclusive loyalty bonus.",
        TierLabel.LOYAL: "Offer semester stationery bundles and tiered referral incentives to grow them into Champions.",
        TierLabel.POTENTIAL: "Send targeted welcome-back discount coupons and highlight point redemption benefits.",
        TierLabel.AT_RISK: "Dispatch win-back retention alert with time-limited bonus points on next campus visit.",
    }

    customer = models.OneToOneField(
        Customer,
        on_delete=models.CASCADE,
        related_name="rfm_segment",
    )
    recency_days = models.IntegerField()
    frequency_count = models.IntegerField()
    monetary_total = models.DecimalField(max_digits=12, decimal_places=2)
    r_score = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    f_score = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    m_score = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    tier_label = models.CharField(
        max_length=32,
        choices=TierLabel.choices,
        db_index=True,
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "crm_rfm_segment"
        ordering = ["-monetary_total"]
        indexes = [
            models.Index(fields=["tier_label", "monetary_total"]),
        ]

    @property
    def rfm_code(self):
        return f"{self.r_score}{self.f_score}{self.m_score}"

    @property
    def recommended_action(self):
        return self.RECOMMENDED_ACTIONS.get(self.tier_label, "Monitor purchase cadence.")

    def __str__(self):
        return f"{self.customer.cust_code} [{self.rfm_code}] — {self.tier_label}"


class SupportTicket(models.Model):
    """Customer inquiry, dispute, feedback, and damaged item support ticket."""

    class Category(models.TextChoices):
        PRODUCT_INQUIRY = "Product Inquiry", "Product Inquiry"
        LOYALTY_DISPUTE = "Loyalty Dispute", "Loyalty Dispute"
        SERVICE_FEEDBACK = "Service Feedback", "Service Feedback"
        DAMAGED_ITEM = "Damaged Item", "Damaged Item"

    class Status(models.TextChoices):
        OPEN = "Open", "Open"
        IN_PROGRESS = "In_Progress", "In Progress"
        RESOLVED = "Resolved", "Resolved"

    ticket_code = models.CharField(max_length=20, unique=True, db_index=True, blank=True)
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="support_tickets",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_tickets",
    )
    category = models.CharField(
        max_length=32,
        choices=Category.choices,
        db_index=True,
    )
    subject = models.CharField(max_length=200)
    description = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
        db_index=True,
    )
    resolution_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "crm_support_ticket"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "category"]),
            models.Index(fields=["customer", "status"]),
        ]

    def save(self, *args, **kwargs):
        if not self.ticket_code:
            last = SupportTicket.objects.order_by("-id").first()
            next_num = (last.id + 101) if last else 101
            candidate = f"TCK-{next_num:03d}"
            while SupportTicket.objects.filter(ticket_code=candidate).exists():
                next_num += 1
                candidate = f"TCK-{next_num:03d}"
            self.ticket_code = candidate
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.ticket_code} — {self.subject} ({self.get_status_display()})"
