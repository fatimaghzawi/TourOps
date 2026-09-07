from django.urls import path

from apps.tours import views

app_name = "availability"

urlpatterns = [
    path("", views.availability, name="index"),
]
