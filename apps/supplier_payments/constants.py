from apps.suppliers.constants import PREFERRED_METHOD_CHOICES, PREFERRED_METHOD_LABELS
from core.constants import PaymentMethod

FIELD_CLASS = "field"

METHOD_LABELS = {
    **PREFERRED_METHOD_LABELS,
    PaymentMethod.ONLINE.value: "Online",
    PaymentMethod.OTHER.value: "Other",
}
METHOD_CHOICES = tuple(METHOD_LABELS.items())
TRANSACTION_METHOD_CHOICES = PREFERRED_METHOD_CHOICES
ALLOWED_METHODS = set(METHOD_LABELS)
