from core.constants import TourStatus

FIELD_CLASS = "field"

STATUS_LABELS = {
    TourStatus.DRAFT.value: "Draft",
    TourStatus.AVAILABLE.value: "Available",
    TourStatus.FULLY_BOOKED.value: "Fully booked",
    TourStatus.IN_PROGRESS.value: "In progress",
    TourStatus.COMPLETED.value: "Completed",
    TourStatus.CANCELLED.value: "Cancelled",
}
STATUS_CHOICES = tuple(STATUS_LABELS.items())

MONEY_FIELDS = ("selling_price_per_person",)
