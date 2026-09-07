from core.constants import ExpenseCategory, InvoiceStatus, PaymentRecordStatus, RefundStatus

FIELD_CLASS = "field"

EXPENSE_GROUPS = (
    ("Hotel", frozenset({ExpenseCategory.HOTEL.value})),
    ("Transport", frozenset({ExpenseCategory.TRANSPORTATION.value, ExpenseCategory.FLIGHT.value})),
    ("Guides", frozenset({ExpenseCategory.TOUR_GUIDE.value})),
    (
        "Overhead",
        frozenset(
            {
                ExpenseCategory.RENT.value,
                ExpenseCategory.SALARY.value,
                ExpenseCategory.UTILITIES.value,
                ExpenseCategory.SOFTWARE.value,
                ExpenseCategory.OFFICE.value,
                ExpenseCategory.MARKETING.value,
            }
        ),
    ),
)

REVENUE_INVOICE_STATUSES = {
    InvoiceStatus.ISSUED.value,
    InvoiceStatus.PARTIALLY_PAID.value,
    InvoiceStatus.PAID.value,
    InvoiceStatus.PARTIALLY_REFUNDED.value,
    InvoiceStatus.REFUNDED.value,
}

OPEN_INVOICE_STATUSES = {
    InvoiceStatus.ISSUED.value,
    InvoiceStatus.PARTIALLY_PAID.value,
}

LIVE_PAYMENT_STATUSES = {PaymentRecordStatus.COMPLETED.value}
CASH_REFUND_STATUSES = {RefundStatus.COMPLETED.value}

INVOICE_MONEY_FIELDS = ("total_amount", "paid_amount", "refunded_amount", "remaining_amount")
EXPENSE_MONEY_FIELDS = ("amount", "paid_amount", "remaining_amount")
