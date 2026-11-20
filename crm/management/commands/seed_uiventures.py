"""Idempotent management command to seed realistic UI Ventures campus retail data."""

from datetime import timedelta
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
import random

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

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
    POINT_EARN_RATE,
    POINT_NAIRA_VALUE,
    calculate_max_redeemable_points,
    compute_rfm_segments,
)

DEMO_PASSWORD = "Password123!"

FIRST_NAMES = [
    "Oluwaseun", "Adebayo", "Chidinma", "Ibrahim", "Temitope", "Chukwuemeka",
    "Funmilayo", "Abdullahi", "Ngozi", "Babajide", "Aisha", "Olumide",
    "Kelechi", "Bukola", "Yusuf", "Ifeoma", "Damilola", "Sadiq",
    "Tolulope", "Uchenna", "Morenike", "Musa", "Amaka", "Tunde",
    "Zainab", "Gbenga", "Chisom", "Femi", "Hauwa", "Nnamdi",
    "Folake", "Kabiru", "Adaeze", "Segun", "Rukayat", "Obinna",
    "Omolara", "Usman", "Chioma", "Kayode", "Halima", "Chinedu",
    "Bolanle", "Aminu", "Ebele", "Rotimi", "Fatima", "Ikenna",
    "Simisola", "Bashir", "Nneka", "Wale", "Khadijat", "Somto",
    "Ayomide", "Jide", "Efe", "Osas", "Iniobong", "Edidiong",
]

LAST_NAMES = [
    "Adewale", "Ogunleye", "Okafor", "Mohammed", "Balogun", "Eze",
    "Oladipo", "Bello", "Nwosu", "Akinyemi", "Danladi", "Afolabi",
    "Okonkwo", "Suleiman", "Fashola", "Nwachukwu", "Ajayi", "Abubakar",
    "Oni", "Umeh", "Ojo", "Garba", "Chukwu", "Alabi",
    "Ibrahim", "Oyelakin", "Obi", "Lawal", "Madu", "Adeyemi",
    "Oseni", "Kalu", "Adediran", "Shehu", "Anyanwu", "Bakare",
    "Daramola", "Salisu", "Igwe", "Olatunji", "Yakubu", "Okeke",
    "Soyinka", "Bamidele", "Idowu", "Ekwueme", "Ogunbiyi", "Tijani",
    "Obasanjo", "Adegoke", "Okoro", "Ndukwe", "Akanbi", "Fagbemi",
    "Olabode", "Etim", "Okon", "Ighodaro", "Omoregie", "Bassey",
]

PHONE_PREFIXES = ["0803", "0805", "0806", "0810", "0813", "0814", "0816", "0703", "0706", "0903"]

