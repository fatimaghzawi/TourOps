from django.urls import path

from apps.refunds import views

app_name = "refunds"

urlpatterns = [
    path("", views.refund_list, name="list"),
    path("new/", views.refund_create, name="create"),
    path("<str:id>/approve/", views.refund_approve, name="approve"),
    path("<str:id>/reject/", views.refund_reject, name="reject"),
    path("<str:id>/complete/", views.refund_complete, name="complete"),
    path("<str:id>/", views.refund_detail, name="detail"),
]
