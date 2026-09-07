from django.urls import path

from apps.notifications import views

app_name = "notifications"

urlpatterns = [
    path("", views.notification_list, name="list"),
    path("read-all/", views.notification_mark_all_read, name="read_all"),
    path("<str:id>/open/", views.notification_open, name="open"),
    path("<str:id>/read/", views.notification_mark_read, name="read"),
]
