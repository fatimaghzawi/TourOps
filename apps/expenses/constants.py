from core.constants import ExpenseCategory, ExpensePaymentStatus, ExpenseScope

MONEY_FIELDS = ("amount", "paid_amount", "remaining_amount")

CATEGORY_LABELS = {item.value: item.value.replace("_", " ").title() for item in ExpenseCategory}
CATEGORY_CHOICES = tuple((item.value, CATEGORY_LABELS[item.value]) for item in ExpenseCategory)

SCOPE_LABELS = {
    ExpenseScope.TOUR.value: "Tour",
    ExpenseScope.GENERAL.value: "General",
}
SCOPE_CHOICES = tuple(SCOPE_LABELS.items())

STATUS_LABELS = {
    ExpensePaymentStatus.UNPAID.value: "Unpaid",
    ExpensePaymentStatus.PARTIALLY_PAID.value: "Partially paid",
    ExpensePaymentStatus.PAID.value: "Paid",
}
STATUS_CHOICES = tuple(STATUS_LABELS.items())

FIELD_CLASS = "field"
