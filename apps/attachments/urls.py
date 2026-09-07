from django.urls import path

from apps.attachments import views

app_name = "attachments"

urlpatterns = [
    path("", views.attachment_list, name="list"),
    path("upload/", views.attachment_upload, name="upload"),
    path("<str:id>/download/", views.attachment_download, name="download"),
    path("<str:id>/preview/", views.attachment_preview, name="preview"),
    path("<str:id>/delete/", views.attachment_delete, name="delete"),
]
