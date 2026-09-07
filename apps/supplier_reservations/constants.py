from core.constants import SupplierReservationStatus, SupplierType

FIELD_CLASS = "field"

STATUS_LABELS = {
    SupplierReservationStatus.REQUESTED.value: "Requested",
    SupplierReservationStatus.CONFIRMED.value: "Confirmed",
    SupplierReservationStatus.CANCELLED.value: "Cancelled",
}
STATUS_CHOICES = tuple(STATUS_LABELS.items())

SERVICE_TYPE_LABELS = {
    SupplierType.HOTEL.value: "Accommodation",
    SupplierType.TRANSPORTATION.value: "Transportation",
    SupplierType.TOUR_GUIDE.value: "Guide",
    SupplierType.AIRLINE.value: "Airline",
    SupplierType.ACTIVITY_PROVIDER.value: "Activity",
    SupplierType.RESTAURANT.value: "Restaurant",
    SupplierType.INSURANCE.value: "Insurance",
    SupplierType.OTHER.value: "Other",
}
