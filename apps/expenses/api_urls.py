from django.urls import path

from apps.expenses import api
from core.access import FINANCE_ROLES
from core.http import method_view

app_name = "expenses_api"

urlpatterns = [
    path("", method_view(*FINANCE_ROLES, GET=api.list_expenses, POST=api.create_expense), name="collection"),
    path("<str:id>/", method_view(*FINANCE_ROLES, GET=api.get_expense, PATCH=api.patch_expense), name="detail"),
]
