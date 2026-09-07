from django.urls import path

from apps.presentation import views

app_name = "presentation"

urlpatterns = [
    path("", views.briefing, name="briefing"),
    path("watch/", views.play, name="play"),
    path("stop/", views.stop, name="stop"),
    path("go/<int:index>/", views.jump, name="jump"),
    path("state/", views.state, name="state"),
]
