from django.urls import path

from apps.attachments import api
from core.access import ALL_ROLES
from core.http import method_view

app_name = "attachments_api"

urlpatterns = [
    path("", method_view(*ALL_ROLES, GET=api.list_attachments, POST=api.create_attachment), name="collection"),
    path("<str:id>/download/", method_view(*ALL_ROLES, GET=api.download_attachment), name="download"),
    path("<str:id>/", method_view(*ALL_ROLES, GET=api.get_attachment, DELETE=api.delete_attachment), name="detail"),
]
