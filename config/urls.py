from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", RedirectView.as_view(pattern_name="dashboard:home"), name="home"),
    path("", include("apps.accounts.urls")),
    path("dashboard/", include("apps.dashboard.urls")),
    path("customers/", include("apps.customers.urls")),
    path("bookings/", include("apps.bookings.urls")),
    path("suppliers/", include("apps.suppliers.urls")),
    path("tours/", include("apps.tours.urls")),
    path("packages/", include("apps.packages.urls")),
    path("availability/", include("apps.tours.availability_urls")),
    path("invoices/", include("apps.invoices.urls")),
    path("payments/", include("apps.payments.urls")),
    path("receipts/", include("apps.receipts.urls")),
    path("refunds/", include("apps.refunds.urls")),
    path("expenses/", include("apps.expenses.urls")),
    path("supplier-payments/", include("apps.supplier_payments.urls")),
    path("supplier-reservations/", include("apps.supplier_reservations.urls")),
    path("finance/", include("apps.finance.urls")),
    path("reports/", include("apps.reports.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("attachments/", include("apps.attachments.urls")),
    path("audit/", include("apps.audit.urls")),
    path("presentation/", include("apps.presentation.urls")),
    path("api/", include("config.api_urls")),
]

handler403 = "core.views.handler403"
handler404 = "core.views.handler404"
handler500 = "core.views.handler500"

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )
