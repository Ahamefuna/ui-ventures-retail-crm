# UI Ventures Retail CRM System

**Department of Computer Science, University of Ibadan — Group 22 Final Year Project**

A full-stack institutional Retail Customer Relationship Management (CRM), Loyalty Engine, and Automated Quintile-Based RFM Analytics platform designed for **UI Ventures Limited**, University of Ibadan (Bookshop, Stationery, Bakery, Beverages, and Campus Consumables outlets).

---

## System Architecture

The system follows a three-tier client-server architecture built with Django (Model-View-Template):

- **Presentation Layer:** Responsive HTML5, CSS3, Bootstrap 5, vanilla JavaScript (interactive POS checkout), and Chart.js (revenue and RFM visualizations).
- **Application & Analytics Layer:** Python 3.11+ / Django 5.2 with atomic transaction services (`crm/services.py`), role-based access control decorators (`crm/decorators.py`), and `pandas`/`numpy` quintile-based RFM segmentation.
- **Data Persistence Layer:** Strict Third Normal Form (3NF) 8-table relational schema targeting **MySQL 8.0** via environment variables (`USE_MYSQL=True`), with zero-configuration **SQLite (`db.sqlite3`)** fallback (`USE_MYSQL=False`) for local development and evaluation.

### Core Modules
1. **Role-Based Authentication (`/login/`, `/logout/`)** — Supports institutional Email or Staff Code login with PBKDF2 password hashing and strict 403 RBAC isolation.
2. **Executive Analytical Dashboard (`/dashboard/`)** — KPI summaries, 6-month revenue bar chart, RFM distribution doughnut chart, Top 5 RFM Champions, and low-stock watch.
3. **Customer Directory & 360° Profiles (`/customers/`)** — Live search/filter by name, phone, code, category, or RFM tier, with full purchase history, loyalty ledger, RFM scores, and support tickets.
4. **POS Checkout & Digital Receipts (`/pos/`, `/receipt/<id>/`)** — Atomic inventory validation/deduction, 1% loyalty accrual (1 pt per ₦100 net spend), 50%-capped point redemption (1 pt = ₦10), and printable receipts.
5. **RFM Segmentation & Retention Campaigns (`/rfm/`)** — Live quintile recomputation (`Champions`, `Loyal Customers`, `Potential Loyalists`, `At-Risk / Dormant`), quintile matrix, and auditable retention alert dispatch.
6. **Support Ticket & Feedback Portal (`/tickets/`)** — End-to-end ticket lifecycle (`Open` → `In Progress` → `Resolved`) with staff assignment, resolution notes, and customer ticket isolation.
7. **Analytical Reports & CSV Exports (`/reports/`)** — Date-range and category sales analytics, RFM tier revenue breakdown, and one-click CSV downloads.
8. **Product Catalog & Staff Administration (`/products/`, `/staff/`)** — Inventory CRUD with reorder alerts and Admin staff role management.
9. **Customer Self-Service Portal (`/my-portal/`)** — Dedicated portal for registered campus customers to check loyalty points, download/print receipts, and track support tickets.

---

## Installation & Setup

### 1. Create and Activate Virtual Environment
```bash
python -m venv venv
# Windows (PowerShell)
.\venv\Scripts\Activate.ps1
# Linux / macOS
source venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables (Optional)
By default, the system runs locally on SQLite (`USE_MYSQL=False`) with zero external database setup. To connect to MySQL 8.0, copy `.env.example` to `.env` and set `USE_MYSQL=True` along with your MySQL credentials:
```bash
cp .env.example .env
```

### 4. Apply Migrations & Seed Institutional Dataset
```bash
python manage.py makemigrations
python manage.py migrate
python manage.py seed_uiventures
```
The idempotent `seed_uiventures` command populates:
- 6 demo staff & customer accounts
- 420 realistic Nigerian campus customers (`UG`, `PG`, `Academic`, `Non-Teaching`, `Visitor`)
- 85 UI Ventures retail products across 5 categories
- 1,850 itemized transactions spread over 6 months with accurate `LoyaltyLedger` records
- Live quintile RFM scores across all 420 customers
- 15 support tickets across `Open`, `In Progress`, and `Resolved` states

### 5. Run the Development Server
```bash
python manage.py runserver
```
Open `http://127.0.0.1:8000/login/` in your browser.

---

## Demo Login Credentials

All seeded demo accounts use the password **`Password123!`**:

| Role | Email Address | Staff Code | Default Workspace |
| :--- | :--- | :--- | :--- |
| **Admin** | `admin@uiventures.ui.edu.ng` | `UIV-STF-001` | `/dashboard/` |
| **Store Manager** | `manager@uiventures.ui.edu.ng` | `UIV-STF-002` | `/dashboard/` |
| **Sales Attendant** | `attendant@uiventures.ui.edu.ng` | `UIV-STF-003` | `/pos/` |
| **Customer (Student)** | `student@ui.edu.ng` | — | `/my-portal/` |

---

## Running Automated Tests

Execute the full `pytest` unit and integration suite:
```bash
pytest -v
```
Tests verify atomic POS settlement and rollback, 1% loyalty accrual, 50% redemption cap enforcement, quintile RFM scoring and tier rules, role-based access control (403 enforcement), and the support ticket lifecycle.

---

## Cloud Deployment (Render)

The repository includes `render.yaml`, `build.sh`, `Procfile`, `gunicorn`, and `whitenoise` for one-click deployment on Render:

1. Open: `https://render.com/deploy?repo=https://github.com/Ahamefuna/ui-ventures-retail-crm`
2. Sign in to Render with your GitHub account and click **Apply**.
3. Render automatically installs dependencies, collects static assets, applies migrations, seeds the dataset, and exposes a public HTTPS link (`https://ui-ventures-retail-crm.onrender.com`).

