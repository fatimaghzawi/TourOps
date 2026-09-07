from django.apps import AppConfig


class ExpensesConfig(AppConfig):
    name = "apps.expenses"
    label = "expenses"
    verbose_name = "Expenses"
    default_auto_field = "django.db.models.BigAutoField"
