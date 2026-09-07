from enum import StrEnum


class NotificationType(StrEnum):
    PAYMENT = "payment"
    REFUND = "refund"
    EXPENSE = "expense"
    SUPPLIER = "supplier"
    BOOKING = "booking"
    TOUR = "tour"
    SYSTEM = "system"
    ATTACHMENT = "attachment"


TYPE_LABELS = {
    NotificationType.PAYMENT.value: "Payment",
    NotificationType.REFUND.value: "Refund",
    NotificationType.EXPENSE.value: "Expense",
    NotificationType.SUPPLIER.value: "Supplier",
    NotificationType.BOOKING.value: "Booking",
    NotificationType.TOUR.value: "Tour",
    NotificationType.SYSTEM.value: "System",
    NotificationType.ATTACHMENT.value: "Attachment",
}

TYPE_CHOICES = tuple(TYPE_LABELS.items())

TYPE_BADGE = {
    NotificationType.REFUND.value: "b-warn",
    NotificationType.PAYMENT.value: "b-ok",
    NotificationType.EXPENSE.value: "b-info",
    NotificationType.SUPPLIER.value: "b-info",
    NotificationType.TOUR.value: "b-warm",
    NotificationType.BOOKING.value: "b-ok",
    NotificationType.SYSTEM.value: "b-mute",
    NotificationType.ATTACHMENT.value: "b-mute",
}
