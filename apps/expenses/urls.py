from django.urls import path

from apps.expenses import views

app_name = "expenses"

urlpatterns = [
    path("", views.expense_list, name="list"),
    path("create/", views.expense_create, name="create"),
    path("<str:id>/edit/", views.expense_edit, name="edit"),
    path("<str:id>/delete/", views.expense_delete, name="delete"),
    path("<str:id>/", views.expense_detail, name="detail"),
]
