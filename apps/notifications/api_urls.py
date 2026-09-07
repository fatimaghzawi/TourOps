from django.urls import path

from apps.notifications import api
from core.http import method_view

app_name = "notifications_api"

urlpatterns = [
    path("", method_view(GET=api.list_notifications), name="collection"),
    path("read-all/", method_view(POST=api.mark_all_read), name="read_all"),
    path("<str:id>/read/", method_view(POST=api.mark_read), name="read"),
    path("<str:id>/", method_view(GET=api.get_notification), name="detail"),
]
