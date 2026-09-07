from django.urls import path

from apps.dashboard import views

app_name = "dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    path("agent/", views.agent, name="agent"),
    path("accountant/", views.accountant, name="accountant"),
    path("owner/", views.owner, name="owner"),
]
