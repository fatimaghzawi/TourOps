from django.apps import AppConfig


class InvoicesConfig(AppConfig):
    name = "apps.invoices"
    label = "invoices"
    verbose_name = "Invoices"
    default_auto_field = "django.db.models.BigAutoField"