# 85 authentic UI Ventures products across 5 categories
PRODUCT_CATALOG = [
    # Books (20 items)
    ("BK-101", "Introduction to Algorithms (CLRS 4th Ed.)", "Books", "8500.00", 42, 10),
    ("BK-102", "CSC 201 Structured Programming Lab Manual", "Books", "2200.00", 95, 20),
    ("BK-103", "Discrete Mathematics and Its Applications", "Books", "5800.00", 35, 10),
    ("BK-104", "Database System Concepts (UI Edition)", "Books", "6400.00", 28, 10),
    ("BK-105", "UI General Studies GES 101 Compendium", "Books", "2500.00", 140, 25),
    ("BK-106", "GES 107 Reproductive Health & Campus Ethics", "Books", "1800.00", 110, 20),
    ("BK-107", "Operating System Concepts Workbook", "Books", "4900.00", 30, 8),
    ("BK-108", "Software Engineering: A Practitioner's Approach", "Books", "6200.00", 24, 8),
    ("BK-109", "University Physics Vol. 1 (Mechanics & Waves)", "Books", "5500.00", 38, 10),
    ("BK-110", "Organic Chemistry Practical Laboratory Guide", "Books", "3100.00", 60, 15),
    ("BK-111", "Engineering Mathematics by K.A. Stroud", "Books", "7200.00", 8, 10),
    ("BK-112", "Principles of Economics (Nigerian Perspective)", "Books", "4400.00", 48, 12),
    ("BK-113", "Nigerian Constitutional Law & Jurisprudence", "Books", "5900.00", 26, 8),
    ("BK-114", "Human Anatomy Dissection Manual (UCH/UI)", "Books", "6800.00", 19, 8),
    ("BK-115", "Data Structures & Python Programming Guide", "Books", "3800.00", 54, 15),
    ("BK-116", "Statistical Inference & Probability Notes", "Books", "2900.00", 65, 15),
    ("BK-117", "Computer Networks & Security Handbook", "Books", "5100.00", 7, 10),
    ("BK-118", "Agricultural Economics & Extension Reader", "Books", "3400.00", 44, 10),
    ("BK-119", "Academic Writing & Research Methodology", "Books", "2700.00", 75, 15),
    ("BK-120", "Final Year Project Formatting & Citation Guide", "Books", "1500.00", 120, 25),
    # Stationery (20 items)
    ("ST-001", "UI Ventures 80-Leaf Higher Education Notebook", "Stationery", "850.00", 260, 40),
    ("ST-002", "UI Branded 60-Leaf Lecture Exercise Book", "Stationery", "600.00", 310, 50),
    ("ST-003", "A4 80gsm Double-A Printing Paper Ream", "Stationery", "5600.00", 45, 12),
    ("ST-004", "Bic Cristal Blue Ballpoint Pen (Pack of 10)", "Stationery", "1400.00", 120, 20),
    ("ST-005", "Casio FX-991EX Scientific Calculator", "Stationery", "9500.00", 9, 10),
    ("ST-006", "Oxford Mathematical Drawing Set", "Stationery", "1900.00", 80, 15),
    ("ST-007", "Hardcover Laboratory Observation Book", "Stationery", "1650.00", 90, 20),
    ("ST-008", "Spiral Bound A4 Project Sketchpad", "Stationery", "1450.00", 72, 15),
    ("ST-009", "Whiteboard Dry-Erase Marker Set (4 Colours)", "Stationery", "1300.00", 65, 15),
    ("ST-010", "Highlighter Pastel Set (5 Pieces)", "Stationery", "1550.00", 58, 12),
    ("ST-011", "Heavy-Duty Office Stapler + 1000 Pins", "Stationery", "2600.00", 36, 10),
    ("ST-012", "Clear Plastic Zip Document Wallet (A4)", "Stationery", "550.00", 180, 30),
    ("ST-013", "UI Crested Executive Hardcover Diary", "Stationery", "3900.00", 6, 10),
    ("ST-014", "Sticky Notes 3x3 Neon Cube (400 Sheets)", "Stationery", "1100.00", 95, 20),
    ("ST-015", "HB Graphite Drawing Pencils (Box of 12)", "Stationery", "1200.00", 85, 15),
    ("ST-016", "Spring Lever Arch Box File (A4)", "Stationery", "2100.00", 50, 12),
    ("ST-017", "Correction Fluid & Tape Twin Pack", "Stationery", "950.00", 105, 20),
    ("ST-018", "Stainless Steel 30cm Drafting Ruler", "Stationery", "700.00", 130, 25),
    ("ST-019", "Graph Paper Pad (2mm Engineering Grid)", "Stationery", "900.00", 140, 25),
    ("ST-020", "SanDisk 32GB USB 3.0 Flash Drive", "Stationery", "4800.00", 32, 10),
    # Bakery (18 items)
    ("BK-201", "UI Ventures Jumbo Sliced Bread (900g)", "Bakery", "1600.00", 150, 30),
    ("BK-202", "UI Ventures Special Butter Bread (700g)", "Bakery", "1350.00", 140, 25),
    ("BK-203", "UI Whole Wheat Diabetic Loaf", "Bakery", "1800.00", 60, 15),
    ("BK-204", "UI Ventures Coconut Swirl Loaf", "Bakery", "1750.00", 55, 15),
    ("BK-205", "Freshly Baked Beef Meat Pie", "Bakery", "800.00", 180, 35),
    ("BK-206", "Flaky Chicken Pie", "Bakery", "900.00", 130, 25),
    ("BK-207", "Golden Sausage Roll", "Bakery", "650.00", 160, 30),
    ("BK-208", "Glazed Jam Doughnut", "Bakery", "550.00", 140, 25),
    ("BK-209", "Crunchy UI Chin-Chin Jar (350g)", "Bakery", "1400.00", 90, 20),
    ("BK-210", "Spiced Plantain Chips Pouch (150g)", "Bakery", "750.00", 125, 25),
    ("BK-211", "UI Ventures Sponge Cake Slice", "Bakery", "950.00", 85, 20),
    ("BK-212", "Red Velvet Cupcake Twin Pack", "Bakery", "1200.00", 70, 15),
    ("BK-213", "Baked Scotch Egg", "Bakery", "850.00", 95, 20),
    ("BK-214", "UI Chocolate Chip Muffin", "Bakery", "700.00", 110, 20),
    ("BK-215", "Family Celebration Fruit Cake (1kg)", "Bakery", "6500.00", 5, 8),
    ("BK-216", "Sweet Dinner Rolls (Pack of 6)", "Bakery", "1100.00", 100, 20),
    ("BK-217", "Peanut Burger Bottle (250g)", "Bakery", "1250.00", 80, 15),
    ("BK-218", "Shortbread Butter Biscuits Box", "Bakery", "1500.00", 75, 15),
    # Beverages (15 items)
    ("BV-001", "UI Ventures Table Water (75cl Bottle)", "Beverages", "300.00", 500, 80),
    ("BV-002", "UI Ventures Table Water Pack (12 x 75cl)", "Beverages", "2800.00", 95, 20),
    ("BV-003", "Chilled Hibiscus Zobo Drink (50cl)", "Beverages", "600.00", 160, 30),
    ("BV-004", "Fresh Tiger Nut Milk (Kunu Aya 50cl)", "Beverages", "950.00", 90, 20),
    ("BV-005", "UI Dairy Sweetened Yoghurt (50cl)", "Beverages", "1100.00", 110, 25),
    ("BV-006", "Maltina Classic Can (33cl)", "Beverages", "650.00", 200, 40),
    ("BV-007", "Chivita 100% Orange Juice (1 Litre)", "Beverages", "1950.00", 70, 15),
    ("BV-008", "Hollandia Plain Yoghurt (1 Litre)", "Beverages", "2200.00", 65, 15),
    ("BV-009", "Nescafe 3-in-1 Coffee Sachet Pack (10s)", "Beverages", "2400.00", 80, 15),
    ("BV-010", "Milo Chocolate Malt Refill (400g)", "Beverages", "3600.00", 48, 12),
    ("BV-011", "Peak Evaporated Milk Tin (160g)", "Beverages", "850.00", 140, 25),
    ("BV-012", "Lipton Yellow Label Tea (25 Bags)", "Beverages", "1200.00", 95, 20),
    ("BV-013", "Five Alive Pulpy Citrus (85cl)", "Beverages", "1300.00", 115, 25),
    ("BV-014", "Cold Brew Iced Coffee Bottle (35cl)", "Beverages", "1250.00", 9, 12),
    ("BV-015", "Coca-Cola PET Bottle (50cl)", "Beverages", "450.00", 260, 50),
    # Consumables (12 items)
    ("CN-001", "Pocket Facial Tissue Pack (10s)", "Consumables", "900.00", 130, 25),
    ("CN-002", "Antibacterial Hand Sanitizer (250ml)", "Consumables", "1450.00", 85, 20),
    ("CN-003", "UI Branded Insulated Thermal Flask (500ml)", "Consumables", "5200.00", 28, 8),
    ("CN-004", "UI Ventures Cotton Tote Shopping Bag", "Consumables", "1600.00", 95, 20),
    ("CN-005", "Alkaline AA Batteries (Pack of 4)", "Consumables", "1350.00", 75, 15),
    ("CN-006", "Multi-Purpose Disinfectant Wipes (80s)", "Consumables", "1750.00", 64, 15),
    ("CN-007", "UI 75th Anniversary Ceramic Coffee Mug", "Consumables", "2900.00", 7, 10),
    ("CN-008", "White Cotton Laboratory Coat (Medium/Large)", "Consumables", "6800.00", 34, 10),
    ("CN-009", "Reusable BPA-Free Campus Water Bottle (1L)", "Consumables", "2400.00", 52, 12),
    ("CN-010", "Compact Folding Rain Umbrella (UI Navy)", "Consumables", "4200.00", 8, 10),
    ("CN-011", "Microfiber Laptop & Screen Cleaning Kit", "Consumables", "1850.00", 46, 10),
    ("CN-012", "UI Lanyard & Transparent Student ID Holder", "Consumables", "750.00", 210, 40),
]

TICKET_TEMPLATES = [
    ("Product Inquiry", "Availability of CLRS 4th Edition at Main Bookshop", "Checked the Kenneth Dike wing yesterday and wanted to confirm if additional copies of Introduction to Algorithms have been restocked.", "Open", ""),
    ("Loyalty Dispute", "Points not reflected for bakery bulk order", "Purchased 15 loaves of UI Ventures Jumbo Bread for our departmental seminar using POS transfer, but points did not show immediately.", "Open", ""),
    ("Damaged Item", "Cracked cover on Engineering Mathematics textbook", "Noticed the spine binding separated shortly after unboxing the textbook bought on Tuesday.", "Open", ""),
    ("Service Feedback", "Faster checkout queue at Queen Idia mini-mart", "The new digital POS terminal has reduced lunch-hour wait times significantly. Thank you to the attendants.", "Resolved", "Feedback logged and shared with the mini-mart operations supervisor."),
    ("Product Inquiry", "Bulk quote for 50 laboratory coats (Faculty of Science)", "We need 50 medium and large white lab coats for 200-level Chemistry practicals next Monday.", "In_Progress", "Quotation drafted; verifying warehouse inventory count before confirming pickup."),
    ("Loyalty Dispute", "Clarification on 50% point redemption threshold", "Tried redeeming 400 points on a ₦3,000 purchase and the attendant explained the 50% cap. Seeking confirmation on remaining balance.", "Resolved", "Explained the ₦10/point valuation and 50% gross cap policy; balance confirmed intact."),
    ("Damaged Item", "Leaking seal on 12-pack UI Table Water", "Two bottles in the shrink-wrapped pack had loose caps upon delivery to Mellanby Hall.", "In_Progress", "Replacement pack scheduled for pickup at the Main Gate depot."),
    ("Service Feedback", "Suggestion to stock USB-C laptop adapters", "Many Computer Science students look for Type-C hubs and adapters during project defense week.", "Open", ""),
    ("Product Inquiry", "Restock date for UI Crested Executive Diary", "Planning to order 12 diaries for visiting external examiners from Lagos.", "In_Progress", "Printing press confirmed next batch arrives Friday morning."),
    ("Loyalty Dispute", "Duplicate phone number preventing profile lookup", "Changed my phone line last semester and my old UIV code points are still tied to the previous line.", "Resolved", "Verified student ID and merged customer profile contact details safely."),
    ("Damaged Item", "Defective Casio FX-991EX display contrast", "Calculator bought two days ago displays faint digits even under bright light.", "Resolved", "Inspected device under 7-day warranty and issued a fresh sealed replacement."),
    ("Service Feedback", "Freshness of UI Ventures Whole Wheat Bread", "Appreciate the consistent morning baking schedule; the whole wheat loaves are always fresh by 8:30 AM.", "Resolved", "Commendation forwarded to the UI Ventures Bakery production team."),
    ("Product Inquiry", "Pre-order inquiry for GES 101 Compendium", "Can freshmen pay upfront and collect with their digital receipt at the bookstore annex?", "Open", ""),
    ("Loyalty Dispute", "Points balance query after receipt cancellation", "Requesting an audit statement of my last three transactions and associated loyalty point deltas.", "In_Progress", "Exported LoyaltyLedger statement and reviewing with store manager."),
    ("Service Feedback", "Extend Friday evening closing hours to 7 PM", "Postgraduate students returning from evening labs would benefit from an extra hour at the stationery kiosk.", "Open", ""),
]


