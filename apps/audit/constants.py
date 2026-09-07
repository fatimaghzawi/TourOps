from enum import StrEnum


class AuditAction(StrEnum):
    CREATED = "CREATED"
    UPDATED = "UPDATED"
    DELETED = "DELETED"
    VOIDED = "VOIDED"
    CANCELLED = "CANCELLED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"
    UPLOADED = "UPLOADED"
    DOWNLOADED = "DOWNLOADED"
    STATUS_CHANGED = "STATUS_CHANGED"
    ROLE_CHANGED = "ROLE_CHANGED"
    LOGIN = "LOGIN"
    EMAIL_GENERATED = "EMAIL_GENERATED"
    EMAIL_SENT = "EMAIL_SENT"


ACTION_LABELS = {
    AuditAction.CREATED.value: "Created",
    AuditAction.UPDATED.value: "Updated",
    AuditAction.DELETED.value: "Deleted",
    AuditAction.VOIDED.value: "Voided",
    AuditAction.CANCELLED.value: "Cancelled",
    AuditAction.APPROVED.value: "Approved",
    AuditAction.REJECTED.value: "Rejected",
    AuditAction.COMPLETED.value: "Completed",
    AuditAction.UPLOADED.value: "Uploaded",
    AuditAction.DOWNLOADED.value: "Downloaded",
    AuditAction.STATUS_CHANGED.value: "Changed status",
    AuditAction.ROLE_CHANGED.value: "Changed role",
    AuditAction.LOGIN.value: "Signed in",
    AuditAction.EMAIL_GENERATED.value: "Prepared email",
    AuditAction.EMAIL_SENT.value: "Sent email",
}

ACTION_CHOICES = tuple(ACTION_LABELS.items())

ACTION_BADGE = {
    AuditAction.CREATED.value: "b-ok",
    AuditAction.UPDATED.value: "b-info",
    AuditAction.DELETED.value: "b-bad",
    AuditAction.VOIDED.value: "b-warn",
    AuditAction.CANCELLED.value: "b-warn",
    AuditAction.APPROVED.value: "b-ok",
    AuditAction.REJECTED.value: "b-bad",
    AuditAction.COMPLETED.value: "b-ok",
    AuditAction.UPLOADED.value: "b-info",
    AuditAction.DOWNLOADED.value: "b-mute",
    AuditAction.STATUS_CHANGED.value: "b-warm",
    AuditAction.ROLE_CHANGED.value: "b-warm",
    AuditAction.LOGIN.value: "b-mute",
    AuditAction.EMAIL_GENERATED.value: "b-info",
    AuditAction.EMAIL_SENT.value: "b-ok",
}

ENTITY_CHOICES = (
    ("expenses", "Expense"),
    ("supplier_payments", "Supplier payment"),
    ("invoices", "Invoice"),
    ("payments", "Payment"),
    ("refunds", "Refund"),
    ("suppliers", "Supplier"),
    ("packages", "Package"),
    ("tours", "Tour"),
    ("bookings", "Booking"),
    ("customers", "Customer"),
    ("supplier_reservations", "Supplier reservation"),
    ("attachments", "Attachment"),
    ("users", "User"),
)
ENTITY_LABELS = dict(ENTITY_CHOICES)

