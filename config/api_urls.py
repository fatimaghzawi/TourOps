from django.urls import include, path

urlpatterns = [
    path("", include("apps.accounts.api_urls")),
    path("customers/", include("apps.customers.api_urls")),
    path("bookings/", include("apps.bookings.api_urls")),
    path("tours/", include("apps.tours.api_urls")),
    path("packages/", include("apps.packages.api_urls")),
    path("suppliers/", include("apps.suppliers.api_urls")),
    path("invoices/", include("apps.invoices.api_urls")),
    path("payments/", include("apps.payments.api_urls")),
    path("receipts/", include("apps.receipts.api_urls")),
    path("refunds/", include("apps.refunds.api_urls")),
    path("expenses/", include("apps.expenses.api_urls")),
    path("supplier-payments/", include("apps.supplier_payments.api_urls")),
    path("supplier-reservations/", include("apps.supplier_reservations.api_urls")),
    path("finance/", include("apps.finance.api_urls")),
    path("reports/", include("apps.reports.api_urls")),
    path("dashboard/", include("apps.dashboard.api_urls")),
    path("notifications/", include("apps.notifications.api_urls")),
    path("attachments/", include("apps.attachments.api_urls")),
    path("audit/", include("apps.audit.api_urls")),
]
