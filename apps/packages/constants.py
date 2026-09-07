from core.constants import PackageStatus

FIELD_CLASS = "field"

STATUS_LABELS = {
    PackageStatus.ACTIVE.value: "Active",
    PackageStatus.INACTIVE.value: "Inactive",
}
STATUS_CHOICES = tuple(STATUS_LABELS.items())

MONEY_FIELDS = ("selling_price_per_person",)
