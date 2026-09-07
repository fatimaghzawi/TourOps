from core.constants import PaymentMethod, RecordStatus, SupplierType

FIELD_CLASS = "field"

TYPE_LABELS = {
    SupplierType.HOTEL.value: "Hotel",
    SupplierType.TRANSPORTATION.value: "Transportation",
    SupplierType.TOUR_GUIDE.value: "Guide",
    SupplierType.AIRLINE.value: "Airline",
    SupplierType.ACTIVITY_PROVIDER.value: "Activity",
    SupplierType.RESTAURANT.value: "Restaurant",
    SupplierType.INSURANCE.value: "Insurance",
    SupplierType.OTHER.value: "Other",
}
TYPE_CHOICES = tuple(TYPE_LABELS.items())

STATUS_CHOICES = (
    (RecordStatus.ACTIVE.value, "Active"),
    (RecordStatus.INACTIVE.value, "Inactive"),
)

PREFERRED_METHOD_LABELS = {
    PaymentMethod.BANK_TRANSFER.value: "Bank Transfer",
    PaymentMethod.CARD.value: "Card",
    PaymentMethod.CASH.value: "Cash",
    PaymentMethod.CHEQUE.value: "Cheque",
}
PREFERRED_METHOD_CHOICES = (
    (PaymentMethod.BANK_TRANSFER.value, "Bank Transfer"),
    (PaymentMethod.CARD.value, "Card"),
    (PaymentMethod.CASH.value, "Cash"),
)
PREFERRED_METHODS = set(PREFERRED_METHOD_LABELS)
PREFERRED_METHOD_HELP = {
    PaymentMethod.BANK_TRANSFER.value: "Opens the supplier’s bank account details.",
    PaymentMethod.CARD.value: "The agency pays with its own card. Card numbers are not stored here.",
    PaymentMethod.CASH.value: "Optional if the agency pays this supplier in cash.",
}

CORE_TYPES = (
    SupplierType.HOTEL.value,
    SupplierType.TRANSPORTATION.value,
    SupplierType.TOUR_GUIDE.value,
)
CORE_TYPE_CHOICES = tuple((value, TYPE_LABELS[value]) for value in CORE_TYPES)
CORE_TYPE_HELP = {
    SupplierType.HOTEL.value: "Opens hotel fields — star rating only.",
    SupplierType.TRANSPORTATION.value: "Opens fleet fields — vehicle, seats, coverage.",
    SupplierType.TOUR_GUIDE.value: "Opens guide fields — languages, specialties, experience.",
}
OTHER_GROUP_TYPES = tuple(item.value for item in SupplierType if item.value not in CORE_TYPES)

DIRECTORY_TYPES = {
    "HOTEL": (SupplierType.HOTEL.value,),
    "TRANSPORTATION": (SupplierType.TRANSPORTATION.value,),
    "TOUR_GUIDE": (SupplierType.TOUR_GUIDE.value,),
    "OTHER": OTHER_GROUP_TYPES,
}

KIND_LABELS = {
    "ACCOMMODATION": "Accommodation",
    "TRANSFER": "Transfer",
    "TRANSPORTATION": "Transportation",
    "GUIDE": "Guided tour",
    "ACTIVITY": "Activity",
    "MEAL": "Meal",
    "OTHER": "Other",
}
KIND_CHOICES = tuple(KIND_LABELS.items())

DEFAULT_KIND_BY_SUPPLIER = {
    SupplierType.HOTEL.value: "ACCOMMODATION",
    SupplierType.TRANSPORTATION.value: "TRANSFER",
    SupplierType.TOUR_GUIDE.value: "GUIDE",
    SupplierType.ACTIVITY_PROVIDER.value: "ACTIVITY",
    SupplierType.RESTAURANT.value: "MEAL",
}

INFO_FIELDS = {
    SupplierType.HOTEL.value: ("star_rating",),
    SupplierType.TRANSPORTATION.value: (
        "vehicle_type",
        "fleet_size",
        "seats_per_vehicle",
        "license_number",
        "coverage_areas",
    ),
    SupplierType.TOUR_GUIDE.value: (
        "languages",
        "license_number",
        "specialties",
        "years_experience",
    ),
    SupplierType.AIRLINE.value: ("iata_code", "alliance"),
    SupplierType.ACTIVITY_PROVIDER.value: ("activity_kinds", "typical_duration_hours", "location"),
    SupplierType.RESTAURANT.value: ("cuisine", "seating_capacity", "meal_types"),
    SupplierType.INSURANCE.value: ("policy_types", "coverage_notes"),
    SupplierType.OTHER.value: ("details",),
}

LIST_INFO_FIELDS = {
    "coverage_areas",
    "languages",
    "specialties",
    "activity_kinds",
    "meal_types",
    "policy_types",
}
INT_INFO_FIELDS = {
    "star_rating",
    "fleet_size",
    "seats_per_vehicle",
    "years_experience",
    "typical_duration_hours",
    "seating_capacity",
}