class Command(BaseCommand):
    help = "Idempotently seed UI Ventures Retail CRM with demo users, 420 customers, 85 products, 1,850 transactions, 15 tickets, and live RFM segments."

    def handle(self, *args, **options):
        rng = random.Random(222026)

        with transaction.atomic():
            users = self._seed_users()
            products = self._seed_products()
            customers = self._seed_customers(rng, users["customer"])
            txn_created = self._seed_transactions(rng, customers, products, users["attendants"])
            tickets_created = self._seed_tickets(customers, users["attendants"])

        rfm_count = compute_rfm_segments()

        total_rev = sum(
            Transaction.objects.values_list("net_amount", flat=True),
            Decimal("0.00"),
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"UI Ventures CRM seed complete | "
                f"Customers: {Customer.objects.count()} | "
                f"Products: {Product.objects.count()} | "
                f"Transactions: {Transaction.objects.count()} (new: {txn_created}) | "
                f"Revenue: NGN {total_rev:,.2f} | "
                f"RFM Segments: {rfm_count} | "
                f"Support Tickets: {SupportTicket.objects.count()} (new: {tickets_created})"
            )
        )

    def _seed_users(self):
        accounts = [
            ("admin@uiventures.ui.edu.ng", "UIV-STF-001", "Dr. Olufemi Adeyinka", User.Role.ADMIN, True, True),
            ("manager@uiventures.ui.edu.ng", "UIV-STF-002", "Mrs. Folashade Oguntimehin", User.Role.MANAGER, True, False),
            ("attendant@uiventures.ui.edu.ng", "UIV-STF-003", "Mr. Tobi Adekunle", User.Role.ATTENDANT, False, False),
            ("bookshop.attendant@uiventures.ui.edu.ng", "UIV-STF-004", "Miss Chiamaka Nwankwo", User.Role.ATTENDANT, False, False),
            ("bakery.attendant@uiventures.ui.edu.ng", "UIV-STF-005", "Mr. Sulaimon Rasheed", User.Role.ATTENDANT, False, False),
            ("student@ui.edu.ng", None, "Adebayo Oluwaseun", User.Role.CUSTOMER, False, False),
        ]

        created_map = {}
        for email, staff_code, full_name, role, is_staff, is_superuser in accounts:
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "staff_code": staff_code,
                    "full_name": full_name,
                    "role": role,
                    "is_staff": is_staff,
                    "is_superuser": is_superuser,
                    "is_active": True,
                },
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save()
            created_map[email] = user

        return {
            "admin": created_map["admin@uiventures.ui.edu.ng"],
            "manager": created_map["manager@uiventures.ui.edu.ng"],
            "attendants": [
                created_map["attendant@uiventures.ui.edu.ng"],
                created_map["bookshop.attendant@uiventures.ui.edu.ng"],
                created_map["bakery.attendant@uiventures.ui.edu.ng"],
                created_map["manager@uiventures.ui.edu.ng"],
            ],
            "customer": created_map["student@ui.edu.ng"],
        }

    def _seed_products(self):
        products = []
        for sku, name, cat, price, stock, reorder in PRODUCT_CATALOG:
            prod, _ = Product.objects.get_or_create(
                sku_code=sku,
                defaults={
                    "product_name": name,
                    "category": cat,
                    "unit_price": Decimal(price),
                    "stock_qty": stock,
                    "reorder_level": reorder,
                },
            )
            products.append(prod)
        return products

    def _seed_customers(self, rng, demo_customer_user):
        # Guarantee UIV-001 is linked to demo customer student@ui.edu.ng
        demo_cust, _ = Customer.objects.get_or_create(
            cust_code="UIV-001",
            defaults={
                "user": demo_customer_user,
                "full_name": demo_customer_user.full_name,
                "phone": "08031000001",
                "email": demo_customer_user.email,
                "category": Customer.Category.UG,
                "loyalty_points": 0,
            },
        )
        if demo_cust.user_id != demo_customer_user.id:
            demo_cust.user = demo_customer_user
            demo_cust.save(update_fields=["user"])

        existing_codes = set(Customer.objects.values_list("cust_code", flat=True))
        existing_phones = set(Customer.objects.values_list("phone", flat=True))

        category_pool = (
            [Customer.Category.UG] * 50
            + [Customer.Category.PG] * 20
            + [Customer.Category.ACADEMIC] * 12
            + [Customer.Category.NON_TEACHING] * 11
            + [Customer.Category.VISITOR] * 7
        )

        to_create = []
        for idx in range(2, 421):
            code = f"UIV-{idx:03d}"
            if code in existing_codes:
                continue

            first = rng.choice(FIRST_NAMES)
            last = rng.choice(LAST_NAMES)
            full_name = f"{first} {last}"
            cat = rng.choice(category_pool)

            prefix = PHONE_PREFIXES[idx % len(PHONE_PREFIXES)]
            phone = f"{prefix}{1000000 + idx * 17:07d}"
            while phone in existing_phones:
                phone = f"{prefix}{rng.randint(1000000, 9999999)}"
            existing_phones.add(phone)

            domain = "stu.ui.edu.ng" if cat in {Customer.Category.UG, Customer.Category.PG} else "ui.edu.ng"
            email = f"{first.lower()}.{last.lower()}{idx}@{domain}"

            to_create.append(
                Customer(
                    cust_code=code,
                    full_name=full_name,
                    phone=phone,
                    email=email,
                    category=cat,
                    loyalty_points=0,
                )
            )

        if to_create:
            Customer.objects.bulk_create(to_create)

        return list(Customer.objects.order_by("cust_code")[:420])

    def _seed_transactions(self, rng, customers, products, attendants):
        target_total = 1850
        existing_count = Transaction.objects.count()
        if existing_count >= target_total:
            return 0

        now = timezone.now()
        # Partition 420 customers into 4 behavioral archetypes so RFM tiers are naturally well-balanced:
        # 0..84 (85): Champions — frequent (7-12 txns), recent (0-20d), higher basket
        # 85..189 (105): Loyal — regular (4-7 txns), recent-mid (5-45d), solid basket
        # 190..289 (100): Potential Loyalists — recent (1-30d), low frequency (1-2 txns)
        # 290..419 (130): At-Risk / Dormant — older last visit (70-175d), 1-4 txns
        plan_counts = []
        for i in range(len(customers)):
            if i < 85:
                plan_counts.append(rng.randint(7, 11))
            elif i < 190:
                plan_counts.append(rng.randint(4, 6))
            elif i < 290:
                plan_counts.append(rng.randint(1, 2))
            else:
                plan_counts.append(rng.randint(1, 3))

        # Calibrate total transaction count to exactly 1,850
        diff = target_total - sum(plan_counts)
        idx = 0
        while diff != 0:
            if diff > 0:
                target_idx = idx % 190
                plan_counts[target_idx] += 1
                diff -= 1
            else:
                target_idx = idx % len(plan_counts)
                if plan_counts[target_idx] > 1:
                    plan_counts[target_idx] -= 1
                    diff += 1
            idx += 1

        # Build chronological transaction schedule
        high_value_products = [p for p in products if p.unit_price >= Decimal("2200.00")]
        mid_value_products = [
            p for p in products if Decimal("900.00") <= p.unit_price < Decimal("2200.00")
        ]
        everyday_products = [p for p in products if p.unit_price < Decimal("1800.00")]

        scheduled = []
        for cust_idx, (cust, n_txns) in enumerate(zip(customers, plan_counts)):
            if cust_idx < 85:
                # Champions: at least one very recent purchase, others across 180 days
                days_list = [rng.randint(0, 14)] + [rng.randint(1, 165) for _ in range(n_txns - 1)]
                tier_profile = "champion"
            elif cust_idx < 190:
                days_list = [rng.randint(5, 38)] + [rng.randint(10, 175) for _ in range(n_txns - 1)]
                tier_profile = "loyal"
            elif cust_idx < 290:
                days_list = [rng.randint(1, 28)] + [rng.randint(2, 45) for _ in range(n_txns - 1)]
                tier_profile = "potential"
            else:
                days_list = [rng.randint(75, 178) for _ in range(n_txns)]
                tier_profile = "dormant"

            for d_ago in days_list:
                dt = now - timedelta(
                    days=d_ago,
                    hours=rng.randint(8, 18),
                    minutes=rng.randint(0, 59),
                )
                scheduled.append((dt, cust, tier_profile))

        # Sort chronologically so loyalty balances & ledger audit trails are 100% accurate
        scheduled.sort(key=lambda x: x[0])

        loyalty_bal = {c.id: c.loyalty_points for c in customers}
        txn_items_bulk = []
        ledger_bulk = []
        pay_methods = ["POS", "TRF", "CSH"]

        for seq, (txn_dt, cust, profile) in enumerate(scheduled, start=1):
            # Calibrated campus basket mix yielding ~₦4.8M total revenue across 1,850 txns
            roll = rng.random()
            if profile == "champion":
                if roll < 0.28:
                    chosen_prods = [rng.choice(high_value_products)]
                elif roll < 0.72:
                    chosen_prods = rng.sample(mid_value_products, k=2)
                else:
                    chosen_prods = rng.sample(everyday_products, k=2)
            elif profile == "loyal":
                if roll < 0.18:
                    chosen_prods = [rng.choice(high_value_products)]
                elif roll < 0.62:
                    chosen_prods = rng.sample(mid_value_products, k=2)
                else:
                    chosen_prods = rng.sample(everyday_products, k=2)
            else:
                if roll < 0.08:
                    chosen_prods = [rng.choice(high_value_products)]
                elif roll < 0.48:
                    chosen_prods = [rng.choice(mid_value_products)]
                else:
                    chosen_prods = rng.sample(everyday_products, k=rng.choice([1, 2]))

            gross = Decimal("0.00")
            line_records = []
            for p in chosen_prods:
                qty = 1 if p.unit_price >= Decimal("1500.00") else rng.choice([1, 1, 2])
                sub = (p.unit_price * qty).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                gross += sub
                line_records.append((p, qty, p.unit_price, sub))

            # Occasionally redeem loyalty points when customer has >= 20 pts
            current_pts = loyalty_bal[cust.id]
            redeem_pts = 0
            if current_pts >= 20 and rng.random() < 0.22:
                max_pts = calculate_max_redeemable_points(current_pts, gross)
                if max_pts >= 10:
                    redeem_pts = rng.randint(10, min(max_pts, 80))

            discount = (Decimal(redeem_pts) * POINT_NAIRA_VALUE).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            net = (gross - discount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            receipt_no = f"UIV-{txn_dt.strftime('%Y%m%d')}-{seq:04d}"
            pay_ref = f"{rng.choice(pay_methods)}-{txn_dt.strftime('%y%m%d')}-{seq:04d}"

            txn = Transaction.objects.create(
                receipt_no=receipt_no,
                customer=cust,
                attended_by=rng.choice(attendants),
                gross_amount=gross,
                discount_amount=discount,
                net_amount=net,
                payment_ref=pay_ref,
                txn_date=txn_dt,
            )

            for p, qty, unit_price, sub in line_records:
                txn_items_bulk.append(
                    TransactionItem(
                        transaction=txn,
                        product=p,
                        quantity=qty,
                        unit_price_at_sale=unit_price,
                        line_subtotal=sub,
                    )
                )

            if redeem_pts > 0:
                current_pts -= redeem_pts
                ledger_bulk.append(
                    LoyaltyLedger(
                        customer=cust,
                        transaction=txn,
                        action_type=LoyaltyLedger.ActionType.REDEEM,
                        points_delta=-redeem_pts,
                        balance_after=current_pts,
                        recorded_at=txn_dt,
                    )
                )

            earned_pts = int(
                (net * POINT_EARN_RATE).to_integral_value(rounding=ROUND_FLOOR)
            )
            if earned_pts > 0:
                current_pts += earned_pts
                ledger_bulk.append(
                    LoyaltyLedger(
                        customer=cust,
                        transaction=txn,
                        action_type=LoyaltyLedger.ActionType.EARN,
                        points_delta=earned_pts,
                        balance_after=current_pts,
                        recorded_at=txn_dt,
                    )
                )

            loyalty_bal[cust.id] = current_pts

        TransactionItem.objects.bulk_create(txn_items_bulk, batch_size=500)
        LoyaltyLedger.objects.bulk_create(ledger_bulk, batch_size=500)

        for c in customers:
            c.loyalty_points = loyalty_bal[c.id]
        Customer.objects.bulk_update(customers, ["loyalty_points"], batch_size=200)

        return len(scheduled)

    def _seed_tickets(self, customers, attendants):
        if SupportTicket.objects.count() >= len(TICKET_TEMPLATES):
            return 0

        created = 0
        for idx, (cat, subject, desc, status, note) in enumerate(TICKET_TEMPLATES):
            ticket_code = f"TCK-{101 + idx:03d}"
            if SupportTicket.objects.filter(ticket_code=ticket_code).exists():
                continue

            # Assign first 2 tickets to UIV-001 (student@ui.edu.ng) for portal visibility
            cust = customers[0] if idx in {0, 5} else customers[(idx * 19) % len(customers)]
            assigned = attendants[idx % len(attendants)] if status != "Open" else None

            SupportTicket.objects.create(
                ticket_code=ticket_code,
                customer=cust,
                assigned_to=assigned,
                category=cat,
                subject=subject,
                description=desc,
                status=status,
                resolution_note=note,
            )
            created += 1

        return created
