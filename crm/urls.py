"""URL routing for all UI Ventures Retail CRM modules."""

from django.urls import path

from crm import views

app_name = "crm"

urlpatterns = [
    path("", views.home_redirect_view, name="home"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    # Analytical Dashboard (Admin & Manager)
    path("dashboard/", views.dashboard_view, name="dashboard"),
    # Customer Directory & Profile Management (Admin, Manager, Attendant)
    path("customers/", views.customers_list_view, name="customers"),
    path("customers/create/", views.customer_create_view, name="customer_create"),
    path("customers/<int:customer_id>/", views.customer_detail_view, name="customer_detail"),
    path("customers/<int:customer_id>/edit/", views.customer_edit_view, name="customer_edit"),
    path(
        "customers/<int:customer_id>/adjust-points/",
        views.customer_adjust_points_view,
        name="customer_adjust_points",
    ),
    # POS Checkout & Printable Digital Receipt
    path("pos/", views.pos_checkout_view, name="pos"),
    path("receipt/<int:txn_id>/", views.receipt_view, name="receipt"),
    # RFM Segmentation & Retention Campaigns (Admin & Manager)
    path("rfm/", views.rfm_view, name="rfm"),
    path("rfm/recompute/", views.rfm_recompute_view, name="rfm_recompute"),
    path("rfm/dispatch-alert/", views.rfm_dispatch_alert_view, name="rfm_dispatch_alert"),
    # Support Ticket & Feedback Portal (Staff & Customers)
    path("tickets/", views.tickets_view, name="tickets"),
    path("tickets/create/", views.ticket_create_view, name="ticket_create"),
    path("tickets/<int:ticket_id>/update/", views.ticket_update_view, name="ticket_update"),
    # Reports & CSV Exports (Admin & Manager)
    path("reports/", views.reports_view, name="reports"),
    path("reports/export/sales/", views.export_sales_csv_view, name="export_sales_csv"),
    path("reports/export/rfm/", views.export_rfm_csv_view, name="export_rfm_csv"),
    # Product Catalog Administration (Admin & Manager)
    path("products/", views.products_view, name="products"),
    path("products/create/", views.product_create_view, name="product_create"),
    path("products/<int:product_id>/edit/", views.product_edit_view, name="product_edit"),
    path("products/<int:product_id>/delete/", views.product_delete_view, name="product_delete"),
    # Staff Administration (Admin only)
    path("staff/", views.staff_view, name="staff"),
    path("staff/create/", views.staff_create_view, name="staff_create"),
    path("staff/<int:user_id>/edit/", views.staff_edit_view, name="staff_edit"),
    # Customer Self-Service Portal (Customer role)
    path("my-portal/", views.my_portal_view, name="my_portal"),
]
