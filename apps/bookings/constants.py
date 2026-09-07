from core.constants import BookingStatus

FIELD_CLASS = "field"

STATUS_LABELS = {
    BookingStatus.PENDING.value: "Pending",
    BookingStatus.CONFIRMED.value: "Confirmed",
    BookingStatus.COMPLETED.value: "Completed",
    BookingStatus.CANCELLED.value: "Cancelled",
}
STATUS_CHOICES = tuple(STATUS_LABELS.items())
