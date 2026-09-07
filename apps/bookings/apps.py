from django.apps import AppConfig


class BookingsConfig(AppConfig):
    name = "apps.bookings"
    label = "bookings"
    verbose_name = "Bookings"
    default_auto_field = "django.db.models.BigAutoField"
