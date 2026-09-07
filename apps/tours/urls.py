from django.urls import path

from apps.tours import views

app_name = "tours"

urlpatterns = [
    path("", views.tour_list, name="list"),
    path("create/", views.tour_create, name="create"),
    path("<str:id>/edit/", views.tour_edit, name="edit"),
    path("<str:id>/gallery/", views.tour_gallery_add, name="gallery_add"),
    path("<str:id>/delete/", views.tour_delete, name="delete"),
    path("<str:id>/", views.tour_detail, name="detail"),
]
